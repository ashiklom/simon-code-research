"""Analytic inverse geolocation: (lat, lon) -> (line, sample) from orbit + scan geometry.

No lat/lon index is needed: only the per-scan spacecraft state (a few kB of metadata) and a
handful of instrument constants. Optionally, the guess is refined by reading a small k x k
window of the real lat/lon arrays around it.

Model (all three sensors are cross-track scanners whose line of sight (LOS) rotates about an
axis close to the along-track direction):

  frame    x = along-track, y = cross-track, z = nadir. MODIS: the per-scan instrument->ECR
           matrix shipped in MOD03 (`T_inst2ECR`). VIIRS/ECOSTRESS: an orbital frame built from
           ECEF position and *inertial* velocity (v_ecef + omega_E x r; using the Earth-fixed
           velocity would yaw the frame by ~3.5 deg at the equator => tens of km at swath edge),
           optionally rotated by small calibrated roll/pitch/yaw angles.
  LOS      u = (T - S(t)) / |T - S(t)|, expressed in that frame.
  angles   scan angle theta = atan2(u_y, u_z); along-track angle phi = asin(u_x).
  timing   the sample at scan angle theta is observed at t_scan + kappa * theta, so S is
           interpolated to that time (MODIS: ~0.45 s across the Earth view => ~3 km).
  sample   MODIS/ECOSTRESS: j = j_c + s * theta / alpha (linear).
           VIIRS: native index n = n_c + s * theta / alpha, then aggregated through the
           1:1 / 2:1 / 3:1 / 2:1 / 1:1 on-board aggregation zones (640/368/1184/368/640 samples).
  detector d = d_c + (phi - phi0) / delta; line = scan * N_det + d. A target lies in scan k if
           d is within the detector array; with bow-tie overlap (MODIS) several scans qualify
           and the one whose array centre is closest is chosen.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from . import geom

OMEGA_E = 7.2921159e-5  # rad/s

# VIIRS M-band aggregation zones: (n aggregated samples, aggregation factor), edge->nadir->edge
VIIRS_ZONES = [(640, 1), (368, 2), (1184, 3), (368, 2), (640, 1)]


def _viirs_tables():
    agg_edges = np.cumsum([0] + [n for n, _ in VIIRS_ZONES])  # aggregated sample boundaries
    nat_edges = np.cumsum([0] + [n * f for n, f in VIIRS_ZONES])  # native sample boundaries
    return agg_edges.astype(float), nat_edges.astype(float)


VIIRS_AGG_EDGES, VIIRS_NAT_EDGES = _viirs_tables()  # 0..3200, 0..6304


def viirs_native_to_agg(n):
    """Fractional native sample (0..6304) -> fractional aggregated sample (0..3200)."""
    return np.interp(n, VIIRS_NAT_EDGES, VIIRS_AGG_EDGES, left=np.nan, right=np.nan)


def viirs_agg_to_native(j):
    return np.interp(j, VIIRS_AGG_EDGES, VIIRS_NAT_EDGES)


@dataclass(frozen=True)
class SensorModel:
    sensor: str
    n_det: int  # lines per scan
    n_samp: int  # samples per line (aggregated for VIIRS)
    alpha: float  # rad per (native) sample along-scan
    j_c: float  # (native) sample index at theta = 0
    s: float  # +1/-1: sign of d(sample)/d(theta)
    delta: float  # rad per detector along-track
    d_c: float  # detector index at phi = phi0
    phi0: float  # along-track angle of the array centre (rad)
    kappa: float  # s per rad of scan angle (time offset of a sample relative to scan time)
    t_off: float = 0.0  # s: Earth-view centre time minus the scan reference time
    rpy: tuple = (0.0, 0.0, 0.0)  # extra frame rotation (orbital-frame sensors), rad
    frame: str = "orbital"  # "inst" (MODIS T_inst2ECR), "attitude" (ECOSTRESS quaternions), "orbital"
    nadir: str = "geodetic"  # orbital frame z: "geodetic" (ellipsoid normal) or "geocentric"
    note: str = ""

    def theta_to_sample(self, theta):
        n = self.j_c + self.s * theta / self.alpha
        if self.sensor == "viirs":
            return viirs_native_to_agg(n)
        return n

    def sample_to_theta(self, j):
        n = viirs_agg_to_native(j) if self.sensor == "viirs" else j
        return (n - self.j_c) * self.s * self.alpha


# "Spec" models: constants straight from instrument documentation (see config/sensors.toml and
# the methods page for sources). phi0/j_c are nominal array/scan centres.
SPEC = {
    "modis": SensorModel(
        "modis", n_det=10, n_samp=1354, alpha=1.41844e-3, j_c=676.5, s=-1.0,
        delta=1.41844e-3, d_c=4.5, phi0=0.0, kappa=1.0 / 4.2546, frame="inst",
        note="MOD03 ATBD: 1 km IFOV = 1.418 mrad, 1354 frames, +-55 deg, 20.3 rpm two-sided mirror"),
    "viirs": SensorModel(
        "viirs", n_det=16, n_samp=3200, alpha=np.radians(112.12) / 6304, j_c=3151.5, s=-1.0,
        delta=0.742 / 829.0, d_c=7.5, phi0=0.0, kappa=1.7864 / (2 * np.pi), frame="orbital",
        note="VIIRS SDR/GEO ATBD: 6304 native M samples over +-56.06 deg, 1.7864 s scan, 16 detectors 742 m @ 829 km"),
    "ecostress": SensorModel(
        "ecostress", n_det=128, n_samp=5400, alpha=np.radians(51.0) / 5400, j_c=2699.5, s=-1.0,
        delta=68.754 / 400e3, d_c=63.5, phi0=0.0, kappa=1.0 / (2 * 2 * np.pi * 25.4 / 60), frame="attitude",
        note="ECOSTRESS L1 ATBD: +-25.5 deg, 5400 samples, 25.4 rpm two-sided mirror, 44 scans x 128 lines"),
}


def _rot(rpy):
    r, p, y = rpy
    cr, sr, cp, sp, cy, sy = np.cos(r), np.sin(r), np.cos(p), np.sin(p), np.cos(y), np.sin(y)
    rx = np.array([[1, 0, 0], [0, cr, -sr], [0, sr, cr]])
    ry = np.array([[cp, 0, sp], [0, 1, 0], [-sp, 0, cp]])
    rz = np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]])
    return rz @ ry @ rx


@dataclass
class ScanNav:
    """Per-scan state used by the model: time, ECEF pos/vel, frame matrix (3x3, columns = x,y,z)."""

    t: np.ndarray
    pos: np.ndarray
    vel: np.ndarray
    frames: np.ndarray  # (n_scan, 3, 3) frame -> ECEF (columns are frame axes in ECEF)

    def interp(self, k, dt):
        """Position at scan k (int array) + dt seconds (linear in time across scans)."""
        p = self.pos[k] + self.vel[k] * dt[..., None]
        return p


def orbital_frames(pos, vel, nadir="geodetic"):
    vin = vel + np.cross(np.array([0.0, 0.0, OMEGA_E]), pos)  # inertial velocity, in ECEF axes
    if nadir == "geodetic":
        la, lo, _ = geom.ecef_to_lla(pos)
        z = -geom.unit_xyz(la, lo)
    else:
        z = -pos / np.linalg.norm(pos, axis=-1, keepdims=True)
    x = vin - (vin * z).sum(-1, keepdims=True) * z
    x /= np.linalg.norm(x, axis=-1, keepdims=True)
    y = np.cross(z, x)
    return np.stack([x, y, z], axis=-1)


def scan_nav(sw, model: SensorModel) -> ScanNav:
    """Spacecraft state at each scan's centre time."""
    n = sw.nav
    if sw.sensor in ("modis", "viirs"):
        t, pos, vel = n.time, n.pos, n.vel
        ok = np.isfinite(pos).all(1) & np.isfinite(t)
        if not ok.all():  # fill bad scans by interpolation in time index
            idx = np.arange(len(t))
            for a in (t,):
                a[~ok] = np.interp(idx[~ok], idx[ok], a[ok])
            for arr in (pos, vel):
                for c in range(3):
                    arr[~ok, c] = np.interp(idx[~ok], idx[ok], arr[ok, c])
        if model.frame == "inst" and n.t_inst2ecr is not None:
            fr = n.t_inst2ecr.copy()
            bad = ~np.isfinite(fr).all((1, 2))
            if bad.any():
                good = np.where(~bad)[0]
                fr[bad] = fr[good[np.abs(good[None, :] - np.where(bad)[0][:, None]).argmin(1)]]
        else:
            fr = orbital_frames(pos, vel, model.nadir)
    else:  # ECOSTRESS: ephemeris at 1 Hz, scans = groups of n_det lines
        t = sw.line_time[:: model.n_det]  # scan start times; EV-centre offset = model.t_off
        pos = np.stack([np.interp(t, n.time, n.pos[:, c]) for c in range(3)], -1)
        vel = np.stack([np.interp(t, n.time, n.vel[:, c]) for c in range(3)], -1)
        if model.frame == "attitude" and n.body2ecef is not None:
            fr = np.stack([np.stack([np.interp(t, n.att_time, n.body2ecef[:, i, j]) for j in range(3)], -1)
                           for i in range(3)], -2)
            u_, _, vt = np.linalg.svd(fr)  # re-orthonormalise after interpolation
            fr = u_ @ vt
        else:
            fr = orbital_frames(pos, vel, model.nadir)
    if any(model.rpy):
        fr = fr @ _rot(model.rpy)
    return ScanNav(np.asarray(t, float), np.asarray(pos, float), np.asarray(vel, float), fr)


def _angles(T, S, F):
    """LOS angles of targets T (.., 3) from S (.., 3) in frames F (.., 3, 3)."""
    u = T - S
    u /= np.linalg.norm(u, axis=-1, keepdims=True)
    uf = np.einsum("...ij,...i->...j", F, u)  # components along frame axes
    theta = np.arctan2(uf[..., 1], uf[..., 2])
    phi = np.arcsin(np.clip(uf[..., 0], -1, 1))
    return theta, phi


def scan_angles(T, ks, model: SensorModel, nav: ScanNav):
    """Fractional detector index d and sample j of targets T (.., 3) w.r.t. scans ks (..)."""
    F = nav.frames[ks]
    theta, _ = _angles(T, nav.pos[ks], F)
    for _ in range(2):  # account for spacecraft motion within the scan
        S = nav.interp(ks, model.t_off + model.s * model.kappa * theta)
        theta, phi = _angles(T, S, F)
    d = model.d_c + (phi - model.phi0) / model.delta
    j = model.theta_to_sample(theta)
    return d, j


@dataclass
class Prediction:
    line: np.ndarray  # (m,) best fractional line
    samp: np.ndarray  # (m,) best fractional sample
    in_swath: np.ndarray  # (m,) bool
    cand_line: np.ndarray  # (m, n_cand) fractional line for each candidate scan
    cand_samp: np.ndarray  # (m, n_cand)
    cand_d: np.ndarray  # (m, n_cand) detector index within the candidate scan


def predict(sw, lat, lon, model: SensorModel | None = None, nav: ScanNav | None = None,
            height=0.0, n_cand: int = 3) -> Prediction:
    """Predict fractional (line, sample) of targets from orbit + scan geometry only."""
    model = model or SPEC[sw.sensor]
    nav = nav or scan_nav(sw, model)
    lat = np.atleast_1d(np.asarray(lat, float))
    lon = np.atleast_1d(np.asarray(lon, float))
    T = geom.lla_to_ecef(lat, lon, height)  # (m, 3)
    # coarse: along-track angle wrt every scan centre (m x n_scan) -> nearest scans
    _, phi_all = _angles(T[:, None, :], nav.pos[None], nav.frames[None])
    k0 = np.abs(phi_all - model.phi0).argmin(1)
    ks = np.clip(k0[:, None] + np.arange(-(n_cand // 2), n_cand // 2 + 1)[None], 0, len(nav.t) - 1)
    Tk = np.broadcast_to(T[:, None, :], ks.shape + (3,))
    d, j = scan_angles(Tk, ks, model, nav)
    # choose the scan whose detector-array centre is closest (bow-tie / scan overlap)
    best = np.abs(d - model.d_c).argmin(1)
    r = np.arange(len(lat))
    dd, jj = d[r, best], j[r, best]
    line = ks[r, best] * model.n_det + dd
    n_lines = len(nav.t) * model.n_det
    in_swath = np.isfinite(jj) & (jj >= -0.5) & (jj <= model.n_samp - 0.5) & (line >= -0.5) & (line <= n_lines - 0.5)
    in_swath &= np.abs(dd - model.d_c) <= model.n_det / 2 + 0.5
    return Prediction(line, jj, in_swath, ks * model.n_det + d, j, d)


def refine(sw, lat, lon, pred: Prediction, half_line: int, half_samp: int, n_det: int,
           all_scans: bool = True):
    """Nearest pixel among windows around the predicted pixel in each candidate scan.

    Window = (2*half_line+1) x (2*half_samp+1) pixels, clipped to the candidate scan's own
    lines when `all_scans` (scan-aware: each overlapping scan gets its own small window).
    Returns rows, cols, dist_m, n_pixels_read.
    """
    nl, ns = sw.lat.shape
    m = len(lat)
    out_r = np.full(m, -1)
    out_c = np.full(m, -1)
    dist = np.full(m, np.nan)
    nread = np.zeros(m, int)
    for i in range(m):
        best = (np.inf, -1, -1)
        cands = range(pred.cand_line.shape[1]) if all_scans else [None]
        for c in cands:
            if c is None:
                l, s_ = pred.line[i], pred.samp[i]
            else:
                l, s_ = pred.cand_line[i, c], pred.cand_samp[i, c]
                d = pred.cand_d[i, c]
                if not (np.isfinite(d) and -0.5 - half_line <= d <= n_det - 0.5 + half_line):
                    continue
            if not (np.isfinite(l) and np.isfinite(s_)):
                continue
            l0, s0 = int(round(l)), int(round(s_))
            r0, r1 = max(l0 - half_line, 0), min(l0 + half_line + 1, nl)
            if c is not None:  # stay inside the candidate scan
                k = int(np.floor((l0 if l0 >= 0 else 0) / n_det))
                k = int(round((l - pred.cand_d[i, c]) / n_det))
                r0, r1 = max(r0, k * n_det), min(r1, (k + 1) * n_det)
            c0, c1 = max(s0 - half_samp, 0), min(s0 + half_samp + 1, ns)
            if r0 >= r1 or c0 >= c1:
                continue
            wl, wo = sw.lat[r0:r1, c0:c1], sw.lon[r0:r1, c0:c1]
            nread[i] += wl.size
            dd = geom.haversine_m(lat[i], lon[i], wl, wo)
            if not np.isfinite(dd).any():
                continue
            kk = np.nanargmin(dd)
            rr, cc = np.unravel_index(kk, dd.shape)
            if dd[rr, cc] < best[0]:
                best = (dd[rr, cc], r0 + rr, c0 + cc)
        if best[1] >= 0:
            dist[i], out_r[i], out_c[i] = best
    return out_r, out_c, dist, nread


# --- calibration ----------------------------------------------------------------------


def sample_pixels(sw, n=3000, seed=0, margin=2):
    rng = np.random.default_rng(seed)
    nl, ns = sw.lat.shape
    rows = rng.integers(margin, nl - margin, n)
    cols = rng.integers(margin, ns - margin, n)
    ok = np.isfinite(sw.lat[rows, cols]) & np.isfinite(sw.lon[rows, cols])
    return rows[ok], cols[ok]


def own_scan_residuals(sw, rows, cols, model, height=0.0, nav=None):
    """(d - detector, j - sample) of pixel centres w.r.t. their *own* scan."""
    nav = nav or scan_nav(sw, model)
    T = geom.lla_to_ecef(sw.lat[rows, cols], sw.lon[rows, cols], height)
    k = rows // model.n_det
    d, j = scan_angles(T, k, model, nav)
    return d - rows % model.n_det, j - cols


def calibrate(sw, base: SensorModel | None = None, n=3000, seed=0, fit_rpy=None, use_height=True):
    """Fit model constants (j_c, alpha, phi0, delta, kappa, t_off, [pitch, yaw]) to one granule.

    Pixel centres with known (scan, detector, sample) are pushed through the forward angles
    w.r.t. their own scan; constants minimise pixel-unit residuals (robust loss).
    """
    from scipy.optimize import least_squares

    base = base or SPEC[sw.sensor]
    fit_rpy = (base.frame != "inst") if fit_rpy is None else fit_rpy
    rows, cols = sample_pixels(sw, n, seed)
    hgt = sw.height[rows, cols] if (use_height and sw.height is not None) else 0.0
    hgt = np.nan_to_num(hgt)
    nav0 = scan_nav(sw, replace(base, rpy=(0.0, 0.0, 0.0)))

    # roll is degenerate with j_c (both shift theta), so only pitch and yaw are fitted
    def make(p):
        rpy = (0.0, p[6] * 1e-3, p[7] * 1e-3) if fit_rpy else base.rpy
        return replace(base, j_c=p[0], alpha=abs(p[1]) * 1e-3, phi0=p[2] * 1e-3, delta=abs(p[3]) * 1e-3,
                       kappa=p[4], t_off=p[5], rpy=rpy)

    def resid(p):
        m = make(p)
        nav = nav0
        if any(m.rpy):
            nav = ScanNav(nav0.t, nav0.pos, nav0.vel, nav0.frames @ _rot(m.rpy))
        r1, r2 = own_scan_residuals(sw, rows, cols, m, hgt, nav)
        out = np.concatenate([r1, r2])
        return np.where(np.isfinite(out), out, 50.0)

    p0 = np.array([base.j_c, base.alpha * 1e3, base.phi0 * 1e3, base.delta * 1e3, base.kappa, base.t_off,
                   *(np.array(base.rpy[1:]) * 1e3)])
    if not fit_rpy:
        p0 = p0[:6]
    res = least_squares(resid, p0, loss="soft_l1", f_scale=1.0, x_scale="jac")
    if not fit_rpy:
        res.x = np.r_[res.x, np.array(base.rpy[1:]) * 1e3]
    return make(res.x), res
