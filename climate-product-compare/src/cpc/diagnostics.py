"""Timestamp-convention checks: lag correlation of products vs USCRN.

Hourly products: correlation of hourly pr / sw / tair at lags -3..+3 h (positive lag = the
product series shifted later). Daily products: correlation of daily pr / tmax / tmin against
station days ending at different UTC hours (0..42 h after the label date's 00 UTC).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import analysis as A


def _corr(a: pd.Series, b: pd.Series) -> float:
    j = pd.concat([a, b], axis=1).dropna()
    return float(np.corrcoef(j.iloc[:, 0], j.iloc[:, 1])[0, 1]) if len(j) > 100 else np.nan


def lag_table(site: pd.Series, products: list[str], root=None) -> list[dict]:
    obs = A.obs_series("USCRN", site.site_id, root)
    if obs is None:
        return []
    rows = []
    for name in products:
        df = A.product_series(name, site.site_id, root, "bilinear")
        if df is None or df.empty:
            continue
        freq = df.attrs["freq"]
        if freq == "30min":
            df = A.to_hourly(df)
        if freq in ("1h", "30min"):
            for v in ("pr", "sw", "tair"):
                if v in df and v in obs:
                    for lag in range(-3, 4):
                        rows.append({"site": site.site_id, "product": name, "var": v, "scale": "hourly", "lag_h": lag,
                                     "r": _corr(obs[v], df[v].shift(lag, freq="h"))})
        else:
            for v in ("pr", "tmax", "tmin"):
                if v not in df:
                    continue
                for E in range(0, 43, 6):
                    od = A.station_daily(obs, E)
                    rows.append({"site": site.site_id, "product": name, "var": v, "scale": "daily", "day_end_offset_h": E,
                                 "r": _corr(od[v], df[v])})
    return rows


NOMINAL_E = {"prism": 12, "gridmet": 31, "daymet": 30, "chirps3": 24, "imerg_final_daily": 24, "chelsa": 24}
OVERRIDE_GAIN = 0.02


def overrides_from(lags: pd.DataFrame) -> pd.DataFrame:
    """Daily (product, var) whose best-aligned station day differs from the documented one.

    Uses the median r across sites at each candidate day end (0..42 h, step 6); an override is
    recorded when the best window beats the window nearest the documented one by > 0.02 in r.
    """
    d = lags[lags.scale == "daily"].groupby(["product", "var", "day_end_offset_h"]).r.median().reset_index()
    rows = []
    for (p, v), g in d.groupby(["product", "var"]):
        nom = NOMINAL_E.get(p, 24)
        if p == "chelsa" and v in ("tmax", "tmin"):
            nom = 30
        g = g.set_index("day_end_offset_h").r
        near = g.index[np.argmin(np.abs(g.index - nom))]
        best = g.idxmax()
        rows.append({"product": p, "var": v, "documented_h": nom, "best_h": best, "r_documented": g[near], "r_best": g[best],
                     "use_h": best if g[best] - g[near] > OVERRIDE_GAIN else nom})
    return pd.DataFrame(rows)
