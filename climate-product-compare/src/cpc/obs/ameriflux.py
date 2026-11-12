"""AmeriFlux BASE half-hourly data (needs AMERIFLUX_USER_ID and AMERIFLUX_EMAIL; skipped without).

BASE (not FLUXNET/ONEFlux) because FLUXNET gap-fills meteorology with ERA5. Timestamps are
local standard time (TIMESTAMP_END) -> UTC via the longitude-based standard offset. Uses the
first TA/RH/P/SW_IN/WS/PA column (H_V_R qualifiers 1_1_1 preferred).
NOTE: written against AmeriFlux's documented API and file format; not exercised until
credentials are set.
"""

from __future__ import annotations

import io
import os
import re
import zipfile

import numpy as np
import pandas as pd

from .. import http

API = "https://amfcdn.lbl.gov/api/v1"
NETWORK = "AMERIFLUX"
SITES = ["US-Ha1", "US-MMS", "US-NR1", "US-Ne1", "US-Var", "US-Ton", "US-Wkg", "US-SRM", "US-Seg", "US-Mpj", "US-UMB",
         "US-Syv", "US-ARM"]
VARS = {
    "tair": ("temp", "degC", {}), "rh": ("rh", "%", {}), "tdew": ("temp", "degC", {}), "vpd": ("vpd", "kPa", {}),
    "pr": ("precip", "mm", {}), "sw": ("rad", "W m-2", {}), "wind": ("wind", "m s-1", {"height_m": 10}),
    "ps": ("pres", "Pa", {}),
}
COLS = {"TA": "tair", "RH": "rh", "P": "pr", "SW_IN": "sw", "WS": "wind", "PA": "ps"}


def creds():
    u, e = os.environ.get("AMERIFLUX_USER_ID"), os.environ.get("AMERIFLUX_EMAIL")
    return (u, e) if u and e else None


def stations() -> pd.DataFrame:
    meta = {d["SITE_ID"]: d for d in http.get(f"{API}/site_display/AmeriFlux").json()}
    rows = []
    for s in SITES:
        d = meta[s]
        loc = d["GRP_LOCATION"]
        rows.append({"site_id": f"AMERIFLUX:{s}", "network": NETWORK, "tier": 2, "name": d["SITE_NAME"], "state": d.get("STATE", ""),
                     "lat": float(loc["LOCATION_LAT"]), "lon": float(loc["LOCATION_LONG"]),
                     "elev_m": float(loc.get("LOCATION_ELEV") or np.nan), "code": s,
                     "independence": "AmeriFlux towers are not in GHCN-D, MADIS or PRISM inputs."})
    return pd.DataFrame(rows)


def _pick(cols, var):
    cands = [c for c in cols if re.fullmatch(rf"{var}(_\d+_\d+_\d+|_\d+)?", c)]
    if not cands:
        return None
    pri = {f"{var}": 0, f"{var}_1_1_1": 1}
    return sorted(cands, key=lambda c: (pri.get(c, 2), c))[0]


def fetch_site(row, years) -> pd.DataFrame:
    c = creds()
    if not c:
        raise RuntimeError("AMERIFLUX_USER_ID / AMERIFLUX_EMAIL not set; skipping AmeriFlux")
    from ..physics import dewpoint_from_rh, vpd_kpa

    body = {"user_id": c[0], "user_email": c[1], "data_product": "BASE-BADM", "data_variant": "FULLSET",
            "data_policy": "CCBY4.0", "site_ids": [row.code], "intended_use": "other_research",
            "description": "Evaluation of gridded meteorological products against tower observations"}
    r = http.session().post(f"{API}/data_download", json=body, timeout=300)
    r.raise_for_status()
    urls = [u["url"] for u in r.json().get("data_urls", [])]
    if not urls:
        return pd.DataFrame()
    z = zipfile.ZipFile(io.BytesIO(http.get(urls[0], timeout=600).content))
    name = next(n for n in z.namelist() if re.search(r"_BASE_HH_.*\.csv$", n))
    d = pd.read_csv(z.open(name), comment="#", na_values=[-9999, "-9999"])
    t = pd.to_datetime(d.TIMESTAMP_END.astype(str), format="%Y%m%d%H%M") - pd.Timedelta(hours=round(row.lon / 15))
    df = pd.DataFrame(index=t)
    for src, dst in COLS.items():
        col = _pick(d.columns, src)
        if col:
            df[dst] = d[col].values
    df = df[df.index.year.isin(years)]
    lab = df.index.ceil("h")
    g = df.groupby(lab)
    n = g.count()
    h = pd.DataFrame({c: (g[c].sum(min_count=2) if c == "pr" else g[c].mean()).where(n[c] >= 2) for c in df})
    if "ps" in h:
        h["ps"] = h.ps * 1000
    if "sw" in h:
        h["sw"] = h.sw.clip(lower=0)
    if "tair" in h and "rh" in h:
        h["tdew"] = dewpoint_from_rh(h.tair.values, h.rh.values)
        h["vpd"] = vpd_kpa(h.tair.values, h.rh.values)
    h.index.name = "time"
    return h
