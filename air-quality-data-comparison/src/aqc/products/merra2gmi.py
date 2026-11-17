"""MERRA-2 GMI (MERRA-2 meteorology replayed with GMI full chemistry), NCCS data portal (no login).

    https://portal.nccs.nasa.gov/datashare/merra2_gmi/Y<YYYY>/M<MM>/MERRA2_GMI.<coll>.<YYYYMMDD>.nc4

* ``merra2_gmi``: tavg1_2d_aer_Nx, hourly 2-D surface aerosol: PM25 ("total reconstructed
  PM2.5", which unlike MERRA-2 includes nitrate and ammonium), NISMASS25 (nitrate) and NH4SMASS.
  Hourly means stamped HH:30 -> end of hour.
* ``merra2_gmi_gas``: surface O3 and NO2. GMI publishes no hourly 2-D gas fields; the lowest
  model level (lev index 71, "positive down") of the DAILY-mean 3-D tavg24_3d_dac_Nv is used.
  Daily means of the UTC day (label = date at 00 UTC, day_end_offset_h = 24), so only
  daily-mean comparisons are possible (no MDA8 or diurnal cycle).
"""

from __future__ import annotations

import re
import time
import zlib

import numpy as np
import pandas as pd

from .. import http
from .base import Block, Grid, Var, bounded_map, sample_field, scale
from .h5remote import read_vars
from .merra2 import LAT, LON, _DailyFiles

BASE = "https://portal.nccs.nasa.gov/datashare/merra2_gmi"
KG2UG = 1e9


def _url(coll: str, day: pd.Timestamp) -> str:
    return f"{BASE}/Y{day:%Y}/M{day:%m}/MERRA2_GMI.{coll}.{day:%Y%m%d}.nc4"


def _portal_end(coll: str) -> pd.Timestamp:
    years = sorted(re.findall(r'href="Y(\d{4})/"', http.get(f"{BASE}/").text))
    for y in reversed(years):
        months = sorted(re.findall(r'href="M(\d{2})/"', http.get(f"{BASE}/Y{y}/").text))
        for m in reversed(months):
            days = re.findall(rf"MERRA2_GMI\.{coll}\.(\d{{8}})\.nc4", http.get(f"{BASE}/Y{y}/M{m}/").text)
            if days:
                return pd.Timestamp(max(days))
    raise RuntimeError("no MERRA2_GMI files found")


class _GMI(_DailyFiles):
    coll = ""
    level: tuple[int, int] | None = None
    day_workers = 2

    def available_end(self) -> pd.Timestamp:
        return _portal_end(self.coll) + pd.Timedelta(hours=24 if self.freq == "1h" else 0)

    def _read_day(self, args):
        day, url, st = args
        srcs = sorted({s for v in self.variables.values() for s in v.src})
        for attempt in range(4):
            try:
                a = read_vars(url, srcs, workers=6, level=self.level)
                break
            except FileNotFoundError:
                return None
            except Exception as e:
                if attempt == 3:
                    if isinstance(e, zlib.error):  # a corrupt chunk in the file itself: skip the day
                        print(f"[{self.name}] {url}: undecodable after 4 tries ({e}), day skipped", flush=True)
                        return None
                    raise
                time.sleep(10 * 2 ** attempt)
        raw = {s: sample_field(x[:, 0] if self.level else x, st).astype("f4") for s, x in a.items()}
        del a
        if self.freq == "1h":
            times = day + pd.to_timedelta(np.arange(1, 25), unit="h")
        else:
            times = pd.DatetimeIndex([day])
        return times, raw

    def fetch(self, sites, st, t0, t1):
        ids = list(sites.site_id)
        for month in pd.period_range(t0.to_period("M"), t1.to_period("M"), freq="M"):
            days = [(d, _url(self.coll, d), st) for d in pd.date_range(month.start_time, month.end_time.floor("D"))
                    if d + pd.Timedelta(hours=24) >= t0 and d <= t1]
            parts = [r for r in bounded_map(self._read_day, days, self.day_workers) if r is not None]
            if not parts:
                continue
            times = pd.DatetimeIndex(np.concatenate([p[0] for p in parts]))
            raw = {k: np.concatenate([p[1][k] for p in parts], axis=-1) for k in parts[0][1]}
            m = (times >= t0) & (times <= t1)
            yield Block(ids, times[m], self.convert_all({k: v[..., m] for k, v in raw.items()}))


class MERRA2GMI(_GMI):
    name = "merra2_gmi"
    title = "MERRA-2 GMI aerosols (full chemistry, with nitrate)"
    coll = "tavg1_2d_aer_Nx"
    freq = "1h"
    start = pd.Timestamp("2018-01-01 01:00")
    source = "NCCS portal datashare/merra2_gmi tavg1_2d_aer_Nx (range reads)"
    notes = "0.5x0.625 deg hourly; MERRA-2 met replay + GMI chemistry; PM25 = total reconstructed PM2.5 incl. nitrate/NH4"
    variables = {
        "pm25": Var(["PM25"], "pm", "ug m-3", scale(KG2UG), {"desc": "total reconstructed PM2.5"}),
        "pm25_no3": Var(["NISMASS25"], "spec", "ug m-3", scale(KG2UG), {"desc": "nitrate PM2.5"}),
        "pm25_nh4": Var(["NH4SMASS"], "spec", "ug m-3", scale(KG2UG), {"desc": "ammonium"}),
    }


class MERRA2GMIGas(_GMI):
    name = "merra2_gmi_gas"
    title = "MERRA-2 GMI surface O3/NO2 (daily mean)"
    coll = "tavg24_3d_dac_Nv"
    freq = "1d"
    level = (1, 71)
    start = pd.Timestamp("2018-01-01")
    source = "NCCS portal datashare/merra2_gmi tavg24_3d_dac_Nv, lowest model level (range reads)"
    notes = "0.5x0.625 deg; daily means only (no hourly gas output is published)"
    variables = {
        "o3": Var(["O3"], "ppb", "ppb", scale(1e9), {"day_end_offset_h": 24, "desc": "lowest model level, daily mean"}),
        "no2": Var(["NO2"], "ppb", "ppb", scale(1e9), {"day_end_offset_h": 24, "desc": "lowest model level, daily mean"}),
    }
