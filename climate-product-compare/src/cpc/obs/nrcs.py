"""NRCS SCAN and SNOTEL via the AWDB REST API (hourly).

Times are station local standard time (dataTimeZone) -> converted to UTC. TOBS is the
observed (instantaneous) air temperature; SCAN PRCP is the hourly increment. SNOTEL hourly
precipitation (accumulating PREC) is too noisy at 0.1" resolution and is not used. Soil
sensors at 2/4/8/20/40 in (~5/10/20/51/102 cm) map to the USCRN depths.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import http

API = "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1"
DEPTH = {-2: 5, -4: 10, -8: 20, -20: 50, -40: 100}
VARS = {
    "tair": ("temp", "degC", {"desc": "observed air temperature (instantaneous, TOBS)"}),
    "rh": ("rh", "%", {}),
    "tdew": ("temp", "degC", {}),
    "vpd": ("vpd", "kPa", {}),
    "pr": ("precip", "mm", {"desc": "hourly precipitation increment (SCAN PRCP)"}),
    "sw": ("rad", "W m-2", {"desc": "solar radiation (SRADV)"}),
    "wind": ("wind", "m s-1", {"desc": "wind speed (WSPDV)", "height_m": 3}),
    "swe": ("swe", "mm", {}),
    "snowd": ("snowd", "m", {}),
    **{f"sm{d:02d}": ("sm", "m3 m-3", {"depth_cm": d}) for d in DEPTH.values()},
    **{f"ts{d:02d}": ("temp", "degC", {"depth_cm": d}) for d in DEPTH.values()},
}
ELEMENTS = "TOBS,PRCP,RHUM,SRADV,WSPDV,WTEQ,SNWD,SMS:*,STO:*"


def station_list(network: str) -> pd.DataFrame:
    code = {"SCAN": "SCAN", "SNOTEL": "SNTL"}[network]
    d = http.get(f"{API}/stations", params={"stationTriplets": f"*:*:{code}", "activeOnly": "true"}).json()
    df = pd.DataFrame(d)
    df["begin"] = pd.to_datetime(df.beginDate)
    return df


def _f2c(x):
    return (x - 32) * 5 / 9


def fetch_site(row, years) -> pd.DataFrame:
    from ..physics import dewpoint_from_rh, vpd_kpa

    tz = float(row.tz)
    series: dict[str, list[pd.Series]] = {}
    for y in years:
        if pd.Timestamp(f"{y}-01-01") > pd.Timestamp.now():
            break
        r = http.get(f"{API}/data", params={"stationTriplets": row.triplet, "elements": ELEMENTS, "duration": "HOURLY",
                                            "beginDate": f"{y}-01-01 00:00", "endDate": f"{y}-12-31 23:00"}, timeout=300)
        js = r.json()
        if not js:
            continue
        for e in js[0].get("data", []):
            el = e["stationElement"]
            code, depth = el["elementCode"], el.get("heightDepth")
            vals = e.get("values", [])
            if not vals:
                continue
            s = pd.Series([v.get("value", np.nan) for v in vals], index=pd.to_datetime([v["date"] for v in vals]), dtype=float)
            s.index = s.index - pd.Timedelta(hours=tz)  # local standard -> UTC
            key = f"{code}{'' if depth is None else depth}"
            series.setdefault(key, []).append(s)
    if not series:
        return pd.DataFrame()
    S = {k: pd.concat(v).sort_index() for k, v in series.items()}
    S = {k: v[~v.index.duplicated()] for k, v in S.items()}
    out = pd.DataFrame(index=pd.DatetimeIndex(sorted(set().union(*[s.index for s in S.values()]))))
    if "TOBS" in S:
        t = _f2c(S["TOBS"])
        out["tair"] = t.where((t > -60) & (t < 60))
    if "RHUM" in S:
        out["rh"] = S["RHUM"].where((S["RHUM"] >= 0) & (S["RHUM"] <= 100))
    if "PRCP" in S and row.network == "SCAN":
        out["pr"] = (S["PRCP"] * 25.4).where(S["PRCP"] >= 0)
    if "SRADV" in S:
        out["sw"] = S["SRADV"].where((S["SRADV"] >= 0) & (S["SRADV"] < 1500))
    if "WSPDV" in S:
        out["wind"] = (S["WSPDV"] * 0.44704).where(S["WSPDV"] >= 0)
    if "WTEQ" in S:
        out["swe"] = (S["WTEQ"] * 25.4).where(S["WTEQ"] >= 0)
    if "SNWD" in S:
        out["snowd"] = (S["SNWD"] * 0.0254).where(S["SNWD"] >= 0)
    for dd, cm in DEPTH.items():
        if f"SMS{dd}" in S:
            out[f"sm{cm:02d}"] = (S[f"SMS{dd}"] / 100).where((S[f"SMS{dd}"] > 0) & (S[f"SMS{dd}"] <= 60))
        if f"STO{dd}" in S:
            out[f"ts{cm:02d}"] = _f2c(S[f"STO{dd}"]).where(S[f"STO{dd}"] > -40)
    if "tair" in out and "rh" in out:
        out["tdew"] = dewpoint_from_rh(out.tair.values, out.rh.values)
        out["vpd"] = vpd_kpa(out.tair.values, out.rh.values)
    out = out[out.index.minute == 0]
    out.index.name = "time"
    return out
