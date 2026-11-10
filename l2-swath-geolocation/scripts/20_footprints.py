"""Part B: pixel footprints, Voronoi cells, PSFs and their effect on areal averages.

1. Footprint model vs empirical centre spacing along one line of every main scene
   -> results/footprint_validation.csv, results/footprint_theory.csv
2. For each scene x polygon: pixel weights under every scheme (see psf.py) and the
   resulting mean LST -> results/areal_means.csv; per-pixel tables + vector exports for the
   site (results/vectors/*.fgb, *.parquet; full-size exports in data/vectors/).
3. Synthetic truth: the 70 m ECOSTRESS LST field (same day) is "observed" by each
   MODIS/VIIRS scene through its real geometry and PSF; polygon means from each weighting
   scheme are compared with the true polygon mean, over many random polygons
   -> results/synthetic_errors.csv

Usage: python scripts/20_footprints.py [validate] [areal] [synthetic]
"""

from __future__ import annotations

import sys
import time
import tomllib

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from scipy import ndimage
from scipy.spatial import cKDTree

from swathgeo import analytic as an
from swathgeo import config, footprint as fp, geom, io, locate as L, psf as P

RES = config.RESULTS
VEC = RES / "vectors"
VEC_FULL = config.DATA / "vectors"
for d in (VEC, VEC_FULL):
    d.mkdir(parents=True, exist_ok=True)

PSF_CFG = tomllib.loads((config.CONFIG / "psf.toml").read_text())
NOMINAL_M = {"modis": 1000.0, "viirs": 750.0, "ecostress": 70.0}  # "all pixels the same size"
QUAD_K = {"modis": 9, "viirs": 9, "ecostress": 5}
MARGIN_M = {"modis": 12000.0, "viirs": 5000.0, "ecostress": 400.0}  # pixels around A for Σ_j p_j

SCHEMES = ["naive_center", "naive_square", "voronoi", "footprint", "footprint_pou", "psf", "psf_pou"]


def sensor_psf(sensor, cols=None):
    """PSF for a sensor; VIIRS -> ({agg_factor: psf}, per-pixel agg factor)."""
    if sensor == "viirs":
        psfs = {k: {"s": PSF_CFG["viirs"][f"agg{k}"]["along_scan"], "t": PSF_CFG["viirs"][f"agg{k}"]["along_track"]}
                for k in (1, 2, 3)}
        return psfs, (fp.viirs_agg_factor(cols) if cols is not None else None)
    c = PSF_CFG[sensor]
    return {"s": c["along_scan"], "t": c["along_track"]}, None


_scenes: dict = {}


def scene(name):
    if name not in _scenes:
        _scenes.clear()  # keep memory bounded (ECOSTRESS is large)
        sw = io.read_scene(name)
        loc = L.ScipyKDTree().build(sw.lat, sw.lon)
        _scenes[name] = (sw, loc)
    return _scenes[name]


# ---------------------------------------------------------------------------------------
def validate():
    rows_out = []
    models = fp.load_models()
    for name in config.scenes():
        sw, _ = scene(name)
        m = models[fp.platform_of(sw)]
        nl, ns = sw.shape
        r = (nl // 2) // sw.lines_per_scan * sw.lines_per_scan + sw.lines_per_scan // 2
        cols = np.arange(1, ns - 1, max(ns // 400, 1))
        rows = np.full(len(cols), r)
        origin = (float(sw.lat[r, ns // 2]), float(sw.lon[r, ns // 2]))
        pg = fp.pixel_geometry(sw, rows, cols, origin, m)
        es, et = fp.empirical_spacing(sw, rows, cols, origin)
        theta = np.degrees(m.sample_to_theta(cols))
        rows_out.append(pd.DataFrame({"scene": name, "sensor": sw.sensor, "col": cols, "scan_angle": theta,
                                      "vza": pg.vza, "range_km": pg.range_m / 1e3, "W_s": pg.W_s, "W_t": pg.W_t,
                                      "emp_s": es, "emp_t": et}))
        print(name, "max W_s/W_t", pg.W_s.max().round(), pg.W_t.max().round(), flush=True)
    pd.concat(rows_out).to_csv(RES / "footprint_validation.csv", index=False)

    th = []
    for sensor, plat, h in [("modis", "Aqua", 705e3), ("viirs", "NOAA-20", 829e3), ("ecostress", "ISS", 415e3)]:
        m = models[plat]
        tmax = {"modis": 55.0, "viirs": 56.06, "ecostress": 25.5}[sensor]
        theta = np.radians(np.linspace(0, tmax, 200))
        cols = m.theta_to_sample(-theta / m.s) if sensor != "viirs" else None
        if sensor == "viirs":
            n = m.j_c + theta / m.alpha  # native index on one side
            cols = an.viirs_native_to_agg(np.clip(n, 0, 6303.9))
        a, d = fp.angular_widths(sensor, m, np.clip(np.nan_to_num(cols), 0, m.n_samp - 1))
        t = fp.theory(theta, h, a, d)
        th.append(pd.DataFrame({"sensor": sensor, "altitude_km": h / 1e3, "scan_angle": np.degrees(theta),
                                **{k: v for k, v in t.items()}, "alpha_mrad": a * 1e3, "delta_mrad": d * 1e3}))
    pd.concat(th).to_csv(RES / "footprint_theory.csv", index=False)


# ---------------------------------------------------------------------------------------
def subset(sw, loc, poly_ll, margin_m):
    rows, cols = loc.query_polygon(poly_ll, margin_m)
    return rows, cols


def weights_for(sw, poly_ll, rows, cols, origin, schemes=SCHEMES, psf_override=None):
    tr = geom.local_laea(*origin)
    poly_loc = shapely.transform(poly_ll, lambda xy: np.column_stack(tr.transform(xy[:, 0], xy[:, 1])))
    pg = fp.pixel_geometry(sw, rows, cols, origin)
    W = {}
    centers_in = shapely.contains_xy(poly_loc, pg.x, pg.y)
    if "naive_center" in schemes:
        W["naive_center"] = centers_in.astype(float)
    if "naive_square" in schemes:
        W["naive_square"] = P.area_weights(fp.local_polygons(pg, "nominal", NOMINAL_M[sw.sensor]), poly_loc)
    if "voronoi" in schemes:
        cells = fp.voronoi_cells(pg)
        W["voronoi"] = P.area_weights(cells, poly_loc)
    if "footprint" in schemes:
        W["footprint"] = P.area_weights(fp.local_polygons(pg, "model"), poly_loc)
    k = None  # adaptive node count (see psf.psf_weights)
    cf = 1.0 if len(rows) > 50000 else 0.5  # coarser raster for very large subsets (ECOSTRESS county)
    if "footprint_pou" in schemes:
        W["footprint_pou"] = P.psf_weights(pg, poly_loc, P.BOX, k=k, pou=True, cell_factor=cf)
    spsf, grp = psf_override or sensor_psf(sw.sensor, cols)
    if "psf" in schemes:
        W["psf"] = P.psf_weights(pg, poly_loc, spsf, k=k, pou=False, group=grp, cell_factor=cf)
    if "psf_pou" in schemes:
        W["psf_pou"] = P.psf_weights(pg, poly_loc, spsf, k=k, pou=True, group=grp, cell_factor=cf)
    return pg, poly_loc, W


def wmean(x, w):
    ok = np.isfinite(x) & (w > 0)
    return float(np.sum(w[ok] * x[ok]) / np.sum(w[ok])) if ok.any() else np.nan


def areal():
    polys = gpd.read_file(config.CONFIG / "targets/polygons.geojson").set_index("name").geometry
    rows_out = []
    for name in config.scenes():
        sw, loc = scene(name)
        for pname, poly in polys.items():
            t0 = time.time()
            c = poly.centroid
            origin = (c.y, c.x)
            rows, cols = subset(sw, loc, poly, MARGIN_M[sw.sensor])
            pg, poly_loc, W = weights_for(sw, poly, rows, cols, origin)
            lst = sw.lst[rows, cols].astype(float)
            base = {"scene": name, "sensor": sw.sensor, "polygon": pname,
                    "polygon_km2": poly_loc.area / 1e6, "vza_mean": float(np.mean(pg.vza[W["footprint"] > 0])),
                    "n_center_in": int((W["naive_center"] > 0).sum()),
                    "n_touching": int((W["footprint"] > 0).sum()),
                    "n_psf_contrib": int((W["psf_pou"] > 1e-6 * W["psf_pou"].max()).sum()),
                    "valid_frac": float(np.isfinite(lst[W["footprint"] > 0]).mean())}
            for s in SCHEMES:
                base[f"mean_{s}"] = wmean(lst, W[s])
                base[f"sumw_{s}_km2"] = float(W[s].sum() / 1e6) if s != "naive_center" else float(W[s].sum())
            rows_out.append(base)
            print(name, pname, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in base.items()
                                if k.startswith("mean_") or k.startswith("n_")}, f"{time.time() - t0:.1f}s", flush=True)
            export(sw, name, pname, pg, W, lst)
        pd.DataFrame(rows_out).to_csv(RES / "areal_means.csv", index=False)


def export(sw, name, pname, pg, W, lst):
    """Footprint vectors (model quads, nominal squares, Voronoi) with weights as attributes."""
    keep = (W["footprint"] > 0) | (W["psf_pou"] > 1e-4 * max(W["psf_pou"].max(), 1e-12)) | (W["voronoi"] > 0)
    idx = np.flatnonzero(keep)
    if len(idx) == 0:
        return
    sub = P._slice(pg, idx)
    attrs = {"row": sub.rows, "col": sub.cols, "vza": sub.vza.round(2), "W_s_m": sub.W_s.round(1),
             "W_t_m": sub.W_t.round(1), "lst_K": lst[idx].round(2)}
    attrs.update({f"w_{s}": W[s][idx] for s in SCHEMES})
    model = fp.footprint_polygons(sub, "model")
    small = len(idx) < 20000
    outdir = VEC if small else VEC_FULL
    gdf = gpd.GeoDataFrame(attrs, geometry=model, crs=4326)
    gdf.to_file(outdir / f"{name}__{pname}__footprints.fgb", driver="FlatGeobuf")
    if small:
        tr = geom.local_laea(*pg.origin)
        cells = fp.voronoi_cells(pg)[idx]
        cells_ll = shapely.transform(cells, lambda xy: np.column_stack(tr.transform(xy[:, 0], xy[:, 1], direction="INVERSE")))
        gpd.GeoDataFrame(attrs, geometry=cells_ll, crs=4326).to_file(
            outdir / f"{name}__{pname}__voronoi.fgb", driver="FlatGeobuf")


# ---------------------------------------------------------------------------------------
def synthetic(n_poly=60, seed=3):
    """ECOSTRESS 70 m LST as truth; simulate MODIS/VIIRS observations through the PSF."""
    eco, eloc = scene("ecostress")
    T = eco.lst.astype(float)
    bad = ~np.isfinite(T)
    idx = ndimage.distance_transform_edt(bad, return_distances=False, return_indices=True)
    Tf = T[tuple(idx)]  # nearest-valid fill (water / cloud pixels)
    ok = np.isfinite(eco.lat) & np.isfinite(eco.lon)
    etree = cKDTree(geom.unit_xyz(eco.lat[ok], eco.lon[ok]))
    Tflat = Tf[ok]
    badflat = bad[ok]
    common = gpd.read_file(config.CONFIG / "targets/common_footprint.geojson").geometry.iloc[0]

    rng = np.random.default_rng(seed)
    polys = []
    c0 = common.buffer(-0.25)
    minx, miny, maxx, maxy = c0.bounds
    sizes = [2000, 5000, 10000, 20000]
    while len(polys) < n_poly:
        x, y = rng.uniform(minx, maxx), rng.uniform(miny, maxy)
        if not c0.contains(shapely.Point(x, y)):
            continue
        size = sizes[len(polys) % len(sizes)]
        shape = ["square", "circle"][len(polys) // len(sizes) % 2]
        tr = geom.local_aeqd(y, x)
        g = shapely.box(-size / 2, -size / 2, size / 2, size / 2) if shape == "square" else shapely.Point(0, 0).buffer(size / 2)
        g = shapely.transform(g, lambda xy: np.column_stack(tr.transform(xy[:, 0], xy[:, 1], direction="INVERSE")))
        polys.append((len(polys), size, shape, g))

    rows_out = []
    for name in [n for n in config.scenes() if n != "ecostress"]:
        sw, loc = scene(name)
        for pid, size, shape, poly in polys:
            c = poly.centroid
            origin = (c.y, c.x)
            rows, cols = subset(sw, loc, poly, MARGIN_M[sw.sensor])
            pg, poly_loc, W = weights_for(sw, poly, rows, cols, origin)
            # simulate observations: PSF-weighted average of the 70 m truth at dense nodes
            spsf, grp = sensor_psf(sw.sensor, cols)
            psfs = spsf if grp is not None else {0: spsf}
            grp = grp if grp is not None else np.zeros(len(cols), int)
            obs = np.full(len(cols), np.nan)
            trf = geom.local_laea(*origin)
            for g, ps in psfs.items():
                ids = np.flatnonzero(grp == g)
                if len(ids) == 0:
                    continue
                U, V, M = P.quadrature(ps, k=31)
                xy = P.node_xy(P._slice(pg, ids), U, V)
                lon, lat = trf.transform(xy[..., 0], xy[..., 1], direction="INVERSE")
                _, nn = etree.query(geom.unit_xyz(lat.ravel(), lon.ravel()), workers=-1)
                obs[ids] = (Tflat[nn].reshape(lat.shape) * M[None]).sum(1)
            # truth: mean of 70 m pixels with centre inside A
            er, ec = L._buffer_ll(poly, 0).bounds, None
            cand = etree.query_ball_point(geom.unit_xyz(c.y, c.x), 2 * np.sin(size / geom.R_MEAN), workers=-1)
            cand = np.asarray(cand, int)
            elat, elon = eco.lat[ok][cand], eco.lon[ok][cand]
            inside = shapely.contains_xy(poly, elon, elat)
            truth = float(Tflat[cand][inside].mean())
            water = float(badflat[cand][inside].mean())
            rec = {"scene": name, "sensor": sw.sensor, "poly_id": pid, "size_m": size, "shape": shape,
                   "vza_mean": float(np.mean(pg.vza[W["footprint"] > 0])), "truth_K": truth,
                   "truth_std_K": float(Tflat[cand][inside].std()), "filled_frac": water}
            for s in SCHEMES:
                rec[f"err_{s}"] = wmean(obs, W[s]) - truth
            rows_out.append(rec)
        print(name, "done", flush=True)
        pd.DataFrame(rows_out).to_csv(RES / "synthetic_errors.csv", index=False)


if __name__ == "__main__":
    steps = sys.argv[1:] or ["validate", "areal", "synthetic"]
    if "validate" in steps:
        validate()
    if "areal" in steps:
        areal()
    if "synthetic" in steps:
        synthetic()
