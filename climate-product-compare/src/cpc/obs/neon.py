"""NEON tower meteorology (needs NEON_API_TOKEN or NEON_API_KEY since mid-2026; skipped cleanly without it).

30-min basic-package tables, aggregated to hourly (end-of-hour, both halves required):
  DP1.00002.001 SAAT_30min   single-aspirated air temperature, LOWEST tower level (closest to 2 m)
  DP1.00098.001 RH_30min     relative humidity (tower top)
  DP1.00023.001 SLRNR_30min  incoming shortwave (tower top)
  DP1.00044.001 WEIPRE_60min weighing gauge (core sites); else DP1.00045.001 TIPPRE_30min tipping
                bucket (NEON retired DP1.00006.001 after RELEASE-2025 and split it into these)
  DP1.00001.001 2DWSD_30min  wind speed, tower top (the lowest level is inside forest canopies)
  DP1.00004.001 BP_30min     station pressure
Soil sensors are not used (depths need per-site sensor_positions handling).
Each table keeps its native step (30 min, or 60 min for the weighing gauge); an hour needs every
step present.
"""

from __future__ import annotations

import io
import os
import re

import numpy as np
import pandas as pd

from .. import http

API = "https://data.neonscience.org/api/v0"
NETWORK = "NEON"
SITES = ["HARV", "BART", "SCBI", "SERC", "OSBS", "DSNY", "JERC", "TALL", "ORNL", "GRSM", "UNDE", "TREE", "KONZ", "UKFS",
         "WOOD", "NOGP", "CPER", "NIWO", "YELL", "ONAQ", "MOAB", "SRER", "JORN", "CLBJ", "OAES", "WREF", "SJER", "TEAK"]
# product -> (table, value column, QF column, level preference 'min'|'max')
TABLES = {
    "DP1.00002.001": ("SAAT_30min", "tempSingleMean", "finalQF", "min", "tair"),
    "DP1.00098.001": ("RH_30min", "RHMean", "RHFinalQF", "max", "rh"),
    "DP1.00023.001": ("SLRNR_30min", "inSWMean", "inSWFinalQF", "max", "sw"),
    "DP1.00044.001": ("WEIPRE_60min", "precipBulk", "finalQF", "max", "pr"),
    "DP1.00001.001": ("2DWSD_30min", "windSpeedMean", "windSpeedFinalQF", "max", "wind"),
    "DP1.00004.001": ("BP_30min", "staPresMean", "staPresFinalQF", "max", "ps"),
}
SECONDARY_PRECIP = ("DP1.00045.001", "TIPPRE_30min", "precipBulk", "finalQF")
VARS = {
    "tair": ("temp", "degC", {"desc": "single-aspirated air temperature, lowest tower level"}),
    "rh": ("rh", "%", {}), "tdew": ("temp", "degC", {}), "vpd": ("vpd", "kPa", {}),
    "sw": ("rad", "W m-2", {}), "pr": ("precip", "mm", {}), "wind": ("wind", "m s-1", {"desc": "tower-top wind speed; height varies by site (8-60 m, above canopy), not log-law adjusted"}),
    "ps": ("pres", "Pa", {}),
}


def token() -> str | None:
    return os.environ.get("NEON_API_TOKEN") or os.environ.get("NEON_API_KEY")


def headers():
    return {"X-API-Token": token()} if token() else {}


def stations() -> pd.DataFrame:
    rows = []
    for code in SITES:
        d = http.get(f"{API}/sites/{code}").json()["data"]
        rows.append({"site_id": f"NEON:{code}", "network": NETWORK, "tier": 2, "name": d["siteName"], "state": d["stateCode"],
                     "lat": d["siteLatitude"], "lon": d["siteLongitude"], "elev_m": np.nan, "code": code,
                     "independence": "NEON towers are not in GHCN-D, MADIS or PRISM inputs."})
    return pd.DataFrame(rows)


def _files(dp: str, site: str, month: str) -> list[dict]:
    r = http.session().get(f"{API}/data/{dp}/{site}/{month}", params={"package": "basic"}, headers=headers(), timeout=120)
    if r.status_code in (403, 404):
        return []
    r.raise_for_status()
    return r.json()["data"]["files"]


def _months(dp: str, site: str) -> list[str]:
    d = http.get(f"{API}/products/{dp}", headers=headers()).json()["data"]
    for s in d.get("siteCodes") or []:
        if s["siteCode"] == site:
            return s["availableMonths"]
    return []


def _read_table(dp, site, month, table, col, qf, pref):
    files = [f for f in _files(dp, site, month) if f".{table}." in f["name"] and f["name"].endswith(".csv")]
    if not files:
        return None
    # NEON.D01.HARV.DP1.00002.001.000.010.030.SAAT_30min... -> HOR.VER
    def ver(f):
        m = re.search(r"\.(\d{3})\.(\d{3})\.\d{3}\." + re.escape(table), f["name"])
        return int(m.group(2)) if m else 0
    f = (min if pref == "min" else max)(files, key=ver)
    txt = http.get(f["url"], timeout=300).text
    d = pd.read_csv(io.StringIO(txt))
    s = pd.Series(d[col].where(d[qf] == 0).values, index=pd.to_datetime(d.endDateTime).dt.tz_localize(None))
    return s


def _hourly(s: pd.Series, name: str) -> pd.Series:
    """End-of-hour aggregate of one monthly table; every native step (30 or 60 min) is required."""
    step = pd.Series(s.index).diff().median()
    need = max(1, round(pd.Timedelta("1h") / step)) if pd.notna(step) else 1
    g = s.groupby(s.index.ceil("h"))
    n = g.count()
    return (g.sum(min_count=1) if name == "pr" else g.mean()).where(n >= need)


def fetch_site(row, years) -> pd.DataFrame:
    if not token():
        raise RuntimeError("NEON_API_TOKEN / NEON_API_KEY not set; skipping NEON")
    from ..physics import dewpoint_from_rh, vpd_kpa

    series = {}
    for dp, (table, col, qf, pref, name) in TABLES.items():
        months = {m for m in _months(dp, row.code) if int(m[:4]) in years}
        sec_months = set()
        if name == "pr":  # tipping bucket wherever the weighing gauge has no data
            sec_dp = SECONDARY_PRECIP[0]
            sec_months = {m for m in _months(sec_dp, row.code) if int(m[:4]) in years}
        parts = []
        for m in sorted(months | sec_months):
            s = _read_table(dp, row.code, m, table, col, qf, pref) if m in months else None
            if s is None and m in sec_months:
                s = _read_table(sec_dp, row.code, m, *SECONDARY_PRECIP[1:], "max")
            if s is not None and len(s):
                parts.append(_hourly(s, name))
        if parts:
            h = pd.concat(parts).sort_index()
            series[name] = h[~h.index.duplicated()]
    if not series:
        return pd.DataFrame()
    h = pd.DataFrame(series)
    if "ps" in h:
        h["ps"] = h.ps * 1000  # kPa -> Pa
    if "tair" in h and "rh" in h:
        h["tdew"] = dewpoint_from_rh(h.tair.values, h.rh.values)
        h["vpd"] = vpd_kpa(h.tair.values, h.rh.values)
    h.index.name = "time"
    return h
