"""NOAA SURFRAD (7 long-record sites): research-grade radiation plus T, RH, wind, pressure.

Daily files of 1-min (3-min before 2009) data; aggregated to hourly means stamped at the end
of the hour (>= 80 % of samples, QC flag 0). Air temperature/RH/wind are measured on the 10 m
tower (attrs height_m=10).
"""

from __future__ import annotations

import io
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from .. import http

BASE = "https://gml.noaa.gov/aftp/data/radiation/surfrad"
NETWORK = "SURFRAD"
SITES = {  # dir, file prefix, lat, lon, elev_m (from file headers)
    "bon": ("Bondville_IL", 40.05, -88.37, 213),
    "tbl": ("Boulder_CO", 40.13, -105.24, 1689),
    "dra": ("Desert_Rock_NV", 36.62, -116.02, 1007),
    "fpk": ("Fort_Peck_MT", 48.31, -105.10, 634),
    "gwn": ("Goodwin_Creek_MS", 34.25, -89.87, 98),
    "psu": ("Penn_State_PA", 40.72, -77.93, 376),
    "sxf": ("Sioux_Falls_SD", 43.73, -96.62, 473),
}
COLS = ["year", "jday", "month", "day", "hour", "min", "dt", "zen"] + [
    f"{n}{s}" for n in ["dw_psp", "uw_psp", "direct_n", "diffuse", "dw_pir", "dw_casetemp", "dw_dometemp", "uw_pir",
                        "uw_casetemp", "uw_dometemp", "uvb", "par", "netsolar", "netir", "totalnet", "temp", "rh",
                        "windspd", "winddir", "pressure"] for s in ("", "_qc")]
VARS = {
    "tair": ("temp", "degC", {"desc": "air temperature (10 m tower)", "height_m": 10}),
    "rh": ("rh", "%", {}),
    "tdew": ("temp", "degC", {"desc": "dewpoint from T and RH"}),
    "vpd": ("vpd", "kPa", {}),
    "sw": ("rad", "W m-2", {"desc": "downwelling global shortwave (PSP)"}),
    "wind": ("wind", "m s-1", {"height_m": 10}),
    "ps": ("pres", "Pa", {}),
}


def stations() -> pd.DataFrame:
    return pd.DataFrame([{"site_id": f"SURFRAD:{k}", "network": NETWORK, "tier": 2, "name": v[0].replace("_", " "),
                          "state": v[0][-2:], "lat": v[1], "lon": v[2], "elev_m": v[3], "code": k,
                          "independence": "Not in GHCN-D, MADIS or PRISM inputs (radiation network)."}
                         for k, v in SITES.items()])


def _day(code: str, d: pd.Timestamp) -> pd.DataFrame | None:
    url = f"{BASE}/{SITES[code][0]}/{d:%Y}/{code}{d:%y}{d.dayofyear:03d}.dat"
    r = http.session().get(url, timeout=120)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text), sep=r"\s+", skiprows=2, header=None, names=COLS)
    return df


def fetch_site(row, years) -> pd.DataFrame:
    from ..physics import dewpoint_from_rh, vpd_kpa

    days = [d for y in years for d in pd.date_range(f"{y}-01-01", f"{y}-12-31") if d <= pd.Timestamp.now()]
    with ThreadPoolExecutor(8) as ex:
        parts = [p for p in ex.map(lambda d: _day(row.code, d), days) if p is not None]
    if not parts:
        return pd.DataFrame()
    d = pd.concat(parts, ignore_index=True)
    t = pd.to_datetime(dict(year=d.year, month=d.month, day=d.day, hour=d.hour, minute=d["min"]))
    out = pd.DataFrame(index=t)
    for v, src in (("tair", "temp"), ("rh", "rh"), ("sw", "dw_psp"), ("wind", "windspd"), ("ps", "pressure")):
        x = d[src].where((d[src + "_qc"] == 0) & (d[src] > -9999)).values
        out[v] = x
    out["sw"] = out.sw.clip(lower=0)
    out["ps"] = out.ps * 100
    # sample timestamps mark the start of each 1-min (or 3-min) sample -> hour ending ceil
    lab = (out.index + pd.Timedelta(minutes=1)).ceil("h")
    g = out.groupby(lab)
    per_hour = g.size().median()
    h = g.mean().where(g.count() >= 0.8 * per_hour)
    h["tdew"] = dewpoint_from_rh(h.tair.values, h.rh.values)
    h["vpd"] = vpd_kpa(h.tair.values, h.rh.values)
    h.index.name = "time"
    return h
