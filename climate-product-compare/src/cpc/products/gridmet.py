"""gridMET (Abatzoglou 2013) daily, from the Northwest Knowledge THREDDS OPeNDAP aggregations.

One OPeNDAP request per site and variable returns the 2x2 stencil for the full period. Days
end at 07 UTC on the following calendar day (midnight MST), i.e. day_end_offset_h = 31.
"""

from __future__ import annotations

import functools

import numpy as np
import pandas as pd

from .. import dap
from ..physics import K0
from .base import Block, Grid, Product, Var, bounded_map

URL = "https://thredds.northwestknowledge.net/thredds/dodsC/agg_met_{v}_1979_CurrentYear_CONUS.nc"
# short name -> (DAP variable, scale, offset, fill)
SRC = {
    "tmmx": ("daily_maximum_temperature", 0.1, 220.0),
    "tmmn": ("daily_minimum_temperature", 0.1, 210.0),
    "pr": ("precipitation_amount", 0.1, 0.0),
    "rmax": ("daily_maximum_relative_humidity", 0.1, 0.0),
    "rmin": ("daily_minimum_relative_humidity", 0.1, 0.0),
    "sph": ("daily_mean_specific_humidity", 1e-5, 0.0),
    "srad": ("daily_mean_shortwave_radiation_at_surface", 0.1, 0.0),
    "vs": ("daily_mean_wind_speed", 0.1, 0.0),
    "vpd": ("daily_mean_vapor_pressure_deficit", 0.01, 0.0),
}
DAY = {"day_end_offset_h": 31}


class GridMET(Product):
    name = "gridmet"
    title = "gridMET"
    freq = "1d"
    start = pd.Timestamp("1979-01-01")
    revision_window = pd.Timedelta(days=60)
    source = "Northwest Knowledge THREDDS OPeNDAP agg_met_<var>_1979_CurrentYear_CONUS"
    notes = "1/24 deg daily; days end 07 UTC next day (midnight MST). Last ~60 days provisional."
    site_workers = 4
    variables = {
        "tmax": Var(["tmmx"], "temp", "degC", lambda tmmx: tmmx - K0, {**DAY, "desc": "daily max 2 m temperature"}),
        "tmin": Var(["tmmn"], "temp", "degC", lambda tmmn: tmmn - K0, {**DAY, "desc": "daily min 2 m temperature"}),
        "pr": Var(["pr"], "precip", "mm", None, {**DAY, "desc": "daily precipitation"}),
        "rhmax": Var(["rmax"], "rh", "%", None, {**DAY}),
        "rhmin": Var(["rmin"], "rh", "%", None, {**DAY}),
        "q": Var(["sph"], "q", "g kg-1", lambda sph: sph * 1000, {**DAY, "desc": "daily mean specific humidity"}),
        "sw": Var(["srad"], "rad", "W m-2", None, {**DAY, "desc": "daily mean downward shortwave"}),
        "wind": Var(["vs"], "wind", "m s-1", None, {**DAY, "height_m": 10, "desc": "daily mean 10 m wind speed"}),
        "vpd": Var(["vpd"], "vpd", "kPa", None, {**DAY, "desc": "daily mean VPD"}),
    }

    @functools.cached_property
    def coords(self):
        u = URL.format(v="tmmx")
        n = dap.dds_shape(u, "daily_maximum_temperature")
        lat = dap.ascii_array(u, "lat", [(0, n[1] - 1)])
        lon = dap.ascii_array(u, "lon", [(0, n[2] - 1)])
        day = dap.ascii_array(u, "day", [(0, n[0] - 1)])
        return lat, lon, pd.Timestamp("1900-01-01") + pd.to_timedelta(day, unit="D")

    def grid(self):
        lat, lon, _ = self.coords
        return Grid(lat, lon)

    def available_end(self):
        return self.coords[2][-1]

    def fetch(self, sites, st, t0, t1):
        times = self.coords[2]
        it0, it1 = int(times.searchsorted(t0)), int(times.searchsorted(t1, side="right")) - 1
        if it1 < it0:
            return
        tsel = times[it0:it1 + 1]

        def one(k):
            iy, ix = st.iy[k], st.ix[k]
            y0, y1, x0, x1 = iy.min(), iy.max(), ix.min(), ix.max()
            raw = {}
            for short, (dv, sc, off) in SRC.items():
                a = dap.ascii_array(URL.format(v=short), dv, [(it0, it1), (y0, y1), (x0, x1)])
                a = np.where(a >= 32767, np.nan, a * sc + off)
                # reorder box (t, ny, nx) to stencil order
                yy = (iy - y0)[[0, 0, 1, 1]]
                xx = (ix - x0)[[0, 1, 0, 1]]
                raw[short] = a[:, yy, xx].T
            return k, self.convert_all(raw)

        for k, data in bounded_map(one, range(len(sites)), self.site_workers):
            yield Block([sites.site_id.iloc[k]], tsel, {v: a[None] for v, a in data.items()})
