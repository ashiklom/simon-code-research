"""How consistent is the analytic (orbit + scan geometry) locator across scenes and years?

1. Per platform, calibrate the model constants on ONE reference scene (geo-only set,
   California, June 2024) -> results/analytic_models.json.
2. Apply (a) documentation ("spec") constants, (b) the reference calibration, and (c) a
   per-scene self-calibration to every geo-only scene + main scene. For random targets
   (pixel centre + up to ~1 px jitter) record the error of the predicted (line, sample)
   relative to the true nearest pixel, with and without terrain height.
3. Derive the refinement half-window that contains the true nearest pixel for 99 / 99.9 /
   100 % of targets.

Outputs: results/analytic_consistency.csv (one row per scene x model x height mode),
         results/analytic_models.json, results/analytic_selfcal_constants.csv
"""

import json
import sys
from dataclasses import asdict

import numpy as np
import pandas as pd

from swathgeo import analytic as an
from swathgeo import config, geom, io

REF = {  # platform -> reference scene location/epoch in geo_scenes.toml
    "Terra": ("california", "2024-06"), "Aqua": ("california", "2024-06"),
    "SNPP": ("california", "2024-06"), "NOAA-20": ("california", "2024-06"),
    "ISS": ("california", "2024-06"),
}
N_TARGETS = 2000

geo_scenes = config.load_toml("geo_scenes.toml")["scene"]


def geo_path(s):
    return config.RAW / "geo_only" / s["sensor"] / s["url"].rsplit("/", 1)[-1]


def att_path(s):
    return config.RAW / "geo_only" / s["sensor"] / s["att"].rsplit("/", 1)[-1] if s.get("att") else None


def load(s):
    if s["sensor"] == "ecostress":
        return io.read_ecostress_geo(geo_path(s), att_path=att_path(s))
    return io.read_geo(geo_path(s))


def platform_of(sw, s=None):
    if s is not None:
        return s["platform"]
    n = sw.geo_path.name
    return {"MOD": "Terra", "MYD": "Aqua", "VNP": "SNPP", "VJ1": "NOAA-20", "ECO": "ISS"}[n[:3]]


def targets(sw, n, seed):
    """Random targets near pixel centres; truth = brute-force nearest pixel in a local window."""
    rng = np.random.default_rng(seed)
    nd = sw.lines_per_scan
    rows, cols = an.sample_pixels(sw, n, seed=seed, margin=nd + 6)
    dlat = np.nanmedian(np.abs(np.diff(sw.lat[::50, ::50], axis=0))) / 50
    dlon = np.nanmedian(np.abs(np.diff(sw.lon[::50, ::50], axis=1))) / 50
    lat = sw.lat[rows, cols] + rng.uniform(-0.7, 0.7, len(rows)) * dlat
    lon = sw.lon[rows, cols] + rng.uniform(-0.7, 0.7, len(rows)) * dlon
    hgt = np.nan_to_num(sw.height[rows, cols]) if sw.height is not None else np.zeros(len(rows))
    tr, tc = np.empty(len(rows), int), np.empty(len(rows), int)
    nl, ns = sw.shape
    for i, (r, c) in enumerate(zip(rows, cols)):
        r0, r1 = max(r - nd - 5, 0), min(r + nd + 6, nl)
        c0, c1 = max(c - 12, 0), min(c + 13, ns)
        d = geom.haversine_m(lat[i], lon[i], sw.lat[r0:r1, c0:c1], sw.lon[r0:r1, c0:c1])
        k = np.unravel_index(np.nanargmin(d), d.shape)
        tr[i], tc[i] = r0 + k[0], c0 + k[1]
    return lat, lon, hgt, tr, tc


def evaluate(sw, model, lat, lon, hgt, tr, tc):
    nav = an.scan_nav(sw, model)
    T = geom.lla_to_ecef(lat, lon, hgt)
    d, j = an.scan_angles(T, tr // model.n_det, model, nav)  # in the scan holding the truth
    line = (tr // model.n_det) * model.n_det + d
    el, es = line - tr, j - tc
    hwin = np.maximum(np.abs(np.round(line) - tr), np.abs(np.round(j) - tc))
    # does the model pick a scan at all / the right side of the swath?
    pred = an.predict(sw, lat, lon, model, nav, height=hgt)
    return {
        "line_err_p50": np.nanpercentile(np.abs(el), 50), "line_err_p99": np.nanpercentile(np.abs(el), 99),
        "line_err_max": np.nanmax(np.abs(el)), "samp_err_p50": np.nanpercentile(np.abs(es), 50),
        "samp_err_p99": np.nanpercentile(np.abs(es), 99), "samp_err_max": np.nanmax(np.abs(es)),
        "line_bias": np.nanmean(el), "samp_bias": np.nanmean(es),
        "win_p99": np.nanpercentile(hwin, 99), "win_p999": np.nanpercentile(hwin, 99.9), "win_max": np.nanmax(hwin),
        "in_swath_frac": pred.in_swath.mean(),
    }


def scene_info(sw):
    pos = sw.nav.pos
    alt = np.nanmedian(geom.ecef_to_lla(pos)[2]) / 1e3
    return {"altitude_km": alt}


models = {}
rows_out, selfcal = [], []

# --- 1. reference calibration -------------------------------------------------------
for plat, (loc, epoch) in REF.items():
    s = next(x for x in geo_scenes if x["platform"] == plat and x["location"] == loc and x["epoch"] == epoch)
    sw = load(s)
    m, res = an.calibrate(sw, seed=0, n=4000)
    models[plat] = m
    print(f"calibrated {plat} on {sw.name}: cost {res.cost:.1f}", {k: getattr(m, k) for k in ("j_c", "alpha", "phi0", "delta", "kappa", "t_off", "rpy")}, flush=True)

with open(config.RESULTS / "analytic_models.json", "w") as f:
    json.dump({k: {**asdict(v), "rpy": list(map(float, v.rpy))} for k, v in models.items()}, f, indent=1, default=float)

# --- 2./3. evaluation -----------------------------------------------------------------
jobs = [("geo_only", s) for s in geo_scenes] + [("main", name) for name in config.scenes()]
for kind, s in jobs:
    if kind == "geo_only":
        sw = load(s)
        meta = {k: s[k] for k in ("sensor", "platform", "location", "epoch", "day_night", "time_start")}
    else:
        sw = io.read_scene(s, lst=False)
        meta = {"sensor": sw.sensor, "platform": platform_of(sw), "location": "main:" + s, "epoch": "2023-06",
                "day_night": "DAY", "time_start": ""}
    if sw.nav is None:
        print("no nav for", sw.name)
        continue
    meta.update(scene=sw.name, kind=kind, **scene_info(sw))
    lat, lon, hgt, tr, tc = targets(sw, N_TARGETS, seed=11)
    self_m, _ = an.calibrate(sw, seed=1, n=2000)
    selfcal.append({**meta, **{k: getattr(self_m, k) for k in ("j_c", "alpha", "phi0", "delta", "kappa", "t_off")},
                    "pitch": self_m.rpy[1], "yaw": self_m.rpy[2]})
    for mname, m in [("spec", an.SPEC[sw.sensor]), ("reference", models[meta["platform"]]), ("self", self_m)]:
        for hmode, h in [("dem", hgt), ("h0", np.zeros_like(hgt))]:
            r = evaluate(sw, m, lat, lon, h, tr, tc)
            rows_out.append({**meta, "model": mname, "height": hmode, **r})
    last = rows_out[-4]
    print(f"{kind:8s} {meta['platform']:8s} {meta['location']:24s} {meta['epoch']} alt {meta['altitude_km']:.1f} km | "
          f"ref/dem win p99.9={last['win_p999']:.0f} max={last['win_max']:.0f} line_p99={last['line_err_p99']:.2f} "
          f"samp_p99={last['samp_err_p99']:.2f}", flush=True)
    pd.DataFrame(rows_out).to_csv(config.RESULTS / "analytic_consistency.csv", index=False)
    pd.DataFrame(selfcal).to_csv(config.RESULTS / "analytic_selfcal_constants.csv", index=False)

print("done", file=sys.stderr)
