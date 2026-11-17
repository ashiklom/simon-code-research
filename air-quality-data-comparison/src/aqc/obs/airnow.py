"""AirNow hourly files (preliminary, unvalidated) for the recent window not yet in AQS.

    https://s3-us-west-1.amazonaws.com/files.airnowtech.org/airnow/YYYY/YYYYMMDD/HourlyData_YYYYMMDDHH.dat

Anonymous. Pipe-delimited: date|time|AQSID|site|UTC offset|parameter|unit|value|agency; the
date/time are UTC and label the START of the hour (stored here at the hour's end). AQSID's
first 9 digits are the AQS state-county-site code, so values join Tier-1 AQS sites.
Parameters kept: PM2.5, PM10 (ug m-3), OZONE, NO2 (ppb). Written to the obs-AirNow repo.
"""

from __future__ import annotations

import io
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from ..http import session

S3 = "https://s3-us-west-1.amazonaws.com/files.airnowtech.org/airnow"
PARAMS = {"PM2.5": "pm25", "PM10": "pm10", "OZONE": "o3", "NO2": "no2"}


def _hour(t: pd.Timestamp) -> pd.DataFrame | None:
    url = f"{S3}/{t:%Y}/{t:%Y%m%d}/HourlyData_{t:%Y%m%d%H}.dat"
    try:
        r = session().get(url, timeout=60)
        if r.status_code != 200:
            return None
        d = pd.read_csv(io.StringIO(r.content.decode("latin-1")), sep="|", header=None,
                        names=["date", "time", "aqsid", "site", "off", "param", "unit", "value", "agency"],
                        dtype={"aqsid": str}, on_bad_lines="skip")
    except Exception:
        return None
    d = d[d.param.isin(PARAMS)]
    d = d[d.aqsid.str.fullmatch(r"\d{9}", na=False)]
    return pd.DataFrame({"site_id": "AQS:" + d.aqsid.str[:2] + "-" + d.aqsid.str[2:5] + "-" + d.aqsid.str[5:9],
                         "var": d.param.map(PARAMS), "time": t + pd.Timedelta(hours=1),
                         "value": pd.to_numeric(d.value, errors="coerce")})


def hourly(sites: pd.DataFrame, t0: pd.Timestamp, t1: pd.Timestamp, workers: int = 16, log=print) -> dict:
    ids = set(sites.site_id)
    hours = pd.date_range(t0, t1, freq="h")
    out = []
    with ThreadPoolExecutor(workers) as ex:
        for k, d in enumerate(ex.map(_hour, hours)):
            if d is not None:
                out.append(d[d.site_id.isin(ids) & (d.value > -900)])
            if k % 720 == 0:
                log(f"[AirNow] {hours[k]:%Y-%m-%d} ({k}/{len(hours)})")
    d = pd.concat(out)
    d = d.groupby(["site_id", "var", "time"])["value"].mean().reset_index()
    return {v: g[["site_id", "time", "value"]] for v, g in d.groupby("var")}
