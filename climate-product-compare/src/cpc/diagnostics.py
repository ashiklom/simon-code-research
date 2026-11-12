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
        if df.attrs["freq"] == "30min":
            df = A.to_hourly(df)
        if df.attrs["freq"] in ("1h", "30min"):
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
