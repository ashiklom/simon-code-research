"""HAQES (Hazardous Air Quality Ensemble System; GMU / NASA HAQAST) ensemble-mean surface PM2.5.

GES DISC collections HAQES_NA_PM25_{TOT,OC,BC} v1 (DOI 10.5067/N0BWP445491R), one netCDF3 file
per day with 8 three-hourly steps (00..21 UTC) on a 12 km Lambert conformal CMAQ grid
(442 x 265; lcc 33/45, lat_0 40, lon_0 -97, sphere 6370 km; first cell centre at
(-2502000, -1710000) m, fitted exactly to the files' LAT/LON). Read over Earthdata HTTPS
(bearer token, redirect to the signed CloudFront URL) and opened in memory.

* Period: 2022-01-02 -> present (daily latency).
* Members: GEOS (NASA), NAAPS (Navy), GEFS-Aerosols, HRRR-Smoke and NACC-CMAQ (NOAA). Files are
  produced the afternoon before their valid day, so each day is a ~12-33 h forecast; values
  are stamped as given (treated as instantaneous at the stamp, not interval means).
* Independence: the NACC-CMAQ/NAQFC member's bias correction uses AirNow, so HAQES is
  partly dependent on AirNow/AQS.
"""

from __future__ import annotations

import functools
import time
from concurrent.futures import ThreadPoolExecutor

import netCDF4
import numpy as np
import pandas as pd
import pyproj

from .. import http
from .base import FieldProduct, Grid, Var

BASE = "https://data.gesdisc.earthdata.nasa.gov/data/HAQAST"
PROJ = "+proj=lcc +lat_1=33 +lat_2=45 +lat_0=40 +lon_0=-97 +a=6370000 +b=6370000 +units=m"
NX, NY, DX = 442, 265, 12000.0
X0, Y0 = -2502000.0, -1710000.0
COLLECTIONS = {"PM25_TOT": "HAQES_NA_PM25_TOT", "PM25_OC": "HAQES_NA_PM25_OC", "PM25_BC": "HAQES_NA_PM25_BC"}


def _get(url: str) -> bytes:
    h = http.earthdata_headers()
    u = url
    for _ in range(6):
        r = http.session().get(u, headers=h if "earthdata.nasa.gov" in u else {}, allow_redirects=False, timeout=180)
        if r.status_code in (301, 302, 303, 307, 308):
            u = r.headers["Location"]
            continue
        if r.status_code == 404:
            raise FileNotFoundError(url)
        r.raise_for_status()
        return r.content
    raise RuntimeError(f"too many redirects: {url}")


class HAQES(FieldProduct):
    name = "haqes"
    title = "HAQES ensemble mean (GMU/NASA)"
    freq = "3h"
    start = pd.Timestamp("2022-01-02")
    source = "GES DISC HAQES_NA_PM25_{TOT,OC,BC} v1 (data.gesdisc.earthdata.nasa.gov/data/HAQAST, Earthdata login)"
    notes = ("12 km North America, 3-hourly ensemble mean of GEOS, NAAPS, GEFS-Aerosols, HRRR-Smoke and NACC-CMAQ "
             "(next-day forecast). Partly dependent on AirNow via the NACC-CMAQ bias correction.")
    block_workers = 1
    file_workers = 12
    variables = {
        "pm25": Var(["PM25_TOT"], "pm", "ug m-3", attrs={"desc": "ensemble-mean surface PM2.5"}),
        "pm25_oc": Var(["PM25_OC"], "spec", "ug m-3", attrs={"desc": "ensemble-mean surface PM2.5 organic carbon"}),
        "pm25_bc": Var(["PM25_BC"], "spec", "ug m-3", attrs={"desc": "ensemble-mean surface PM2.5 black carbon"}),
    }

    def grid(self) -> Grid:
        crs = pyproj.CRS.from_proj4(PROJ)
        fwd = pyproj.Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        inv = pyproj.Transformer.from_crs(crs, "EPSG:4326", always_xy=True)

        def to_yx(lat, lon):
            x, y = fwd.transform(lon, lat)
            return y, x

        def to_latlon(y, x):
            lon, lat = inv.transform(x, y)
            return lat, lon

        return Grid(Y0 + DX * np.arange(NY), X0 + DX * np.arange(NX), to_yx=to_yx, to_latlon=to_latlon)

    @functools.cache
    def available_end(self) -> pd.Timestamp:
        r = http.get("https://cmr.earthdata.nasa.gov/search/granules.json?short_name=HAQES_NA_PM25_TOT"
                     "&page_size=1&sort_key=-start_date")
        e = r.json()["feed"]["entry"][0]
        return pd.Timestamp(e["time_start"]).tz_convert(None).normalize() + pd.Timedelta(hours=21)

    def blocks(self, t0, t1):
        days = pd.date_range(pd.Timestamp(t0).normalize(), pd.Timestamp(t1).normalize(), freq="D")
        months = days.to_period("M")
        return [days[months == p] for p in months.unique()]

    def _file(self, day: pd.Timestamp, var: str, jy, jx):
        url = f"{BASE}/{COLLECTIONS[var]}.1/{day:%Y}/HAQES_NA_v1.0_3h_{var}.{day:%Y%m%d}.nc"
        for attempt in range(3):  # occasionally a truncated body / HTML error page comes back
            try:
                b = _get(url)
            except FileNotFoundError:
                return var, None
            if b[:3] == b"CDF" or b[:4] == b"\x89HDF":
                break
            time.sleep(10 * (attempt + 1))
        else:
            print(f"[haqes] {url}: not a netCDF file after 3 tries, day skipped", flush=True)
            return var, None
        with netCDF4.Dataset("mem", memory=b) as d:
            tt = d["TIME"]
            times = pd.Timestamp(tt.units.split("since")[1].strip()) + pd.to_timedelta(np.asarray(tt[:]), unit="h")
            v = np.ma.filled(d[var][:].astype("f8"), np.nan)
        v[v < -900] = np.nan
        if v.shape[1:] != (NY, NX):
            raise ValueError(f"{url}: grid {v.shape}")
        return var, (pd.DatetimeIndex(times), np.moveaxis(v[:, jy, jx], 0, -1))  # (nsite, 4, nt)

    def read_block(self, days, st):
        iy, ix = st.px_index()
        ok = iy >= 0
        jy, jx = np.clip(iy, 0, None), np.clip(ix, 0, None)
        times = pd.date_range(days[0], days[-1] + pd.Timedelta(hours=21), freq="3h")
        raw = {v: np.full(iy.shape + (len(times),), np.nan) for v in COLLECTIONS}
        n = 0
        jobs = [(d, v) for d in days for v in COLLECTIONS]
        with ThreadPoolExecutor(self.file_workers) as ex:
            for var, res in ex.map(lambda j: self._file(j[0], j[1], jy, jx), jobs):
                if res is None:
                    continue
                n += 1
                t, v = res
                k = times.get_indexer(t)
                good = k >= 0
                raw[var][..., k[good]] = v[..., good]
        if n == 0:
            raise FileNotFoundError("no HAQES files in block")
        for v in raw.values():
            v[~ok] = np.nan
        return times, raw
