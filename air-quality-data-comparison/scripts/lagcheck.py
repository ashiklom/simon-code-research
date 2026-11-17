"""Timestamp check: lag correlation of hourly products against AQS hourly PM2.5 and O3.

For a fixed random sample of AQS sites with hourly O3 and PM2.5, each sub-daily product's
series is correlated with the observed series shifted by -3..+3 h, after removing a 24-h
centred running mean from both (so the diurnal cycle and timing dominate, not synoptic
variability). With values stamped at the end of their averaging hour, the median correlation
should peak at lag 0 (instantaneous products: between 0 and +1 h, since an instant at t is
compared with the hour ending at t).

Writes results/lagcheck.csv (median r per product x var x lag) and prints the peak lag.
Usage: uv run python scripts/lagcheck.py [n_sites]
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from aqc import analysis as A
from aqc import sites as S

ROOT = Path(__file__).resolve().parents[1]
N = int(sys.argv[1]) if len(sys.argv) > 1 else 40
LAGS = range(-3, 4)
PRODUCTS = ["geoscf_v1", "geoscf_v2", "merra2", "merra2_cnn", "merra2_gmi", "geosfp_aer", "naqfc",
            "naqfc_bc", "hrrr_smoke", "haqes", "cams_eac4", "cams_fcst"]
VARS = {"pm25": "pm25", "o3": "o3"}

avail = set(A.available_products())
sites = S.load("aqs")
sites = sites[sites.params.str.contains("o3") & sites.params.str.contains("pm25")]
sites = sites.sample(n=min(N, len(sites)), random_state=0)


def anom(s: pd.Series, step_h: float = 1.0) -> pd.Series:
    return s - s.rolling("24h", center=True, min_periods=int(18 / step_h)).mean()


rows = []
for _, site in sites.iterrows():
    obs = A.obs_series("AQS", site.site_id, "1h")
    an = A.obs_series("AirNow", site.site_id, "1h")  # preliminary data after AQS ends
    if obs is None or obs.empty:
        obs = an
    elif an is not None and not an.empty:
        obs = pd.concat([obs, an[an.index > obs.index.max()]])
    if obs is None or obs.empty:
        continue
    for prod in PRODUCTS:
        if prod not in avail:
            continue
        df = A.product_series(prod, site.site_id)
        if df is None:
            continue
        step = pd.Timedelta(df.attrs.get("freq", "1h"))
        if step > pd.Timedelta("3h"):
            continue
        for ov, pv0 in VARS.items():
            pv = pv0
            if pv not in df and pv == "pm25" and "pm25_smoke" in df:
                pv = "pm25_smoke"
            if ov not in obs or pv not in df:
                continue
            o = obs[ov].dropna()
            p = df[pv].dropna()
            if len(p) < 24 * 60 or len(o) < 24 * 60:
                continue
            # anomalies on each series' own grid; obs is hourly so shifting it by whole hours is exact
            oa = anom(o.asfreq("1h"))
            pa = anom(p.asfreq(step), step / pd.Timedelta("1h")).reindex(p.index)
            for lag in LAGS:
                # r(prod(t), obs(t + lag)): a positive peak lag means the product leads the obs
                os_ = oa.reindex(p.index + pd.Timedelta(hours=lag))
                ok = np.isfinite(pa.values) & np.isfinite(os_.values)
                if ok.sum() < 24 * 30:
                    continue
                r = np.corrcoef(pa.values[ok], os_.values[ok])[0, 1]
                rows.append({"site": site.site_id, "product": prod, "var": ov, "lag_h": lag, "r": r})

df = pd.DataFrame(rows)
tab = df.groupby(["product", "var", "lag_h"]).r.agg(["median", "size"]).reset_index()
tab.columns = ["product", "var", "lag_h", "median_r", "n_sites"]
tab["median_r"] = tab.median_r.round(3)
tab.to_csv(ROOT / "results" / "lagcheck.csv", index=False)
peak = tab.loc[tab.groupby(["product", "var"]).median_r.idxmax()]
print(peak.to_string(index=False))
