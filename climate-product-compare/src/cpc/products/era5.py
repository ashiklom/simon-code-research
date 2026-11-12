"""ERA5 single levels from Earthmover's free Icechunk copy (group single/temporal)."""

from __future__ import annotations

import functools

import icechunk
import numpy as np
import pandas as pd
import zarr

from ..physics import K0, rh_from_dewpoint, vpd_kpa
from .base import ChunkedStoreProduct, Grid, Var

G = 9.80665
SOIL_T = [(0, 7), (7, 28), (28, 100), (100, 289)]
SOIL_M = [(0, 7), (7, 28)]  # swvl3/4 are not in the Earthmover copy


def common_vars(t="t2m", d="d2m", tp="tp", sp="sp", u="u10", v="v10", ssrd="ssrd", skt="skt", stl="stl", swvl="swvl",
                n_sm=2, snow="sd", snow_kind="swe") -> dict[str, Var]:
    vs = {
        "tair": Var([t], "temp", "degC", lambda **a: a[t] - K0, {"desc": "2 m temperature (instantaneous)", "height_m": 2}),
        "tdew": Var([d], "temp", "degC", lambda **a: a[d] - K0, {"desc": "2 m dewpoint (instantaneous)"}),
        "rh": Var([t, d], "rh", "%", lambda **a: rh_from_dewpoint(a[t] - K0, a[d] - K0), {"desc": "RH from t2m, d2m"}),
        "vpd": Var([t, d], "vpd", "kPa", lambda **a: vpd_kpa(a[t] - K0, rh_from_dewpoint(a[t] - K0, a[d] - K0)), {}),
        "pr": Var([tp], "precip", "mm", lambda **a: np.maximum(a[tp], 0) * 1000, {"desc": "total precipitation over hour ending at stamp"}),
        "ps": Var([sp], "pres", "Pa", None, {"desc": "surface pressure"}),
        "wind": Var([u, v], "wind", "m s-1", lambda **a: np.hypot(a[u], a[v]), {"desc": "10 m wind speed", "height_m": 10}),
        "sw": Var([ssrd], "rad", "W m-2", lambda **a: np.maximum(a[ssrd], 0) / 3600, {"desc": "surface solar radiation downwards, hour mean"}),
        "tsurf": Var([skt], "temp", "degC", lambda **a: a[skt] - K0, {"desc": "skin temperature (instantaneous)"}),
    }
    for i, (top, bot) in enumerate(SOIL_T, 1):
        vs[f"tsoil{i}"] = Var([f"{stl}{i}"], "temp", "degC", (lambda name: (lambda **a: a[name] - K0))(f"{stl}{i}"),
                              {"desc": f"soil temperature layer {i}", "depth_top_cm": top, "depth_bot_cm": bot})
    for i, (top, bot) in enumerate((SOIL_T)[:n_sm], 1):
        vs[f"soilm{i}"] = Var([f"{swvl}{i}"], "sm", "m3 m-3", None,
                              {"desc": f"volumetric soil water layer {i}", "depth_top_cm": top, "depth_bot_cm": bot})
    if snow_kind == "swe":
        vs["swe"] = Var([snow], "swe", "mm", lambda **a: a[snow] * 1000, {"desc": "snow depth water equivalent"})
    else:
        vs["snowd"] = Var([snow], "snowd", "m", None, {"desc": "snow depth"})
    return vs


class ERA5(ChunkedStoreProduct):
    name = "era5"
    title = "ERA5"
    freq = "1h"
    start = pd.Timestamp("1940-01-01")
    source = "Earthmover free Icechunk s3://earthmover-icechunk-era5/icechunkV2 (single/temporal)"
    notes = "Final ERA5, quarterly updates. Instantaneous state variables; accumulations over the hour ending at the stamp."
    variables = common_vars()

    @functools.cached_property
    def group(self):
        st = icechunk.s3_storage(bucket="earthmover-icechunk-era5", prefix="icechunkV2", region="us-east-1", anonymous=True)
        s = icechunk.Repository.open(st).readonly_session("main")
        return zarr.open_group(s.store, mode="r", path="single/temporal")

    def grid(self):
        g = self.group
        return Grid(g["latitude"][:], g["longitude"][:], x_periodic=360.0, lon360=True)

    def elevation(self, st):
        z = self.group["z_sfc"]
        iy, ix = st.px_index()
        ok = iy >= 0
        out = np.full(iy.shape, np.nan)
        out[ok] = z.get_coordinate_selection((iy[ok], ix[ok])) / G
        return out

    def arrays(self):
        return {k: self.group[k] for k in ("t2m", "d2m", "tp", "sp", "u10", "v10", "ssrd", "skt", "stl1", "stl2", "stl3", "stl4",
                                           "swvl1", "swvl2", "sd")}

    @functools.cache
    def source_times(self):
        v = self.group["valid_time"][:]
        return pd.Timestamp("1940-01-01") + pd.to_timedelta(v, unit="h")

    def available_end(self):
        return self.source_times()[-1]
