"""CHELSA-daily v2.1 (EnviCloud COGs, 30 arc-second), one windowed read per site per file.

Raw uint16 with scale/offset per variable; tas* in K, hurs as fraction, rsds W m-2,
sfcWind m s-1, ps hPa, prec/pr mm/day. `pr` (GPCC bias-corrected) exists only 1979-2019 and
is not mixed with `prec`. tasmax/tasmin are taken over 06-06 UTC (day_end_offset_h = 30).
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from .. import http
from .base import Block, Grid, Product, Var

BASE = "https://os.unil.cloud.switch.ch/chelsa02/chelsa/global/daily"
X0, Y0, D = -180.00013888885002, 83.99986041515001, 1 / 120
LON = X0 + D * (np.arange(43200) + 0.5)
LAT = Y0 - D * (np.arange(20880) + 0.5)
GDAL_ENV = dict(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", CPL_VSIL_CURL_USE_HEAD="NO", GDAL_HTTP_MULTIPLEX="YES",
                GDAL_HTTP_VERSION="2", GDAL_HTTP_MAX_RETRY="6", GDAL_HTTP_RETRY_DELAY="2", VSI_CACHE="FALSE",
                GDAL_INGESTED_BYTES_AT_OPEN="32768", GDAL_HTTP_TIMEOUT="120", CPL_VSIL_CURL_CHUNK_SIZE="65536")
# var -> (scale, offset) applied by us; values == 65535 are nodata
SRC = {"tas": (0.1, 0), "tasmax": (0.1, 0), "tasmin": (0.1, 0), "hurs": (0.001, 0), "rsds": (0.1157407407, 0),
       "sfcWind": (0.01, 0), "ps": (1.0, 0), "prec": (0.1, 0), "pr": (0.1, 0)}
UTC = {"day_end_offset_h": 24}
D06 = {"day_end_offset_h": 30}


class CHELSA(Product):
    name = "chelsa"
    title = "CHELSA-daily v2.1"
    freq = "1d"
    # CHELSA is one COG per variable-day and each file is sampled once per site (~17 s per file for
    # 305 sites), so the full record (~58k files) was impractical here: extract the common window.
    start = pd.Timestamp("2018-09-01")
    source = "CHELSA-daily v2.1 COGs (os.unil.cloud.switch.ch/chelsa02/chelsa/global/daily)"
    notes = ("30 arc-second downscaled ERA5. Extracted for the common window (2018-09 onward) only. "
             "prec is not bias corrected; pr (GPCC-corrected) only 1979-2019.")
    file_workers = 48
    variables = {
        "tair": Var(["tas"], "temp", "degC", lambda tas: tas - 273.15, {**UTC, "desc": "daily mean 2 m temperature"}),
        "tmax": Var(["tasmax"], "temp", "degC", lambda tasmax: tasmax - 273.15, {**D06}),
        "tmin": Var(["tasmin"], "temp", "degC", lambda tasmin: tasmin - 273.15, {**D06}),
        "rh": Var(["hurs"], "rh", "%", lambda hurs: hurs * 100, {**UTC}),
        "sw": Var(["rsds"], "rad", "W m-2", None, {**UTC}),
        "wind": Var(["sfcWind"], "wind", "m s-1", None, {**UTC, "height_m": 10}),
        "ps": Var(["ps"], "pres", "Pa", lambda ps: ps * 100, {**UTC}),
        "pr": Var(["prec"], "precip", "mm", None, {**UTC, "desc": "precipitation (not bias corrected)"}),
        "pr_gpcc": Var(["pr"], "precip", "mm", None, {**UTC, "desc": "GPCC bias-corrected precipitation (1979-2019)"}),
    }

    def grid(self):
        return Grid(LAT, LON)

    def url(self, var, d):
        return f"{BASE}/{var}/{d:%Y}/CHELSA_{var}_{d:%d}_{d:%m}_{d:%Y}_V.2.1.tif"

    def available_end(self):
        # walk back from today until a tas file exists
        d = pd.Timestamp.now().normalize()
        for _ in range(800):
            r = http.session().head(self.url("tas", d), timeout=60)
            if r.status_code == 200:
                return d
            d -= pd.Timedelta(days=1 if _ > 30 else 15)
        raise RuntimeError("no CHELSA files found")

    def fetch(self, sites, st, t0, t1):
        import rasterio
        from rasterio.windows import Window

        iy, ix = st.iy, st.ix
        r0, c0 = iy.min(1), ix.min(1)
        yy = (iy - r0[:, None])[:, [0, 0, 1, 1]]
        xx = (ix - c0[:, None])[:, [0, 1, 0, 1]]

        def read(task):
            var, d = task
            out = np.full((len(sites), 4), np.nan)
            sc, off = SRC[var]
            try:
                with rasterio.Env(**GDAL_ENV), rasterio.open("/vsicurl/" + self.url(var, d)) as ds:
                    for k in range(len(sites)):
                        a = ds.read(1, window=Window(int(c0[k]), int(r0[k]), 2, 2)).astype("f8")
                        a = np.where(a == 65535, np.nan, a * sc + off)
                        out[k] = a[yy[k], xx[k]]
            except rasterio.errors.RasterioIOError:
                pass  # missing file -> NaN
            return task, out

        for m0 in pd.date_range(t0.to_period("M").start_time, t1, freq="MS"):
            days = pd.date_range(max(t0, m0), min(t1, m0 + pd.offsets.MonthEnd(0)), freq="D")
            if len(days) == 0:
                continue
            vars_ = [v for v in SRC if not (v == "pr" and m0.year > 2019)]
            raw = {v: np.full((len(sites), 4, len(days)), np.nan) for v in SRC}
            with ThreadPoolExecutor(self.file_workers) as ex:
                for (var, d), vals in ex.map(read, [(v, d) for v in vars_ for d in days]):
                    raw[var][:, :, days.get_loc(d)] = vals
            yield Block(list(sites.site_id), days, self.convert_all(raw))


os.environ.setdefault("GDAL_HTTP_TIMEOUT", "120")
