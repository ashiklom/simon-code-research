"""NEON tower meteorology (needs NEON_API_TOKEN since mid-2026; skipped cleanly without it).

30-min basic-package tables, aggregated to hourly (end-of-hour, both halves required):
  DP1.00002.001 SAAT_30min   single-aspirated air temperature, LOWEST tower level (closest to 2 m)
  DP1.00098.001 RH_30min     relative humidity (tower top)
  DP1.00023.001 SLRNR_30min  incoming shortwave (tower top)
  DP1.00006.001 PRIPRE_30min primary weighing gauge (core sites); else SECPRE_30min tipping bucket
  DP1.00001.001 2DWSD_30min  wind speed, lowest level
  DP1.00004.001 BP_30min     station pressure
Soil sensors are not used (depths need per-site sensor_positions handling).
NOTE: written against NEON's documented file conventions; not exercised until a token is set.
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
    "DP1.00006.001": ("PRIPRE_30min", "priPrecipBulk", "priPrecipFinalQF", "max", "pr"),
    "DP1.00001.001": ("2DWSD_30min", "windSpeedMean", "windSpeedFinalQF", "min", "wind"),
    "DP1.00004.001": ("BP_30min", "staPresMean", "staPresFinalQF", "max", "ps"),
}
SECONDARY_PRECIP = ("SECPRE_30min", "secPrecipBulk", "secPrecipRangeQF")
VARS = {
    "tair": ("temp", "degC", {"desc": "single-aspirated air temperature, lowest tower level"}),
    "rh": ("rh", "%", {}), "tdew": ("temp", "degC", {}), "vpd": ("vpd", "kPa", {}),
    "sw": ("rad", "W m-2", {}), "pr": ("precip", "mm", {}), "wind": ("wind", "m s-1", {"height_m": 3}),
    "ps": ("pres", "Pa", {}),
}


def token() -> str | None:
    return os.environ.get("NEON_API_TOKEN")


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
    for s in d["siteCodes"]:
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


def fetch_site(row, years) -> pd.DataFrame:
    if not token():
        raise RuntimeError("NEON_API_TOKEN not set; skipping NEON")
    from ..physics import dewpoint_from_rh, vpd_kpa

    out = {}
    for dp, (table, col, qf, pref, name) in TABLES.items():
        months = [m for m in _months(dp, row.code) if int(m[:4]) in years]
        parts = []
        for m in months:
            s = _read_table(dp, row.code, m, table, col, qf, pref)
            if s is None and name == "pr":
                s = _read_table(dp, row.code, m, *SECONDARY_PRECIP, "max")
            if s is not None:
                parts.append(s)
        if parts:
            out[name] = pd.concat(parts).sort_index()
    if not out:
        return pd.DataFrame()
    df = pd.DataFrame(out)
    lab = df.index.ceil("h")
    g = df.groupby(lab)
    n = g.count()
    h = pd.DataFrame({c: (g[c].sum(min_count=2) if c == "pr" else g[c].mean()).where(n[c] >= 2) for c in df})
    if "ps" in h:
        h["ps"] = h.ps * 1000  # kPa -> Pa
    if "tair" in h and "rh" in h:
        h["tdew"] = dewpoint_from_rh(h.tair.values, h.rh.values)
        h["vpd"] = vpd_kpa(h.tair.values, h.rh.values)
    h.index.name = "time"
    return h
