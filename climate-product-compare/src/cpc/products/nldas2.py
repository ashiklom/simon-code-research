"""NLDAS-2 forcing and land-surface model outputs via the Giovanni time-series API.

Giovanni exposes only part of the LSM variable lists (see `notes`). Noah 10-40 cm soil
moisture is derived from the 0-100, 0-10 and 40-100 cm layers. Timestamps: Giovanni returns
the file hour; GES DISC V2.0 metadata puts the averaging/accumulation interval in the hour
ENDING at that time (verified separately by lag correlation against USCRN).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from .. import giovanni
from ..physics import K0, dewpoint_from_vp, esat_kpa, vp_from_q
from .base import Block, Grid, Product, Var, bounded_map

LAT = 25.0625 + 0.125 * np.arange(224)
LON = -124.9375 + 0.125 * np.arange(464)


def _k(name):
    return lambda **a: a[name] - K0


def _vol(name, mm):
    return lambda **a: a[name] / mm


class GiovanniProduct(Product):
    freq = "1h"
    start = pd.Timestamp("1979-01-02")
    prefix = ""
    time_shift = pd.Timedelta(0)
    site_workers = 2
    request_workers = 8

    def grid(self):
        return Grid(LAT, LON)

    def available_end(self):
        # probe the last few days at a central CONUS point
        now = pd.Timestamp.now().floor("h")
        src = next(iter(self.variables.values())).src[0]
        s = giovanni.series(f"{self.prefix}_{src}", 38.0625, -97.0625, now - pd.Timedelta(days=20), now)
        return s.dropna().index[-1] + self.time_shift

    def fetch(self, sites, st, t0, t1):
        tsel = pd.date_range(t0, t1, freq="h")
        g = self.grid()
        plat, plon = g.px_latlon(st)
        srcs = sorted({s for v in self.variables.values() for s in v.src})

        def one(k):
            tasks = [(s, p) for s in srcs for p in range(4)]

            def req(task):
                s, p = task
                ser = giovanni.series(f"{self.prefix}_{s}", plat[k, p], plon[k, p], t0 - self.time_shift, t1 - self.time_shift, max_years=20)
                ser.index = ser.index + self.time_shift
                return task, ser.reindex(tsel).values

            raw = {s: np.full((4, len(tsel)), np.nan) for s in srcs}
            with ThreadPoolExecutor(self.request_workers) as ex:
                for (s, p), vals in ex.map(req, tasks):
                    raw[s][p] = vals
            return k, self.convert_all(raw)

        for k, data in bounded_map(one, range(len(sites)), self.site_workers, ahead=self.site_workers):
            yield Block([sites.site_id.iloc[k]], tsel, {v: a[None] for v, a in data.items()})


def _forcing_vars():
    def q(**a):
        return a["Qair"] * 1000

    def td(**a):
        return dewpoint_from_vp(vp_from_q(a["Qair"], a["PSurf"]))

    def rh(**a):
        return np.clip(100 * vp_from_q(a["Qair"], a["PSurf"]) / esat_kpa(a["Tair"] - K0), 0, 100)

    def vpd(**a):
        return np.maximum(esat_kpa(a["Tair"] - K0) - vp_from_q(a["Qair"], a["PSurf"]), 0)

    return {
        "tair": Var(["Tair"], "temp", "degC", _k("Tair"), {"desc": "2 m temperature", "height_m": 2}),
        "q": Var(["Qair"], "q", "g kg-1", q, {}),
        "tdew": Var(["Qair", "PSurf"], "temp", "degC", td, {"desc": "dewpoint from Qair, PSurf"}),
        "rh": Var(["Tair", "Qair", "PSurf"], "rh", "%", rh, {}),
        "vpd": Var(["Tair", "Qair", "PSurf"], "vpd", "kPa", vpd, {}),
        "ps": Var(["PSurf"], "pres", "Pa", None, {}),
        "wind": Var(["Wind_E", "Wind_N"], "wind", "m s-1", lambda **a: np.hypot(a["Wind_E"], a["Wind_N"]), {"height_m": 10}),
        "sw": Var(["SWdown"], "rad", "W m-2", None, {"desc": "downward shortwave, hour mean"}),
        "pr": Var(["Rainf"], "precip", "mm", lambda **a: np.maximum(a["Rainf"], 0), {"desc": "total precipitation over hour"}),
    }


class NLDAS2Forcing(GiovanniProduct):
    name = "nldas2_forcing"
    title = "NLDAS-2 forcing"
    prefix = "NLDAS_FORA0125_H_2_0"
    source = "NASA Giovanni time-series API (NLDAS_FORA0125_H v2.0)"
    notes = "0.125 deg CONUS. Precip: CPC gauge daily totals disaggregated with Stage II/IV radar; other fields from NARR, SW bias-corrected."
    variables = _forcing_vars()


class NLDAS2Noah(GiovanniProduct):
    name = "nldas2_noah"
    title = "NLDAS-2 Noah"
    prefix = "NLDAS_NOAH0125_H_2_0"
    source = "NASA Giovanni time-series API (NLDAS_NOAH0125_H v2.0)"
    notes = "Noah LSM. Soil layers 0-10, 10-40, 40-100, 100-200 cm (10-40 derived from 0-100 minus the others)."
    variables = {
        "soilm1": Var(["SoilM_0_10cm"], "sm", "m3 m-3", _vol("SoilM_0_10cm", 100), {"depth_top_cm": 0, "depth_bot_cm": 10}),
        "soilm2": Var(["SoilM_0_100cm", "SoilM_0_10cm", "SoilM_40_100cm"], "sm", "m3 m-3",
                      lambda **a: (a["SoilM_0_100cm"] - a["SoilM_0_10cm"] - a["SoilM_40_100cm"]) / 300, {"depth_top_cm": 10, "depth_bot_cm": 40}),
        "soilm3": Var(["SoilM_40_100cm"], "sm", "m3 m-3", _vol("SoilM_40_100cm", 600), {"depth_top_cm": 40, "depth_bot_cm": 100}),
        "soilm4": Var(["SoilM_100_200cm"], "sm", "m3 m-3", _vol("SoilM_100_200cm", 1000), {"depth_top_cm": 100, "depth_bot_cm": 200}),
        "tsoil1": Var(["SoilT_0_10cm"], "temp", "degC", _k("SoilT_0_10cm"), {"depth_top_cm": 0, "depth_bot_cm": 10}),
        "tsoil2": Var(["SoilT_10_40cm"], "temp", "degC", _k("SoilT_10_40cm"), {"depth_top_cm": 10, "depth_bot_cm": 40}),
        "tsoil3": Var(["SoilT_40_100cm"], "temp", "degC", _k("SoilT_40_100cm"), {"depth_top_cm": 40, "depth_bot_cm": 100}),
        "tsoil4": Var(["SoilT_100_200cm"], "temp", "degC", _k("SoilT_100_200cm"), {"depth_top_cm": 100, "depth_bot_cm": 200}),
        "tsurf": Var(["AvgSurfT"], "temp", "degC", _k("AvgSurfT"), {"desc": "average surface skin temperature"}),
        "swe": Var(["SWE"], "swe", "mm", None, {}),
        "snowd": Var(["SnowDepth"], "snowd", "m", None, {}),
    }


class NLDAS2VIC(GiovanniProduct):
    name = "nldas2_vic"
    title = "NLDAS-2 VIC"
    prefix = "NLDAS_VIC0125_H_2_0"
    source = "NASA Giovanni time-series API (NLDAS_VIC0125_H v2.0)"
    notes = "VIC LSM. Layer 1 is 0-10 cm; layer 2 depth varies by cell (stored as water mass). AvgSurfT/SWE not served by Giovanni."
    variables = {
        "soilm1": Var(["SoilM_layer1"], "sm", "m3 m-3", _vol("SoilM_layer1", 100), {"depth_top_cm": 0, "depth_bot_cm": 10}),
        "soilw2": Var(["SoilM_layer2"], "swe", "kg m-2", None, {"desc": "layer 2 soil water (variable depth)", "wetness": True}),
        "tsoil1": Var(["SoilT_layer1"], "temp", "degC", _k("SoilT_layer1"), {"depth_top_cm": 0, "depth_bot_cm": 10}),
        "tsoil2": Var(["SoilT_layer2"], "temp", "degC", _k("SoilT_layer2"), {"desc": "layer 2 (variable depth)"}),
    }


class NLDAS2Mosaic(GiovanniProduct):
    name = "nldas2_mosaic"
    title = "NLDAS-2 Mosaic"
    prefix = "NLDAS_MOS0125_H_2_0"
    source = "NASA Giovanni time-series API (NLDAS_MOS0125_H v2.0)"
    notes = "Mosaic LSM. Soil layers 0-10, 10-40, 40-200 cm; single soil temperature. AvgSurfT/SWE not served by Giovanni."
    variables = {
        "soilm1": Var(["SoilM_0_10cm"], "sm", "m3 m-3", _vol("SoilM_0_10cm", 100), {"depth_top_cm": 0, "depth_bot_cm": 10}),
        "soilm2": Var(["SoilM_10_40cm"], "sm", "m3 m-3", _vol("SoilM_10_40cm", 300), {"depth_top_cm": 10, "depth_bot_cm": 40}),
        "soilm3": Var(["SoilM_40_200cm"], "sm", "m3 m-3", _vol("SoilM_40_200cm", 1600), {"depth_top_cm": 40, "depth_bot_cm": 200}),
        "tsoil1": Var(["SoilT"], "temp", "degC", _k("SoilT"), {"desc": "soil temperature (single layer)", "depth_top_cm": 0, "depth_bot_cm": 10}),
    }
