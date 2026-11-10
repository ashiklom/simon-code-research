"""Benchmark pixel locators on the main scenes and the three target types.

Each (scene, locator) runs in a fresh subprocess (clean memory accounting). Timed separately:
geolocation load, index build, query (site, 100 points, each polygon). Correctness is checked
against the brute-force answer (naive_full; points) and the scipy KD-tree (polygons).

Output: results/locate_bench.csv, results/locate_results.parquet (per-target answers)
Usage:  python scripts/10_bench_locate.py [scene ...]
"""

from __future__ import annotations

import json
import multiprocessing as mp
import sys
import time
from dataclasses import fields

import numpy as np
import pandas as pd

from swathgeo import config

LOCATORS = ["naive_full", "naive_bbox", "kdtree_scipy", "kdtree_pykdtree", "xarray_sel_default",
            "xarray_ndpoint_scipy_degrees", "xarray_ndpoint_xoak_geoballtree", "xarray_ndpoint_xoak_s2",
            "s2_pys2index", "s2_sorted", "h3_sorted", "analytic"]
PLATFORM = {"MOD": "Terra", "MYD": "Aqua", "VNP": "SNPP", "VJ1": "NOAA-20", "ECO": "ISS"}


def timeit(fn, reps, budget_s=20.0):
    """Median wall time over reps (fewer reps if a single call is slow). Returns (t, result)."""
    ts, out = [], None
    for _ in range(reps):
        t = time.perf_counter()
        out = fn()
        ts.append(time.perf_counter() - t)
        if sum(ts) > budget_s:
            break
    return float(np.median(ts)), len(ts), out


def make_locator(name, sw):
    from swathgeo import analytic as an
    from swathgeo import locate as L

    s = sw.sensor
    if name == "naive_full":
        return L.NaiveFull()
    if name == "naive_bbox":
        return L.NaiveBBox(L.BBOX_DEG[s])
    if name == "kdtree_scipy":
        return L.ScipyKDTree()
    if name == "kdtree_pykdtree":
        return L.PyKDTree()
    if name == "xarray_sel_default":
        return L.XarrayNaiveSel()
    if name.startswith("xarray_ndpoint_"):
        return L.XarrayNDPoint(name.removeprefix("xarray_ndpoint_"))
    if name == "s2_pys2index":
        return L.S2PointIndexLoc()
    if name == "s2_sorted":
        return L.S2SortedIndex(L.S2_LEVEL[s])
    if name == "h3_sorted":
        return L.H3SortedIndex(L.H3_RES[s])
    if name == "analytic":
        models = json.loads((config.RESULTS / "analytic_models.json").read_text())
        plat = PLATFORM[sw.geo_path.name[:3]]
        kw = {f.name: models[plat][f.name] for f in fields(an.SensorModel) if f.name in models[plat]}
        kw["rpy"] = tuple(kw["rpy"])
        model = an.SensorModel(**kw)
        win = json.loads((config.RESULTS / "analytic_window.json").read_text())[plat] \
            if (config.RESULTS / "analytic_window.json").exists() else 3
        return L.AnalyticLocator(sw, model, half_line=win, half_samp=win, height=0.0)
    raise KeyError(name)


def worker(scene, name, q):
    import geopandas as gpd
    import psutil

    from swathgeo import io

    proc = psutil.Process()
    rec = {"scene": scene, "locator": name}
    try:
        t = time.perf_counter()
        sw = io.read_scene(scene, nav=(name == "analytic"), lst=False)
        rec["load_s"] = time.perf_counter() - t
        rec["n_pixels"] = int(np.isfinite(sw.lat).sum())
        rec["sensor"] = sw.sensor
        rss0 = proc.memory_info().rss
        loc = make_locator(name, sw)
        rec["build_s"], rec["build_reps"], _ = timeit(lambda: loc.build(sw.lat, sw.lon), 3, budget_s=30)
        rec["index_mb"] = (proc.memory_info().rss - rss0) / 2**20
        site = gpd.read_file(config.CONFIG / "targets/site.geojson")
        pts = gpd.read_file(config.CONFIG / "targets/points100.geojson")
        polys = gpd.read_file(config.CONFIG / "targets/polygons.geojson").set_index("name").geometry
        answers = {}
        for tname, g in [("site", site), ("points100", pts)]:
            plat, plon = g.geometry.y.values, g.geometry.x.values
            try:
                tq, n, (r, c, d) = timeit(lambda: loc.query_points(plat, plon), 5, budget_s=30)
                rec[f"q_{tname}_s"], rec[f"q_{tname}_reps"] = tq, n
                answers[tname] = (r.tolist(), c.tolist(), d.tolist())
                if name == "analytic":
                    rec[f"q_{tname}_pixels_read"] = int(np.sum(loc.last_nread))
            except Exception as e:  # noqa: BLE001
                rec[f"q_{tname}_error"] = f"{type(e).__name__}: {e}"[:300]
        from swathgeo import locate as L

        if loc.supports_polygon:
            for pname, poly in polys.items():
                tq, n, (r, c) = timeit(lambda: loc.query_polygon(poly, L.POLY_BUFFER_M[sw.sensor]), 3, budget_s=30)
                rec[f"q_{pname}_s"] = tq
                rec[f"q_{pname}_n"] = len(r)
                answers[pname] = (r.tolist(), c.tolist())
                if name == "analytic":
                    rec[f"q_{pname}_pixels_read"] = int(loc.last_nread)
        rec["peak_rss_mb"] = proc.memory_info().rss / 2**20
        q.put((rec, answers))
    except Exception as e:  # noqa: BLE001
        rec["error"] = f"{type(e).__name__}: {e}"[:300]
        q.put((rec, {}))


def main(scenes):
    ctx = mp.get_context("spawn")
    recs, ans_rows = [], []
    for scene in scenes:
        answers = {}
        for name in LOCATORS:
            q = ctx.Queue()
            p = ctx.Process(target=worker, args=(scene, name, q))
            p.start()
            rec, ans = q.get()
            p.join()
            answers[name] = ans
            recs.append(rec)
            print({k: (round(v, 4) if isinstance(v, float) else v) for k, v in rec.items()}, flush=True)
        # correctness
        truth = answers.get("naive_full", {})
        ktruth = answers.get("kdtree_scipy", {})
        for rec in [r for r in recs if r["scene"] == scene]:
            a = answers.get(rec["locator"], {})
            for tname in ("site", "points100"):
                if tname in a and tname in truth:
                    r, c, d = map(np.asarray, a[tname])
                    tr, tc, td = map(np.asarray, truth[tname])
                    rec[f"{tname}_exact_frac"] = float(((r == tr) & (c == tc)).mean())
                    rec[f"{tname}_max_excess_m"] = float(np.nanmax(d - td))
            for pname in ("box_3km", "circle_10km", "colusa_county"):
                if pname in a and pname in ktruth:
                    s1 = set(zip(*a[pname]))
                    s0 = set(zip(*ktruth[pname]))
                    rec[f"{pname}_same_set"] = s1 == s0
                    rec[f"{pname}_missing"] = len(s0 - s1)
            for tname, v in a.items():
                ans_rows.append({"scene": scene, "locator": rec["locator"], "target": tname,
                                 "rows": v[0], "cols": v[1]})
        pd.DataFrame(recs).to_csv(config.RESULTS / "locate_bench.csv", index=False)
    pd.DataFrame(ans_rows).to_parquet(config.DATA / "locate_answers.parquet")


if __name__ == "__main__":
    main(sys.argv[1:] or list(config.scenes()))
