"""Separable pixel point-spread functions and polygon weighting schemes.

A PSF is described per axis (along-scan "s", along-track "t") as a convolution of simple
1-D components in units of the pixel's own sample spacing (W_s / W_t from footprint.py):

    {"type": "rect",  "width": w}    box of full width w
    {"type": "gauss", "fwhm": f}     Gaussian with that FWHM

e.g. MODIS along-scan = rect(1) * rect(1) (detector * scan-motion integration -> triangle,
FWHM 1 sample, base 2 samples). Parameters live in config/psf.toml with citations.

Weighting schemes for the mean of a variable over polygon A (estimate = sum w_i x_i / sum w_i):

    naive_center   w_i = 1 if the pixel centre is inside A
    naive_square   w_i = |S_i ∩ A|, S_i = square of the *nadir* pixel size at the centre
    voronoi        w_i = |V_i ∩ A|, V_i = Voronoi cell of the centre (nearest-neighbour partition)
    footprint      w_i = |F_i ∩ A|, F_i = trig footprint quadrilateral (overlaps double-count)
    footprint_pou  w_i = ∫_A b_i(s) / Σ_j b_j(s) ds, b_i = box PSF of F_i ("partition of unity":
                   each point of A splits its unit area among the pixels that see it)
    psf            w_i = |F_i| ∫_A p_i(s) ds, p_i = sensor PSF (spill-over, no overlap handling)
    psf_pou        w_i = ∫_A p_i(s) / Σ_j p_j(s) ds  (partition of unity with the sensor PSF)

The *_pou integrals are evaluated by quadrature in each pixel's own frame, with the
denominator accumulated on a fine raster in a local equal-area plane.
"""

from __future__ import annotations

import numpy as np
import shapely

from .footprint import PixelGeom

BOX = {"s": [{"type": "rect", "width": 1.0}], "t": [{"type": "rect", "width": 1.0}]}


def kernel_1d(components, n=257):
    """Tabulate a 1-D kernel (normalised, unit = sample spacing). Returns (u, f, du)."""
    half = 0.0
    for c in components:
        half += c["width"] / 2 if c["type"] == "rect" else 3.0 * c["fwhm"] / 2.355
    half = max(half, 0.5)
    u = np.linspace(-half, half, n)
    du = u[1] - u[0]
    f = None
    for c in components:
        if c["type"] == "rect":
            k = (np.abs(u) <= c["width"] / 2 + 1e-12).astype(float)
        elif c["type"] == "gauss":
            sig = c["fwhm"] / 2.355
            k = np.exp(-0.5 * (u / sig) ** 2)
        else:
            raise ValueError(c)
        k /= k.sum()
        f = k if f is None else np.convolve(f, k, mode="same")
    f /= f.sum()
    return u, f, du


def support(components):
    u, _, _ = kernel_1d(components)
    return u[-1] - u[0]


def quadrature(psf, k=9):
    """Nodes (u, v) and masses for a separable PSF, k nodes per axis (int or (ks, kt)) placed
    at the centres of k equal-width bins over the support (mass = PSF integral over the bin)."""
    ks = (k, k) if np.isscalar(k) else k
    out = []
    for ax, k in zip(("s", "t"), ks):
        u, f, _ = kernel_1d(psf[ax])
        edges = np.linspace(u[0], u[-1], k + 1)
        mass = np.array([f[(u >= a) & (u < b) if i < k - 1 else (u >= a) & (u <= b)].sum()
                         for i, (a, b) in enumerate(zip(edges[:-1], edges[1:]))])
        nodes = 0.5 * (edges[:-1] + edges[1:])
        out.append((nodes, mass / mass.sum()))
    (us, ms), (vt, mt) = out
    U, V = np.meshgrid(us, vt, indexing="ij")
    M = np.outer(ms, mt)
    return U.ravel(), V.ravel(), M.ravel()


def fwhm(components):
    u, f, _ = kernel_1d(components, n=4097)
    above = u[f >= f.max() / 2]
    return above.max() - above.min()


def node_xy(pg: PixelGeom, U, V):
    """World (local metre) coordinates of quadrature nodes for every pixel: (n_pix, n_node, 2)."""
    c = np.stack([pg.x, pg.y], -1)[:, None, :]
    return (c + (U[None, :, None] * pg.W_s[:, None, None]) * pg.e_s[:, None, :]
            + (V[None, :, None] * pg.W_t[:, None, None]) * pg.e_t[:, None, :])


class Raster:
    """Fine raster over the local plane, used for the partition-of-unity denominator."""

    def __init__(self, bounds, cell):
        x0, y0, x1, y1 = bounds
        self.x0, self.y0, self.cell = x0, y0, cell
        self.nx = int(np.ceil((x1 - x0) / cell)) + 1
        self.ny = int(np.ceil((y1 - y0) / cell)) + 1

    def index(self, xy):
        ix = np.floor((xy[..., 0] - self.x0) / self.cell).astype(np.int64)
        iy = np.floor((xy[..., 1] - self.y0) / self.cell).astype(np.int64)
        ok = (ix >= 0) & (ix < self.nx) & (iy >= 0) & (iy < self.ny)
        return np.where(ok, iy * self.nx + ix, -1)

    def centres(self):
        xs = self.x0 + (np.arange(self.nx) + 0.5) * self.cell
        ys = self.y0 + (np.arange(self.ny) + 0.5) * self.cell
        X, Y = np.meshgrid(xs, ys)
        return X.ravel(), Y.ravel()


def psf_weights(pg: PixelGeom, poly_local, psf, k=None, cell=None, pou=True, batch=20000, group=None,
                cell_factor=0.5):
    """Weights of each pixel for polygon `poly_local` (local metres) under `psf`.

    pou=False: w_i = |F_i| * ∫_A p_i ;  pou=True: w_i = ∫_A p_i / Σ_j p_j.
    Pixels must include a margin around A (so Σ_j p_j is complete inside A).
    `psf` may be a dict {group_id: psf} with `group` giving each pixel's group id
    (e.g. VIIRS aggregation zone).
    """
    n = len(pg.x)
    psfs = psf if (isinstance(psf, dict) and "s" not in psf) else {0: psf}
    group = np.asarray(group) if group is not None else np.zeros(n, int)
    # raster cell ~ half the typical short pixel side; node spacing must not exceed it,
    # otherwise raster cells receive no PSF mass (holes in the partition of unity)
    cell = cell or cell_factor * float(np.nanmedian(np.minimum(pg.W_s, pg.W_t)))
    quads = {}
    for g, p in psfs.items():
        m = group == g
        if not m.any():
            continue
        if k is None:
            kk = tuple(int(np.clip(np.ceil(1.5 * support(p[ax]) * np.nanmax(W[m]) / cell) + 1, 5, 61))
                       for ax, W in (("s", pg.W_s), ("t", pg.W_t)))
        else:
            kk = k
        quads[g] = quadrature(p, kk)
    b = shapely.bounds(poly_local)
    pad = float(np.nanmax(np.maximum(pg.W_s, pg.W_t))) * 2
    ras = Raster((b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad), cell)
    cx, cy = ras.centres()
    shapely.prepare(poly_local)
    near = shapely.contains_xy(shapely.buffer(poly_local, 1.5 * cell), cx, cy)  # cells near/inside A
    # pass 1: total PSF mass per cell (density x cell area summed over pixels)
    tot = np.zeros(ras.nx * ras.ny)
    def batches():
        for g, (U, V, M) in quads.items():
            ids = np.flatnonzero(group == g)
            for s in range(0, len(ids), batch):
                yield ids[s:s + batch], U, V, M

    if pou:
        for sl, U, V, M in batches():
            xy = node_xy(_slice(pg, sl), U, V)
            idx = ras.index(xy)
            ok = idx >= 0
            tot += np.bincount(idx[ok], weights=np.broadcast_to(M, idx.shape)[ok], minlength=tot.size)
    # pass 2: weights
    w = np.zeros(n)
    area_cell = cell * cell
    for sl, U, V, M in batches():
        xy = node_xy(_slice(pg, sl), U, V)
        idx = ras.index(xy)
        ok = idx >= 0
        ins = np.zeros(idx.shape, bool)
        cand = np.zeros(idx.shape, bool)
        cand[ok] = near[idx[ok]]  # only test nodes in cells near A exactly
        ins[cand] = shapely.contains_xy(poly_local, xy[..., 0][cand], xy[..., 1][cand])
        if pou:
            dens = np.zeros(idx.shape)
            dens[ok] = tot[idx[ok]]
            contrib = np.where(ins & (dens > 0), M[None, :] * area_cell / np.where(dens > 0, dens, 1), 0.0)
            w[sl] = contrib.sum(1)
        else:
            w[sl] = (np.where(ins, M[None, :], 0.0)).sum(1) * pg.area[sl]
    return w


def _slice(pg: PixelGeom, sl):
    from dataclasses import replace

    return replace(pg, rows=pg.rows[sl], cols=pg.cols[sl], lat=pg.lat[sl], lon=pg.lon[sl], x=pg.x[sl],
                   y=pg.y[sl], e_s=pg.e_s[sl], e_t=pg.e_t[sl], W_s=pg.W_s[sl], W_t=pg.W_t[sl],
                   vza=pg.vza[sl], range_m=pg.range_m[sl])


def area_weights(polys_local, poly_local):
    """|P_i ∩ A| for shapely polygons (local metres)."""
    return shapely.area(shapely.intersection(polys_local, poly_local))


def psf_lsq_weights(pg: PixelGeom, poly_local, psf, k=None, cell=None, group=None, cell_factor=0.5,
                    max_pixels=2500):
    """PSF-optimal weights: non-negative least squares so that the weighted sum of the pixels'
    PSFs best reproduces the polygon's indicator function,

        min_w || sum_i w_i p_i(s) - 1_A(s) ||^2,  w >= 0   (on a raster around A)

    so the estimate sum_i w_i x_i / sum_i w_i is the best linear (non-negative) approximation
    of the polygon mean seen through the PSF. Pixels whose PSF mostly lies outside A get
    little weight even if they touch A. Returns NaN weights if the subset is too large.
    """
    from scipy.optimize import nnls
    from scipy.sparse import coo_matrix

    n = len(pg.x)
    if n > max_pixels:
        return np.full(n, np.nan)
    psfs = psf if (isinstance(psf, dict) and "s" not in psf) else {0: psf}
    group = np.asarray(group) if group is not None else np.zeros(n, int)
    cell = cell or cell_factor * float(np.nanmedian(np.minimum(pg.W_s, pg.W_t)))
    b = shapely.bounds(poly_local)
    pad = float(np.nanmax(np.maximum(pg.W_s, pg.W_t))) * 2
    ras = Raster((b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad), cell)
    cx, cy = ras.centres()
    shapely.prepare(poly_local)
    target = shapely.contains_xy(poly_local, cx, cy).astype(float)
    rows, cols, vals = [], [], []
    for g, p in psfs.items():
        ids = np.flatnonzero(group == g)
        if len(ids) == 0:
            continue
        kk = k or tuple(int(np.clip(np.ceil(1.5 * support(p[ax]) * np.nanmax(W[ids]) / cell) + 1, 5, 61))
                        for ax, W in (("s", pg.W_s), ("t", pg.W_t)))
        U, V, M = quadrature(p, kk)
        xy = node_xy(_slice(pg, ids), U, V)
        idx = ras.index(xy)
        ok = idx >= 0
        pix = np.broadcast_to(ids[:, None], idx.shape)
        rows.append(idx[ok])
        cols.append(pix[ok])
        vals.append(np.broadcast_to(M, idx.shape)[ok])
    A = coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                   shape=(ras.nx * ras.ny, n)).tocsr()
    # each column: fraction of pixel i's PSF mass in each cell; scale to "coverage" per cell
    used = np.unique(A.nonzero()[0])
    Ad = A[used].toarray() * (1.0 / (cell * cell))
    tgt = target[used]
    w, _ = nnls(Ad, tgt, maxiter=50 * n)
    return w
