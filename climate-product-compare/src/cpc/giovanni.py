"""NASA Giovanni-in-the-Cloud time-series API (point series; nearest grid cell).

GET https://api.giovanni.earthdata.nasa.gov/timeseries?data=<ID>&location=[lat,lon]&time=<t0>/<t1>
with an Earthdata bearer token. Returns CSV: header block, blank line, then
"Timestamp (UTC),Data". We pass pixel-centre coordinates so "nearest" is exact.
"""

from __future__ import annotations

import io
import time

import numpy as np
import pandas as pd

from . import http

URL = "https://api.giovanni.earthdata.nasa.gov/timeseries"


def series(data_id: str, lat: float, lon: float, t0: pd.Timestamp, t1: pd.Timestamp, *, max_years: int = 10) -> pd.Series:
    """Fetch a point series, splitting long periods into <= max_years requests."""
    parts = []
    edges = list(pd.date_range(t0, t1, freq=f"{max_years}YS")) if (t1 - t0).days > 366 * max_years else []
    bounds = [pd.Timestamp(t0), *[e for e in edges if e > t0], pd.Timestamp(t1)]
    for a, b in zip(bounds[:-1], bounds[1:]):
        parts.append(_one(data_id, lat, lon, a, b))
    s = pd.concat(parts)
    return s[~s.index.duplicated()].sort_index()


def _one(data_id, lat, lon, t0, t1) -> pd.Series:
    params = {"data": data_id, "location": f"[{lat:.5f},{lon:.5f}]",
              "time": f"{t0:%Y-%m-%dT%H:%M:%S}/{t1:%Y-%m-%dT%H:%M:%S}"}
    import requests

    for attempt in range(6):
        try:
            r = http.session().get(URL, params=params, headers=http.earthdata_headers(), timeout=600)
        except (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError):
            time.sleep(10 * (attempt + 1))
            continue
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(10 * (attempt + 1))
            continue
        r.raise_for_status()
        break
    else:
        raise RuntimeError(f"Giovanni request failed repeatedly: {params}")
    txt = r.text
    head, _, body = txt.partition("\n\n")
    meta = dict(ln.split(",", 1) for ln in head.splitlines() if "," in ln)
    undef = float(meta.get("undef", "1e15"))
    df = pd.read_csv(io.StringIO(body))
    s = pd.Series(df.iloc[:, 1].astype(float).values, index=pd.to_datetime(df.iloc[:, 0]))
    s[np.isclose(s, undef) | (s.abs() > 1e14)] = np.nan
    return s
