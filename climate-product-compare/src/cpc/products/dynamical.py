"""dynamical.org Icechunk stores: NOAA HRRR analysis, CHIRPS v3 final, IMERG Late."""

from __future__ import annotations

import functools

import icechunk
import numpy as np
import pandas as pd
import pyproj
import zarr

from ..physics import vpd_kpa
from .base import ChunkedStoreProduct, Grid, Var


def open_dynamical(bucket: str, prefix: str) -> zarr.Group:
    st = icechunk.s3_storage(bucket=bucket, prefix=prefix, region="us-west-2", anonymous=True)
    return zarr.open_group(icechunk.Repository.open(st).readonly_session("main").store, mode="r")


def _secs(a) -> pd.DatetimeIndex:
    return pd.to_datetime(a[:], unit="s")


class DynamicalProduct(ChunkedStoreProduct):
    bucket = ""
    prefix = ""

    @functools.cached_property
    def group(self):
        return open_dynamical(self.bucket, self.prefix)

    def arrays(self):
        return {s: self.group[s] for v in self.variables.values() for s in v.src}

    time_shift = pd.Timedelta(0)

    @functools.cache
    def source_times(self):
        return _secs(self.group["time"]) + self.time_shift

    def available_end(self):
        return self.source_times()[-1]


class HRRR(DynamicalProduct):
    name = "hrrr"
    title = "NOAA HRRR analysis"
    freq = "1h"
    start = pd.Timestamp("2014-10-01")
    bucket, prefix = "dynamical-noaa-hrrr", "noaa-hrrr-analysis/v0.2.0.icechunk"
    source = "dynamical.org noaa-hrrr-analysis v0.2.0 Icechunk (s3://dynamical-noaa-hrrr)"
    notes = ("3 km CONUS analysis (f00). Precipitation is the 0-1 h forecast of the previous hour's run. "
             "Shortwave is the instantaneous analysis-time flux. Many hours missing before 2018-08.")
    site_workers = 8
    variables = {
        "tair": Var(["temperature_2m"], "temp", "degC", None, {"desc": "2 m temperature (instantaneous)", "height_m": 2}),
        "tdew": Var(["dew_point_temperature_2m"], "temp", "degC", None, {"desc": "2 m dewpoint (instantaneous)"}),
        "rh": Var(["relative_humidity_2m"], "rh", "%", None, {"desc": "2 m RH (instantaneous)"}),
        "vpd": Var(["temperature_2m", "relative_humidity_2m"], "vpd", "kPa",
                   lambda temperature_2m, relative_humidity_2m: vpd_kpa(temperature_2m, relative_humidity_2m), {}),
        "pr": Var(["precipitation_surface"], "precip", "mm", lambda precipitation_surface: np.maximum(precipitation_surface, 0) * 3600,
                  {"desc": "precipitation over the hour ending at stamp (0-1 h forecast)"}),
        "ps": Var(["pressure_surface"], "pres", "Pa", None, {}),
        "wind": Var(["wind_u_10m", "wind_v_10m"], "wind", "m s-1", lambda wind_u_10m, wind_v_10m: np.hypot(wind_u_10m, wind_v_10m),
                    {"desc": "10 m wind speed", "height_m": 10}),
        "sw": Var(["downward_short_wave_radiation_flux_surface"], "rad", "W m-2",
                  lambda downward_short_wave_radiation_flux_surface: np.clip(downward_short_wave_radiation_flux_surface, 0, 1400),
                  {"desc": "downward shortwave, instantaneous at stamp", "instantaneous": True}),
        "swe": Var(["snow_water_equivalent_surface"], "swe", "mm", lambda snow_water_equivalent_surface: snow_water_equivalent_surface * 1000, {}),
        "snowd": Var(["snow_thickness_surface"], "snowd", "m", None, {}),
    }

    @functools.cached_property
    def crs(self):
        return pyproj.CRS.from_wkt(self.group["spatial_ref"].attrs["crs_wkt"])

    def grid(self):
        fwd = pyproj.Transformer.from_crs("EPSG:4326", self.crs, always_xy=True)
        inv = pyproj.Transformer.from_crs(self.crs, "EPSG:4326", always_xy=True)

        def to_yx(lat, lon):
            x, y = fwd.transform(lon, lat)
            return y, x

        def to_latlon(y, x):
            lon, lat = inv.transform(x, y)
            return lat, lon

        return Grid(self.group["y"][:], self.group["x"][:], to_yx=to_yx, to_latlon=to_latlon)


class CHIRPS3(DynamicalProduct):
    name = "chirps3"
    title = "CHIRPS v3 (final, rnl)"
    freq = "1d"
    start = pd.Timestamp("1981-01-01")
    revision_window = pd.Timedelta(days=0)
    bucket, prefix = "dynamical-ucsb-chc-chirps", "ucsb-chc-chirps-analysis-final/v0.1.0.icechunk"
    source = "dynamical.org ucsb-chc-chirps-analysis-final v0.1.0 Icechunk"
    notes = "0.05 deg land-only daily precipitation; pentad totals split to days with ERA5 (rnl variant). UTC days."
    variables = {
        "pr": Var(["precipitation_surface"], "precip", "mm", lambda precipitation_surface: np.maximum(precipitation_surface, 0) * 86400,
                  {"desc": "daily precipitation, UTC day", "day_end_offset_h": 24}),
    }

    def grid(self):
        return Grid(self.group["latitude"][:], self.group["longitude"][:], x_periodic=360.0)


class IMERGLate(DynamicalProduct):
    name = "imerg_late"
    title = "IMERG Late V07"
    freq = "30min"
    start = pd.Timestamp("1998-01-01")
    bucket, prefix = "dynamical-nasa-imerg", "nasa-imerg-analysis-late/v0.1.0.icechunk"
    source = "dynamical.org nasa-imerg-analysis-late v0.1.0 Icechunk"
    notes = "Half-hourly IMERG Late Run V07 (not the gauge-adjusted Final run). Stamped at the end of each half hour."
    site_workers = 2  # each 1440x100x100 chunk decodes to 57 MB; 8 parallel sites ran out of memory
    time_shift = pd.Timedelta(minutes=30)  # source stamps the start of the half hour
    variables = {
        "pr": Var(["precipitation_surface"], "precip", "mm", lambda precipitation_surface: np.maximum(precipitation_surface, 0) * 1800,
                  {"desc": "precipitation over the half hour ending at stamp"}),
    }

    def grid(self):
        return Grid(self.group["latitude"][:], self.group["longitude"][:], x_periodic=360.0)
