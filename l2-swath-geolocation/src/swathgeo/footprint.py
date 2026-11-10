"""Pixel footprints from view geometry (spherical-Earth trigonometry) + Voronoi cells.

For a cross-track scanner with angular sample width alpha (along-scan) and delta
(along-track), at scan angle theta from a satellite at geocentric radius R+h:

    view zenith      eta   = asin((R+h)/R * sin(theta))
    Earth angle      beta  = eta - theta
    slant range      r     = (R+h) cos(theta) - sqrt(R^2 - (R+h)^2 sin^2(theta))
    along-scan size  W_s   = r * alpha / cos(eta)        (= R * d(beta)/d(theta) * alpha)
    along-track size W_t   = r * delta

For real pixels we use the product's own view zenith (vza) and the satellite radius from the
navigation data: r = sqrt(Rs^2 - R^2 sin^2(vza)) - R cos(vza), which includes terrain-free
Earth curvature exactly. VIIRS' along-scan alpha is the native sample angle times the on-board
aggregation factor of the pixel's zone (3, 2 or 1).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, fields

import numpy as np
import shapely

from . import analytic as an
from . import config, geom

R_EARTH = 6371008.8


def load_models() -> dict[str, an.SensorModel]:
    raw = json.loads((config.RESULTS / "analytic_models.json").read_text())
    out = {}
    for k, v in raw.items():
        kw = {f.name: v[f.name] for f in fields(an.SensorModel) if f.name in v}
        kw["rpy"] = tuple(kw["rpy"])
        out[k] = an.SensorModel(**kw)
    return out


PLATFORM = {"MOD": "Terra", "MYD": "Aqua", "VNP": "SNPP", "VJ1": "NOAA-20", "ECO": "ISS"}


def platform_of(sw) -> str:
    return PLATFORM[sw.geo_path.name[:3]]


def viirs_agg_factor(cols):
    edges = an.VIIRS_AGG_EDGES
    facs = np.array([f for _, f in an.VIIRS_ZONES])
    z = np.clip(np.searchsorted(edges, cols, side="right") - 1, 0, len(facs) - 1)
    return facs[z]


def angular_widths(sensor: str, model: an.SensorModel, cols):
    """(alpha_eff, delta) in radians for pixels in columns `cols`."""
    cols = np.asarray(cols)
    if sensor == "viirs":
        a = model.alpha * viirs_agg_factor(cols)
    else:
        a = np.full(cols.shape, model.alpha)
    return a, np.full(cols.shape, model.delta)


# --- closed-form model (for plots / interactive explainer) ----------------------------


def theory(theta, h, alpha, delta, R=R_EARTH):
    """Footprint sizes (m) vs scan angle theta (rad) for altitude h (m)."""
    Rs = R + h
    s = Rs / R * np.sin(theta)
    eta = np.arcsin(np.clip(s, -1, 1))
    r = Rs * np.cos(theta) - np.sqrt(np.maximum(R**2 - Rs**2 * np.sin(theta) ** 2, 0))
    return {"vza": np.degrees(eta), "range": r, "W_s": r * alpha / np.cos(eta), "W_t": r * delta,
            "earth_angle": np.degrees(eta - theta)}


# --- per-pixel geometry ---------------------------------------------------------------


@dataclass
class PixelGeom:
    rows: np.ndarray
    cols: np.ndarray
    lat: np.ndarray
    lon: np.ndarray
    x: np.ndarray  # local LAEA metres
    y: np.ndarray
    e_s: np.ndarray  # (n, 2) unit vector along increasing sample (scan direction), local plane
    e_t: np.ndarray  # (n, 2) unit vector along-track (perpendicular to e_s, towards increasing line)
    W_s: np.ndarray  # m
    W_t: np.ndarray  # m
    vza: np.ndarray
    range_m: np.ndarray
    origin: tuple  # (lat0, lon0) of the local projection

    @property
    def area(self):
        return self.W_s * self.W_t

    def corners(self):
        """(n, 4, 2) quadrilateral corners in local metres."""
        hs = (0.5 * self.W_s)[:, None] * self.e_s
        ht = (0.5 * self.W_t)[:, None] * self.e_t
        c = np.stack([self.x, self.y], -1)
        return np.stack([c - hs - ht, c + hs - ht, c + hs + ht, c - hs + ht], 1)


def satellite_radius(sw) -> float:
    return float(np.nanmedian(np.linalg.norm(sw.nav.pos, axis=-1)))


def pixel_geometry(sw, rows, cols, origin, model: an.SensorModel | None = None) -> PixelGeom:
    rows = np.asarray(rows)
    cols = np.asarray(cols)
    model = model or load_models()[platform_of(sw)]
    tr = geom.local_laea(*origin)
    nl, ns = sw.shape
    lat, lon = sw.lat[rows, cols], sw.lon[rows, cols]
    x, y = tr.transform(lon, lat)
    # scan direction from neighbouring samples (central difference, same line)
    c0, c1 = np.clip(cols - 1, 0, ns - 1), np.clip(cols + 1, 0, ns - 1)
    xa, ya = tr.transform(sw.lon[rows, c0], sw.lat[rows, c0])
    xb, yb = tr.transform(sw.lon[rows, c1], sw.lat[rows, c1])
    e_s = np.stack([xb - xa, yb - ya], -1)
    e_s /= np.linalg.norm(e_s, axis=-1, keepdims=True)
    # along-track: perpendicular, oriented towards increasing line within the scan
    e_t = np.stack([-e_s[:, 1], e_s[:, 0]], -1)
    nd = sw.lines_per_scan
    r1 = np.where(rows % nd < nd - 1, rows + 1, rows - 1)
    sgn = np.where(rows % nd < nd - 1, 1.0, -1.0)
    xn, yn = tr.transform(sw.lon[r1, cols], sw.lat[r1, cols])
    dot = ((np.stack([xn - x, yn - y], -1) * e_t).sum(-1)) * sgn
    e_t *= np.where(dot < 0, -1.0, 1.0)[:, None]
    vza = np.radians(sw.vza[rows, cols])
    Rs = satellite_radius(sw)
    Rl = np.linalg.norm(geom.lla_to_ecef(lat, lon, 0.0), axis=-1)
    rng = np.sqrt(Rs**2 - Rl**2 * np.sin(vza) ** 2) - Rl * np.cos(vza)
    a, d = angular_widths(sw.sensor, model, cols)
    W_s = rng * a / np.cos(vza)
    W_t = rng * d
    return PixelGeom(rows, cols, lat, lon, np.asarray(x), np.asarray(y), e_s, e_t, W_s, W_t,
                     np.degrees(vza), rng, origin)


def empirical_spacing(sw, rows, cols, origin):
    """Distance (m) between neighbouring centres along sample and along line (same scan)."""
    tr = geom.local_laea(*origin)
    nl, ns = sw.shape
    nd = sw.lines_per_scan
    c0, c1 = np.clip(cols - 1, 0, ns - 1), np.clip(cols + 1, 0, ns - 1)
    xa, ya = tr.transform(sw.lon[rows, c0], sw.lat[rows, c0])
    xb, yb = tr.transform(sw.lon[rows, c1], sw.lat[rows, c1])
    ds = np.hypot(xb - xa, yb - ya) / (c1 - c0)
    r0 = rows - rows % nd
    ra = np.clip(rows - 1, r0, r0 + nd - 1)
    rb = np.clip(rows + 1, r0, r0 + nd - 1)
    xa, ya = tr.transform(sw.lon[ra, cols], sw.lat[ra, cols])
    xb, yb = tr.transform(sw.lon[rb, cols], sw.lat[rb, cols])
    dt = np.hypot(xb - xa, yb - ya) / np.maximum(rb - ra, 1)
    return ds, dt


# --- vector export --------------------------------------------------------------------


def to_lonlat(pg: PixelGeom, xy):
    tr = geom.local_laea(*pg.origin)
    lon, lat = tr.transform(xy[..., 0], xy[..., 1], direction="INVERSE")
    return np.stack([lon, lat], -1)


def footprint_polygons(pg: PixelGeom, kind="model", nominal_m=None):
    """Shapely polygons (lon/lat) per pixel: 'model' (oriented trig footprint) or
    'nominal' (square of side nominal_m, the all-pixels-same-size assumption)."""
    if kind == "model":
        corners = pg.corners()
    else:
        h = nominal_m / 2
        c = np.stack([pg.x, pg.y], -1)[:, None, :]
        corners = c + np.array([[-h, -h], [h, -h], [h, h], [-h, h]])[None]
    ll = to_lonlat(pg, corners)
    return shapely.polygons(np.concatenate([ll, ll[:, :1]], 1))


def local_polygons(pg: PixelGeom, kind="model", nominal_m=None):
    if kind == "model":
        corners = pg.corners()
    else:
        h = nominal_m / 2
        c = np.stack([pg.x, pg.y], -1)[:, None, :]
        corners = c + np.array([[-h, -h], [h, -h], [h, h], [-h, h]])[None]
    return shapely.polygons(np.concatenate([corners, corners[:, :1]], 1))


def voronoi_cells(pg: PixelGeom, clip=None):
    """Planar Voronoi cells (local metres) of the pixel centres, in input order.

    Cells are the regions closest to each centre, i.e. exactly what nearest-neighbour
    extraction implicitly assigns to a pixel. Duplicate centres (rare) get an empty cell.
    """
    pts = shapely.multipoints(np.stack([pg.x, pg.y], -1))
    env = shapely.box(pg.x.min() - 1e4, pg.y.min() - 1e4, pg.x.max() + 1e4, pg.y.max() + 1e4)
    vor = shapely.voronoi_polygons(pts, extend_to=env)
    cells = np.asarray(shapely.get_parts(vor))
    # map cells back to points
    tree = shapely.STRtree(cells)
    pidx, cidx = tree.query(shapely.points(np.stack([pg.x, pg.y], -1)), predicate="within")
    out = np.full(len(pg.x), None, dtype=object)
    out[pidx] = cells[cidx]
    empty = shapely.Polygon()
    out = np.array([c if c is not None else empty for c in out], dtype=object)
    if clip is not None:
        out = shapely.intersection(out, clip)
    return out
