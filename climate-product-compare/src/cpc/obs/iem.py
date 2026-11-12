"""Iowa State Soil Moisture Network (ISUSM) via the Iowa Environmental Mesonet.

Hourly, UTC. Solar radiation (slrkj_tot) is not used: its hourly values are non-zero at night
in the archive. Soil temperature at 4/12/24/50 in (10/30/61/127 cm), soil moisture at
12/24/50 in.
"""

from __future__ import annotations

import io

import numpy as np
import pandas as pd

from .. import http

URL = "https://mesonet.agron.iastate.edu/cgi-bin/request/isusm.py"
SRC = {"tair_c_avg": "tair", "rh_avg": "rh", "rain_in_tot": "pr", "ws_mps_s_wvt": "wind", "t4_c_avg": "ts10",
       "t12_c_avg": "ts30", "t24_c_avg": "ts61", "t50_c_avg": "ts127", "calcvwc12_avg": "sm30", "calcvwc24_avg": "sm61",
       "calcvwc50_avg": "sm127"}
VARS = {
    "tair": ("temp", "degC", {}), "rh": ("rh", "%", {}), "tdew": ("temp", "degC", {}), "vpd": ("vpd", "kPa", {}),
    "pr": ("precip", "mm", {}), "wind": ("wind", "m s-1", {"height_m": 2}),
    **{f"ts{d}": ("temp", "degC", {"depth_cm": d}) for d in (10, 30, 61, 127)},
    **{f"sm{d}": ("sm", "m3 m-3", {"depth_cm": d}) for d in (30, 61, 127)},
}


def station_list() -> pd.DataFrame:
    d = http.get("https://mesonet.agron.iastate.edu/geojson/network/ISUSM.geojson").json()["features"]
    return pd.DataFrame([{**f["properties"], "lon": f["geometry"]["coordinates"][0], "lat": f["geometry"]["coordinates"][1]}
                         for f in d])


def fetch_site(row, years) -> pd.DataFrame:
    from ..physics import dewpoint_from_rh, vpd_kpa

    parts = []
    for y in years:
        if pd.Timestamp(f"{y}-01-01") > pd.Timestamp.now():
            break
        r = http.get(URL, params={"mode": "hourly", "station": row.code, "sts": f"{y}-01-01T00:00Z", "ets": f"{y + 1}-01-01T00:00Z",
                                  "tz": "UTC", "format": "comma", "vars": ",".join(SRC)}, timeout=300)
        if r.text.strip():
            parts.append(pd.read_csv(io.StringIO(r.text)))
    if not parts:
        return pd.DataFrame()
    d = pd.concat(parts)
    d.index = pd.to_datetime(d.valid.str[:16])
    out = pd.DataFrame(index=d.index)
    for s, c in SRC.items():
        if s in d:
            x = pd.to_numeric(d[s], errors="coerce")
            out[c] = x.where(x > -90)
    out["pr"] = out.pr * 25.4
    for c in [c for c in out if c.startswith("sm")]:
        out[c] = out[c].where((out[c] > 0) & (out[c] <= 0.6))
    out["tdew"] = dewpoint_from_rh(out.tair.values, out.rh.values)
    out["vpd"] = vpd_kpa(out.tair.values, out.rh.values)
    out.index.name = "time"
    return out[~out.index.duplicated()]
