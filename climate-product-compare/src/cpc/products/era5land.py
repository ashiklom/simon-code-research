"""ERA5-Land from ECMWF's CDS ARCO data lake, geo-chunked (time-series) Zarr stores.

Accumulations (tp, ssrd) in these stores are already de-accumulated to hourly totals over the
hour ending at the stamp (verified: diurnal SW timing and hourly tp values).
"""

from __future__ import annotations

import functools
import os

import pandas as pd
import zarr
from zarr.storage import FsspecStore

from .base import ChunkedStoreProduct, Grid
from .era5 import common_vars

BASE = "https://arco.datastores.ecmwf.int/cadl-arco-geo-{nnn}/arco/reanalysis_era5_land/{grp}/geoChunked.zarr"
GROUPS = {
    ("007", "sfc-2m-temperature"): ["t2m", "d2m"],
    ("009", "sfc-pressure-precipitation"): ["sp", "tp"],
    ("008", "sfc-wind"): ["u10", "v10"],
    ("010", "sfc-radiation-heat"): ["ssrd"],
    ("043", "sfc-skin-temperature"): ["skt"],
    ("006", "sfc-soil-temperature"): ["stl1", "stl2", "stl3", "stl4"],
    ("005", "sfc-soil-water"): ["swvl1", "swvl2", "swvl3", "swvl4"],
    ("030", "sfc-snow"): ["sde"],
}


class ERA5Land(ChunkedStoreProduct):
    name = "era5land"
    title = "ERA5-Land"
    freq = "1h"
    start = pd.Timestamp("1950-01-02")
    source = "ECMWF CDS ARCO geoChunked Zarr (arco.datastores.ecmwf.int, reanalysis_era5_land)"
    notes = "0.1 deg land reanalysis forced by ERA5; no data assimilation."
    variables = common_vars(n_sm=4, snow="sde", snow_kind="snowd")
    site_workers = 6

    def _headers(self):
        key = os.environ.get("CDSAPI_KEY")
        if not key:
            raise RuntimeError("CDSAPI_KEY is required for the ECMWF ARCO stores")
        return {"Authorization": f"Bearer {key}"}

    @functools.cached_property
    def groups(self) -> dict:
        out = {}
        for (nnn, grp), names in GROUPS.items():
            st = FsspecStore.from_url(BASE.format(nnn=nnn, grp=grp), storage_options={"headers": self._headers()}, read_only=True)
            g = zarr.open_group(st, mode="r", zarr_format=2, use_consolidated=True)
            out[grp] = (g, names)
        return out

    @functools.cached_property
    def _first(self):
        return next(iter(self.groups.values()))[0]

    def grid(self):
        g = self._first
        return Grid(g["latitude"][:], g["longitude"][:], x_periodic=360.0)

    def arrays(self):
        return {n: g[n] for g, names in self.groups.values() for n in names}

    @functools.cache
    def source_times(self):
        t = self._first["time"]
        units = t.attrs.get("units", "")
        v = t[:]
        if "since" in units:
            step, ref = units.split(" since ")
            return pd.Timestamp(ref) + pd.to_timedelta(v, unit={"hours": "h", "seconds": "s", "minutes": "min", "days": "D"}[step])
        return pd.DatetimeIndex(v)

    def available_end(self):
        return self.source_times()[-1]
