"""MERRA-2 hourly: NASA POWER's native-grid MERRA-2 Zarr + Giovanni for SWGDN.

POWER stamps the MERRA-2 hourly mean for HH:00-HH+1:00 at HH (verified identical to the
GES DISC values stamped HH:30), so we shift by +1 h to end-of-interval. POWER converts units
(degC, hPa, mm/hour, g/kg, cm). Soil moisture is available only as wetness (fraction of
saturation): fine for anomaly correlation.
"""

from __future__ import annotations

import functools

import numpy as np
import pandas as pd
import zarr
from zarr.storage import FsspecStore

from .. import giovanni
from .base import Block, ChunkedStoreProduct, Grid, Var, bounded_map

# Catchment model soil temperature layers (cm), GEOS file spec
TSOIL = [(0, 9.88), (9.88, 29.4), (29.4, 68), (68, 144.4), (144.4, 294.5), (294.5, 1294.5)]


def _ident(name):
    return lambda **a: a[name]


class MERRA2(ChunkedStoreProduct):
    name = "merra2"
    title = "MERRA-2"
    freq = "1h"
    start = pd.Timestamp("1980-12-31 01:00")
    revision_window = pd.Timedelta(0)
    source = "NASA POWER MERRA-2 hourly Zarr (s3://nasa-power/merra2/temporal) + Giovanni API (M2T1NXRAD SWGDN)"
    notes = "0.5x0.625 deg; hourly means stamped at end of hour. PRECTOTCORR is gauge-corrected (CPC) over land."
    site_workers = 6
    variables = {
        "tair": Var(["T2M"], "temp", "degC", None, {"desc": "2 m temperature, hour mean", "height_m": 2}),
        "tdew": Var(["T2MDEW"], "temp", "degC", None, {"desc": "2 m dewpoint, hour mean"}),
        "rh": Var(["RH2M"], "rh", "%", None, {}),
        "q": Var(["QV2M"], "q", "g kg-1", None, {}),
        "vpd": Var(["T2M", "RH2M"], "vpd", "kPa", None, {}),
        "pr": Var(["PRECTOTCORR"], "precip", "mm", lambda PRECTOTCORR: np.maximum(PRECTOTCORR, 0), {"desc": "bias-corrected total precipitation"}),
        "ps": Var(["PS"], "pres", "Pa", lambda PS: PS * 100, {}),
        "wind": Var(["WS10M"], "wind", "m s-1", None, {"height_m": 10, "desc": "10 m wind speed"}),
        "wind2m": Var(["WS2M"], "wind", "m s-1", None, {"height_m": 2, "desc": "2 m wind speed"}),
        "tsurf": Var(["TS"], "temp", "degC", None, {"desc": "skin temperature"}),
        "sw": Var(["SWGDN"], "rad", "W m-2", None, {"desc": "surface incoming shortwave, hour mean (Giovanni)"}),
        "wet_top": Var(["GWETTOP"], "frac", "1", None, {"desc": "surface soil wetness (0-5 cm)", "depth_top_cm": 0, "depth_bot_cm": 5, "wetness": True}),
        "wet_root": Var(["GWETROOT"], "frac", "1", None, {"desc": "root zone soil wetness (0-100 cm)", "depth_top_cm": 0, "depth_bot_cm": 100, "wetness": True}),
        "snowd": Var(["SNODP"], "snowd", "m", lambda SNODP: SNODP / 100, {}),
        **{f"tsoil{i}": Var([f"TSOIL{i}"], "temp", "degC", None, {"depth_top_cm": a, "depth_bot_cm": b, "desc": f"soil temperature layer {i}"})
           for i, (a, b) in enumerate(TSOIL[:5], 1)},
    }

    def __init__(self):
        from ..physics import vpd_kpa

        self.variables = dict(self.variables)
        self.variables["vpd"] = Var(["T2M", "RH2M"], "vpd", "kPa", lambda T2M, RH2M: vpd_kpa(T2M, RH2M), {})

    @functools.cached_property
    def group(self):
        st = FsspecStore.from_url("s3://nasa-power/merra2/temporal/power_merra2_hourly_temporal_utc.zarr",
                                  storage_options={"anon": True}, read_only=True)
        return zarr.open_group(st, mode="r", zarr_format=2, use_consolidated=True)

    def grid(self):
        return Grid(self.group["lat"][:], self.group["lon"][:], x_periodic=360.0)

    def arrays(self):
        return {s: self.group[s] for v in self.variables.values() for s in v.src if s in self.group}

    @functools.cache
    def source_times(self):
        t = self.group["time"]
        units = t.attrs["units"]
        step, ref = units.split(" since ")
        return pd.Timestamp(ref) + pd.to_timedelta(t[:], unit={"hours": "h", "minutes": "min", "seconds": "s", "days": "D"}[step]) + pd.Timedelta(hours=1)

    @functools.cache
    def available_end(self):
        # array is pre-allocated to 2029; find the last valid hour at one land point
        t = self.source_times()
        a = self.group["T2M"]
        ct = a.chunks[0]
        guess = int(t.searchsorted(pd.Timestamp.now()))
        i0 = max(0, (guess // ct - 1) * ct)
        col = a[i0:min(len(t), i0 + 2 * ct), 250, 120]
        ok = np.nonzero(~np.isnan(col))[0]
        return t[i0 + ok[-1]]

    def fetch(self, sites, st, t0, t1):
        times = self.source_times()
        it0, it1 = int(times.searchsorted(t0)), int(times.searchsorted(t1, side="right"))
        if it1 <= it0:
            return
        tsel = times[it0:it1]
        arrays = self.arrays()
        g = self.grid()
        plat, plon = g.px_latlon(st)

        def one(k):
            iy, ix = st.iy[k], st.ix[k]
            raw = {s: self.read_box(a, it0, it1, iy, ix) for s, a in arrays.items()}
            sw = np.full((4, len(tsel)), np.nan)
            for p in range(4):
                s = giovanni.series("M2T1NXRAD_5_12_4_SWGDN", plat[k, p], plon[k, p],
                                    tsel[0] - pd.Timedelta(hours=1), tsel[-1])
                s.index = s.index + pd.Timedelta(minutes=30)  # HH:30 centre -> end of hour
                sw[p] = s.reindex(tsel).values
            raw["SWGDN"] = sw
            return k, self.convert_all(raw)

        for k, data in bounded_map(one, range(len(sites)), self.site_workers):
            yield Block([sites.site_id.iloc[k]], tsel, {v: a[None] for v, a in data.items()})
