"""Pixel locators: (lat, lon) targets -> (row, col) of a swath.

Every locator has the same interface:

    loc = Locator(**options)
    loc.build(lat2d, lon2d)                      # timed separately ("build the index")
    rows, cols, dist_m = loc.query_points(plat, plon)
    rows, cols = loc.query_polygon(poly, buffer_m)  # pixel *centres* inside poly buffered by
                                                    # buffer_m (candidates for exact footprint
                                                    # intersection, see footprint.py)

Points: nearest pixel centre (great-circle). Polygons: all pixel centres inside the polygon
grown by `buffer_m` (>= the largest pixel half-diagonal), so every pixel whose footprint could
touch the polygon is returned. All locators must return identical sets (verified in tests).
"""

from __future__ import annotations

import numpy as np
import shapely

from . import geom

# ---------------------------------------------------------------------------------------
# helpers


def _valid(lat, lon):
    ok = np.isfinite(lat) & np.isfinite(lon)
    return np.flatnonzero(ok.ravel())


def _buffer_ll(poly, buffer_m):
    """Buffer a lon/lat polygon by metres (local azimuthal equidistant projection)."""
    c = poly.centroid
    tr = geom.local_aeqd(c.y, c.x)
    fwd = shapely.transform(poly, lambda xy: np.column_stack(tr.transform(xy[:, 0], xy[:, 1])))
    b = fwd.buffer(buffer_m)
    return shapely.transform(b, lambda xy: np.column_stack(tr.transform(xy[:, 0], xy[:, 1], direction="INVERSE")))


def _filter_in_poly(poly_b, lat_flat, lon_flat, cand):
    if len(cand) == 0:
        return cand
    keep = shapely.contains_xy(poly_b, lon_flat[cand], lat_flat[cand])
    return cand[keep]


def _nearest_among(plat, plon, lat_flat, lon_flat, cand_lists):
    """For each target pick the nearest of its candidate flat indices."""
    out = np.full(len(plat), -1, dtype=np.int64)
    dist = np.full(len(plat), np.nan)
    for i, cand in enumerate(cand_lists):
        if len(cand) == 0:
            continue
        d = geom.haversine_m(plat[i], plon[i], lat_flat[cand], lon_flat[cand])
        k = np.nanargmin(d)
        out[i], dist[i] = cand[k], d[k]
    return out, dist


class Locator:
    name = "base"
    supports_polygon = True

    def build(self, lat, lon):
        self.shape = lat.shape
        self.lat_flat = np.ascontiguousarray(lat, dtype=np.float64).ravel()
        self.lon_flat = np.ascontiguousarray(lon, dtype=np.float64).ravel()
        self._build()
        return self

    def _build(self):
        pass

    def _unravel(self, flat):
        r, c = np.unravel_index(np.where(flat >= 0, flat, 0), self.shape)
        return np.where(flat >= 0, r, -1), np.where(flat >= 0, c, -1)

    def query_points(self, plat, plon):
        plat = np.atleast_1d(np.asarray(plat, float))
        plon = np.atleast_1d(np.asarray(plon, float))
        flat, dist = self._query_points(plat, plon)
        r, c = self._unravel(flat)
        return r, c, dist

    def query_polygon(self, poly, buffer_m):
        poly_b = _buffer_ll(poly, buffer_m)
        flat = np.unique(self._query_polygon(poly_b))
        return self._unravel(flat)

    def index_nbytes(self) -> int:
        return 0


# ---------------------------------------------------------------------------------------
# naive


class NaiveFull(Locator):
    """Brute force: great-circle distance to every pixel, argmin. Polygon: contains_xy on all."""

    name = "naive_full"

    def _query_points(self, plat, plon):
        out = np.empty(len(plat), np.int64)
        dist = np.empty(len(plat))
        for i in range(len(plat)):
            d = geom.haversine_m(plat[i], plon[i], self.lat_flat, self.lon_flat)
            k = np.nanargmin(d)
            out[i], dist[i] = k, d[k]
        return out, dist

    def _query_polygon(self, poly_b):
        ok = np.isfinite(self.lat_flat)
        cand = np.flatnonzero(ok)
        return _filter_in_poly(poly_b, self.lat_flat, self.lon_flat, cand)


class NaiveBBox(Locator):
    """Brute force on a lat/lon box prefilter (|dlat| < w, |dlon| < w/cos(lat)) - the usual
    'numpy.where' approach. Box half-width w in degrees must exceed half the pixel size."""

    name = "naive_bbox"

    def __init__(self, half_width_deg=0.1):
        self.w = half_width_deg

    def _query_points(self, plat, plon):
        cands = []
        for la, lo in zip(plat, plon):
            wl = self.w / max(np.cos(np.radians(la)), 0.05)
            dlon = (self.lon_flat - lo + 180) % 360 - 180
            m = (np.abs(self.lat_flat - la) < self.w) & (np.abs(dlon) < wl)
            cands.append(np.flatnonzero(m))
        return _nearest_among(plat, plon, self.lat_flat, self.lon_flat, cands)

    def _query_polygon(self, poly_b):
        x0, y0, x1, y1 = poly_b.bounds
        m = (self.lat_flat >= y0) & (self.lat_flat <= y1) & (self.lon_flat >= x0) & (self.lon_flat <= x1)
        return _filter_in_poly(poly_b, self.lat_flat, self.lon_flat, np.flatnonzero(m))


# ---------------------------------------------------------------------------------------
# KD-trees on unit vectors (chord distance is monotone in great-circle distance)


class ScipyKDTree(Locator):
    name = "kdtree_scipy"

    def _build(self):
        from scipy.spatial import cKDTree

        self.idx = _valid(self.lat_flat, self.lon_flat)
        xyz = geom.unit_xyz(self.lat_flat[self.idx], self.lon_flat[self.idx])
        self.tree = cKDTree(xyz, balanced_tree=False, compact_nodes=False)

    def _query_points(self, plat, plon):
        _, k = self.tree.query(geom.unit_xyz(plat, plon), workers=-1)
        flat = self.idx[k]
        return flat, geom.haversine_m(plat, plon, self.lat_flat[flat], self.lon_flat[flat])

    def _query_polygon(self, poly_b):
        c = poly_b.centroid
        xs, ys = poly_b.exterior.xy
        r = geom.haversine_m(c.y, c.x, np.asarray(ys), np.asarray(xs)).max()
        chord = 2 * np.sin(r / geom.R_MEAN / 2) * 1.001
        k = np.asarray(self.tree.query_ball_point(geom.unit_xyz(c.y, c.x), chord, workers=-1), dtype=np.int64)
        return _filter_in_poly(poly_b, self.lat_flat, self.lon_flat, self.idx[k])

    def index_nbytes(self):
        return self.tree.size * (3 * 8 + 8) * 2


class PyKDTree(Locator):
    """pykdtree (OpenMP; what pyresample uses). No ball query -> polygon via bbox prefilter."""

    name = "kdtree_pykdtree"

    def _build(self):
        from pykdtree.kdtree import KDTree

        self.idx = _valid(self.lat_flat, self.lon_flat)
        self.xyz = geom.unit_xyz(self.lat_flat[self.idx], self.lon_flat[self.idx])
        self.tree = KDTree(self.xyz, leafsize=16)

    def _query_points(self, plat, plon):
        _, k = self.tree.query(geom.unit_xyz(plat, plon), k=1)
        flat = self.idx[k.astype(np.int64)]
        return flat, geom.haversine_m(plat, plon, self.lat_flat[flat], self.lon_flat[flat])

    def _query_polygon(self, poly_b):
        # pykdtree has no radius query; use k-NN with a distance upper bound, growing k.
        c = poly_b.centroid
        xs, ys = poly_b.exterior.xy
        r = geom.haversine_m(c.y, c.x, np.asarray(ys), np.asarray(xs)).max()
        chord = 2 * np.sin(r / geom.R_MEAN / 2) * 1.001
        k = 4096
        q = geom.unit_xyz(c.y, c.x)[None]
        while True:
            d, i = self.tree.query(q, k=min(k, len(self.idx)), distance_upper_bound=chord)
            i = i[0][np.isfinite(d[0])].astype(np.int64)
            if len(i) < min(k, len(self.idx)):
                break
            k *= 4
        return _filter_in_poly(poly_b, self.lat_flat, self.lon_flat, self.idx[i])


# ---------------------------------------------------------------------------------------
# xarray / xoak


class XarrayNDPoint(Locator):
    """xarray.indexes.NDPointIndex + a tree adapter (xarray's own ScipyKDTreeAdapter on raw
    lat/lon degrees, or xoak's SklearnGeoBallTreeAdapter (haversine) / S2PointTreeAdapter).
    Selection: ds.sel(lat=..., lon=..., method="nearest"). No polygon support."""

    supports_polygon = False

    def __init__(self, adapter="xoak_s2"):
        self.adapter = adapter
        self.name = f"xarray_ndpoint_{adapter}"

    def _build(self):
        import xarray as xr

        if self.adapter == "scipy_degrees":
            ad, opts = None, {}
        elif self.adapter == "xoak_geoballtree":
            from xoak import SklearnGeoBallTreeAdapter as ad

            opts = {}
        elif self.adapter == "xoak_s2":
            from xoak import S2PointTreeAdapter as ad

            opts = {}
        lat = self.lat_flat.reshape(self.shape)
        lon = self.lon_flat.reshape(self.shape)
        if not (np.isfinite(lat).all() and np.isfinite(lon).all()):
            # trees cannot hold NaN coordinates; push fill pixels far away (south pole region)
            lat = np.where(np.isfinite(lat), lat, -89.999)
            lon = np.where(np.isfinite(lon), lon, 0.0)
        ds = xr.Dataset(coords={"lat": (("y", "x"), lat), "lon": (("y", "x"), lon),
                                "row": ("y", np.arange(self.shape[0])), "col": ("x", np.arange(self.shape[1]))})
        kw = {} if ad is None else {"tree_adapter_cls": ad}
        self.ds = ds.set_xindex(("lat", "lon"), xr.indexes.NDPointIndex, **kw)

    def _query_points(self, plat, plon):
        import xarray as xr

        sel = self.ds.sel(lat=xr.Variable("pt", plat), lon=xr.Variable("pt", plon), method="nearest")
        r = sel["row"].values
        c = sel["col"].values
        flat = np.ravel_multi_index((r, c), self.shape)
        return flat, geom.haversine_m(plat, plon, self.lat_flat[flat], self.lon_flat[flat])

    def _query_polygon(self, poly_b):
        raise NotImplementedError


class XarrayNaiveSel(Locator):
    """What most people try first: ds.sel(lat=.., lon=.., method='nearest') with 2-D coords.
    Fails (no index on non-dimension coordinates); kept to document the failure mode."""

    name = "xarray_sel_default"
    supports_polygon = False

    def _build(self):
        import xarray as xr

        self.ds = xr.Dataset(coords={"lat": (("y", "x"), self.lat_flat.reshape(self.shape)),
                                     "lon": (("y", "x"), self.lon_flat.reshape(self.shape))})

    def _query_points(self, plat, plon):
        self.ds.sel(lat=plat[0], lon=plon[0], method="nearest")  # raises
        raise RuntimeError("unreachable")


# ---------------------------------------------------------------------------------------
# S2


def _s2_leaf_ids(lat, lon):
    """Vectorised S2 leaf cell ids (uint64) for lat/lon in degrees (port of S2CellId logic,
    validated against s2sphere in tests)."""
    from s2sphere.sphere import LOOKUP_POS

    lut = np.asarray(LOOKUP_POS, dtype=np.uint64)
    p = geom.unit_xyz(lat, lon)
    ap = np.abs(p)
    axis = ap.argmax(-1)
    face = np.where(p[np.arange(len(p)), axis] < 0, axis + 3, axis)
    x, y, z = p[:, 0], p[:, 1], p[:, 2]
    with np.errstate(divide="ignore", invalid="ignore"):
        u = np.select([face == 0, face == 1, face == 2, face == 3, face == 4, face == 5],
                      [y / x, -x / y, -x / z, z / x, z / y, -y / z])
        v = np.select([face == 0, face == 1, face == 2, face == 3, face == 4, face == 5],
                      [z / x, z / y, -y / z, y / x, -x / y, -x / z])

    def uv2st(t):
        with np.errstate(invalid="ignore"):
            return np.where(t >= 0, 0.5 * np.sqrt(1 + 3 * t), 1 - 0.5 * np.sqrt(1 - 3 * t))

    max_size = 1 << 30
    i = np.clip(np.floor(uv2st(u) * max_size), 0, max_size - 1).astype(np.uint64)
    j = np.clip(np.floor(uv2st(v) * max_size), 0, max_size - 1).astype(np.uint64)
    face = face.astype(np.uint64)
    n = face << np.uint64(60)
    bits = face & np.uint64(1)  # SWAP_MASK
    mask = np.uint64(15)
    for k in range(7, -1, -1):
        sh = np.uint64(k * 4)
        bits = bits + (((i >> sh) & mask) << np.uint64(6))
        bits = bits + (((j >> sh) & mask) << np.uint64(2))
        bits = lut[bits]
        n = n | ((bits >> np.uint64(2)) << np.uint64(k * 8))
        bits = bits & np.uint64(3)  # SWAP_MASK | INVERT_MASK
    return n * np.uint64(2) + np.uint64(1)


def _s2_range(cell_ids, level):
    """[min, max] leaf-id range of the level-`level` ancestors of cell ids."""
    lsb = np.uint64(1) << np.uint64(2 * (30 - level))
    parent = (cell_ids & ~(lsb * np.uint64(2) - np.uint64(1))) | lsb
    return parent - lsb + np.uint64(1), parent + lsb - np.uint64(1)


class S2PointIndexLoc(Locator):
    """pys2index.S2PointIndex (C++ S2 library, nearest-neighbour). No region query API ->
    polygon not supported directly."""

    name = "s2_pys2index"
    supports_polygon = False

    def _build(self):
        from pys2index import S2PointIndex

        self.idx = _valid(self.lat_flat, self.lon_flat)
        self.index = S2PointIndex(np.column_stack([self.lat_flat[self.idx], self.lon_flat[self.idx]]))

    def _query_points(self, plat, plon):
        _, k = self.index.query(np.column_stack([plat, plon]))
        flat = self.idx[np.asarray(k, np.int64)]
        return flat, geom.haversine_m(plat, plon, self.lat_flat[flat], self.lon_flat[flat])

    def _query_polygon(self, poly_b):
        raise NotImplementedError


class S2SortedIndex(Locator):
    """Sorted S2 leaf cell ids of every pixel centre (a 'spatial key' you could also store
    on disk). Point: candidates in the target's level-L cell + 8 neighbours. Polygon:
    S2 covering of the polygon -> contiguous id ranges -> searchsorted."""

    def __init__(self, level: int):
        self.level = level
        self.name = "s2_sorted"

    def _build(self):
        self.idx = _valid(self.lat_flat, self.lon_flat)
        ids = _s2_leaf_ids(self.lat_flat[self.idx], self.lon_flat[self.idx])
        order = np.argsort(ids, kind="stable")
        self.ids = ids[order]
        self.order = self.idx[order]

    def _ranges_to_flat(self, lo, hi):
        a = np.searchsorted(self.ids, lo, "left")
        b = np.searchsorted(self.ids, hi, "right")
        if len(a) == 0:
            return np.empty(0, np.int64)
        return np.concatenate([self.order[x:y] for x, y in zip(a, b)])

    def _query_points(self, plat, plon):
        import s2sphere as s2

        cands = []
        for la, lo in zip(plat, plon):
            c = s2.CellId.from_lat_lng(s2.LatLng.from_degrees(la, lo)).parent(self.level)
            cells = [c, *c.get_all_neighbors(self.level)]
            lo_ = np.array([x.range_min().id() for x in cells], np.uint64)
            hi_ = np.array([x.range_max().id() for x in cells], np.uint64)
            cands.append(self._ranges_to_flat(lo_, hi_))
        return _nearest_among(plat, plon, self.lat_flat, self.lon_flat, cands)

    def _query_polygon(self, poly_b):
        import s2sphere as s2

        x0, y0, x1, y1 = poly_b.bounds
        rect = s2.LatLngRect.from_point_pair(s2.LatLng.from_degrees(y0, x0), s2.LatLng.from_degrees(y1, x1))
        cov = s2.RegionCoverer()
        cov.min_level, cov.max_level, cov.max_cells = max(self.level - 6, 0), self.level, 256
        cells = cov.get_covering(rect)
        # drop covering cells that do not touch the polygon (cell polygon from its vertices)
        keep = []
        for c in cells:
            cell = s2.Cell(c)
            vs = [s2.LatLng.from_point(cell.get_vertex(k)) for k in range(4)]
            cp = shapely.Polygon([(v.lng().degrees, v.lat().degrees) for v in vs])
            if cp.intersects(poly_b):
                keep.append(c)
        lo_ = np.array([c.range_min().id() for c in keep], np.uint64)
        hi_ = np.array([c.range_max().id() for c in keep], np.uint64)
        return _filter_in_poly(poly_b, self.lat_flat, self.lon_flat, self._ranges_to_flat(lo_, hi_))

    def index_nbytes(self):
        return self.ids.nbytes + self.order.nbytes


# ---------------------------------------------------------------------------------------
# H3


class H3SortedIndex(Locator):
    """Sorted H3 cell ids (h3ronpy, vectorised) of every pixel centre. Point: candidates in
    grid_disk(target cell, k). Polygon: h3 polygon_to_cells (overlapping) -> lookup."""

    def __init__(self, res: int, k: int = 1):
        self.res, self.k = res, k
        self.name = "h3_sorted"

    def _build(self):
        from h3ronpy.vector import coordinates_to_cells

        self.idx = _valid(self.lat_flat, self.lon_flat)
        cells = np.asarray(coordinates_to_cells(self.lat_flat[self.idx], self.lon_flat[self.idx], self.res)).astype(np.uint64)
        order = np.argsort(cells, kind="stable")
        self.cells = cells[order]
        self.order = self.idx[order]

    def _lookup(self, cells):
        cells = np.asarray(cells, np.uint64)
        a = np.searchsorted(self.cells, cells, "left")
        b = np.searchsorted(self.cells, cells, "right")
        if len(a) == 0:
            return np.empty(0, np.int64)
        return np.concatenate([self.order[x:y] for x, y in zip(a, b)])

    def _query_points(self, plat, plon):
        import h3

        cands = []
        for la, lo in zip(plat, plon):
            c = h3.latlng_to_cell(la, lo, self.res)
            ring = [h3.str_to_int(x) for x in h3.grid_disk(c, self.k)]
            cands.append(self._lookup(ring))
        return _nearest_among(plat, plon, self.lat_flat, self.lon_flat, cands)

    def _query_polygon(self, poly_b):
        import h3

        ext = [(y, x) for x, y in poly_b.exterior.coords]
        holes = [[(y, x) for x, y in r.coords] for r in poly_b.interiors]
        shape = h3.LatLngPoly(ext, *holes)
        cells = h3.h3shape_to_cells_experimental(shape, self.res, contain="overlap")
        ints = [h3.str_to_int(c) for c in cells]
        return _filter_in_poly(poly_b, self.lat_flat, self.lon_flat, self._lookup(ints))

    def index_nbytes(self):
        return self.cells.nbytes + self.order.nbytes


# ---------------------------------------------------------------------------------------
# analytic (orbit + scan geometry), see analytic.py


class AnalyticLocator(Locator):
    """No index: predict (line, sample) from orbit/scan geometry, then search a small
    scan-aware window of the real lat/lon. `build` = assemble per-scan navigation (kB).

    Polygon: predict the (line, sample) of the densified, buffered polygon boundary in every
    candidate scan, take the bounding window (+ margin) and test pixel centres inside it.
    """

    def __init__(self, swath, model, half_line=1, half_samp=1, height=0.0):
        self.sw, self.model = swath, model
        self.hl, self.hs, self.height = half_line, half_samp, height
        self.name = "analytic"

    def _build(self):
        from . import analytic

        self.nav = analytic.scan_nav(self.sw, self.model)

    def _query_points(self, plat, plon):
        from . import analytic

        pred = analytic.predict(self.sw, plat, plon, self.model, self.nav, height=self.height)
        r, c, d, self.last_nread = analytic.refine(self.sw, plat, plon, pred, self.hl, self.hs, self.model.n_det)
        flat = np.where(r >= 0, r * self.shape[1] + c, -1)
        return flat, d

    def _query_polygon(self, poly_b):
        from . import analytic

        ring = shapely.segmentize(poly_b.exterior, max_segment_length=0.01)  # ~1 km in degrees
        xs, ys = np.asarray(ring.xy)
        pred = analytic.predict(self.sw, ys, xs, self.model, self.nav, height=self.height)
        nd = self.model.n_det
        ok = (pred.cand_d >= -0.5 - self.hl) & (pred.cand_d <= nd - 0.5 + self.hl)
        lines = pred.cand_line[ok]
        samps = pred.cand_samp[ok]
        if lines.size == 0:
            return np.empty(0, np.int64)
        nl, ns = self.shape
        r0 = int(max(np.floor(np.nanmin(lines)) - self.hl - nd, 0))
        r1 = int(min(np.ceil(np.nanmax(lines)) + self.hl + nd + 1, nl))
        c0 = int(max(np.floor(np.nanmin(samps)) - self.hs - 1, 0))
        c1 = int(min(np.ceil(np.nanmax(samps)) + self.hs + 2, ns))
        rr, cc = np.mgrid[r0:r1, c0:c1]
        cand = (rr * ns + cc).ravel()
        self.last_nread = cand.size
        cand = cand[np.isfinite(self.lat_flat[cand])]
        return _filter_in_poly(poly_b, self.lat_flat, self.lon_flat, cand)


# ---------------------------------------------------------------------------------------
# per-sensor default parameters (index resolution matched to the largest pixel)

# S2 level / H3 resolution whose cells are >= the largest pixel spacing, so that the true
# nearest pixel always lies in the target cell or its immediate neighbours.
S2_LEVEL = {"modis": 10, "viirs": 11, "ecostress": 15}
H3_RES = {"modis": 5, "viirs": 6, "ecostress": 9}
BBOX_DEG = {"modis": 0.08, "viirs": 0.03, "ecostress": 0.003}
# largest pixel half-diagonal (m) used to grow polygons for candidate search
POLY_BUFFER_M = {"modis": 3500.0, "viirs": 1300.0, "ecostress": 80.0}


def all_locators(sensor: str):
    return [
        NaiveFull(),
        NaiveBBox(BBOX_DEG[sensor]),
        ScipyKDTree(),
        PyKDTree(),
        XarrayNDPoint("scipy_degrees"),
        XarrayNDPoint("xoak_geoballtree"),
        XarrayNDPoint("xoak_s2"),
        S2PointIndexLoc(),
        S2SortedIndex(S2_LEVEL[sensor]),
        H3SortedIndex(H3_RES[sensor]),
    ]
