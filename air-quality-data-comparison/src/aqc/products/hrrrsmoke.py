"""NOAA HRRR-Smoke near-surface smoke (MASSDEN at 8 m above ground), HRRRv4 analysis.

Source: dynamical.org ``noaa-hrrr-analysis-virtual`` Icechunk (s3://dynamical-noaa-hrrr,
anonymous), whose chunks are virtual references to the original GRIB2 messages in
s3://noaa-hrrr-bdp-pds (wrfsfcf00), decoded with gribberish. One chunk = one whole CONUS
field (1059 x 1799, 3 km Lambert conformal), so the reader fetches each hour's field once and
samples every site from it (cost independent of the number of sites).

* Smoke exists only from HRRRv4 (2020-12-02); HRRRv3 files have no MASSDEN.
* Units: NOAA encoded values in ug m-3 for cycles before 2021-12-21T14Z and kg m-3 from that
  cycle on; both are returned in ug m-3.
* Time: analysis (f00) values are instantaneous at the stamp (no shift). This is smoke PM2.5
  only (fire emissions), not total PM2.5.
"""

from __future__ import annotations

import functools
from concurrent.futures import ThreadPoolExecutor

import icechunk
import numpy as np
import pandas as pd
import pyproj
import zarr

from .base import FieldProduct, Grid, Var

UNIT_SWITCH = pd.Timestamp("2021-12-21 14:00")


@functools.cache
def _group():
    st = icechunk.s3_storage(bucket="dynamical-noaa-hrrr", prefix="noaa-hrrr-analysis-virtual/v0.1.0.icechunk",
                             region="us-west-2", anonymous=True)
    creds = icechunk.containers_credentials({"s3://noaa-hrrr-bdp-pds/": icechunk.s3_anonymous_credentials()})
    repo = icechunk.Repository.open(st, authorize_virtual_chunk_access=creds)
    return zarr.open_group(repo.readonly_session("main").store, mode="r")


class HRRRSmoke(FieldProduct):
    name = "hrrr_smoke"
    title = "HRRR-Smoke (HRRRv4 analysis)"
    freq = "1h"
    start = pd.Timestamp("2020-12-02 12:00")
    source = ("dynamical.org noaa-hrrr-analysis-virtual v0.1.0 Icechunk (virtual refs to s3://noaa-hrrr-bdp-pds "
              "wrfsfcf00 GRIB2), variable mass_density_8m")
    notes = ("3 km CONUS. Near-surface (8 m) smoke mass density from fire emissions only (not total PM2.5); "
             "instantaneous analysis value at the stamp. Starts with HRRRv4 (2020-12-02).")
    block_workers = 1
    hour_workers = 8
    variables = {
        "pm25_smoke": Var(["mass_density_8m"], "pm", "ug m-3",
                          attrs={"desc": "HRRR near-surface (8 m) smoke PM2.5, instantaneous", "instantaneous": True}),
    }

    @functools.cached_property
    def _times(self) -> pd.DatetimeIndex:
        return pd.to_datetime(_group()["time"][:], unit="s")

    def available_end(self) -> pd.Timestamp:
        # the axis runs to the latest run; leave a few hours for the GRIB upload to complete
        return (self._times[-1] - pd.Timedelta(hours=3)).floor("h")

    def grid(self) -> Grid:
        g = _group()
        crs = pyproj.CRS.from_wkt(g["spatial_ref"].attrs["crs_wkt"])
        fwd = pyproj.Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        inv = pyproj.Transformer.from_crs(crs, "EPSG:4326", always_xy=True)

        def to_yx(lat, lon):
            x, y = fwd.transform(lon, lat)
            return y, x

        def to_latlon(y, x):
            lon, lat = inv.transform(x, y)
            return lat, lon

        return Grid(g["y"][:], g["x"][:], to_yx=to_yx, to_latlon=to_latlon)

    def blocks(self, t0, t1):
        t = self._times
        m = (t >= t0) & (t <= t1)
        idx = np.nonzero(m)[0]
        months = t[idx].to_period("M")
        return [idx[months == p] for p in months.unique()]

    def read_block(self, idx, st):
        a = _group()["mass_density_8m"]
        times = self._times[idx]
        iy, ix = st.px_index()
        ok = iy >= 0
        jy, jx = np.clip(iy, 0, None), np.clip(ix, 0, None)
        out = np.full(iy.shape + (len(idx),), np.nan)

        def one(k):
            try:
                f = a[int(idx[k])]
            except Exception:
                return k, None
            v = np.asarray(f, dtype="f8")[jy, jx]
            return k, v

        with ThreadPoolExecutor(self.hour_workers) as ex:
            for k, v in ex.map(one, range(len(idx))):
                if v is None:
                    continue
                scale = 1.0 if times[k] < UNIT_SWITCH else 1e9  # -> ug m-3
                out[..., k] = np.where(ok, v * scale, np.nan)
        out[out < 0] = 0.0
        return times, {"mass_density_8m": out}
