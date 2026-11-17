"""GEOS-FP aerosol diagnostics (tavg3_2d_aer_Nx) from the NCCS HTTPS data portal (no login).

    https://portal.nccs.nasa.gov/datashare/gmao/geos-fp/das/Y<Y>/M<m>/D<d>/
        GEOS.fp.asm.tavg3_2d_aer_Nx.<YYYYmmdd>_<HH>30.V01.nc4     HH = 01, 04, ..., 22

The portal carries aerosols only as 3-hourly means (the hourly tavg1_2d_aer_Nx is only on the
OPeNDAP GDS, which returns uncompressed data and is no cheaper). Files are centred at HH:30
and cover HH-1:30 .. HH+1:30, i.e. 00-03, 03-06, ... UTC -> stamped at the END (03, 06, ...).
Each variable is one full-field chunk, read with ``h5remote.read_vars``.

Same PM definitions as MERRA-2 (GOCART, dry): PM2.5 = DU25+SS25+BC+1.4*OC+SO4*132.14/96.06,
PM10 with full-size dust and sea salt. GEOS-FP also carries nitrate (NISMASS25), stored
separately as pm25_no3 and NOT added to pm25 (so pm25 matches MERRA-2's definition).
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .. import http
from .base import Block, FieldProduct, Grid, Var, bounded_map, sample_field, scale, total
from .h5remote import read_vars
from .merra2 import KG2UG, SO4_TO_AS

BASE = "https://portal.nccs.nasa.gov/datashare/gmao/geos-fp/das"
FILE = "{base}/Y{t:%Y}/M{t:%m}/D{t:%d}/GEOS.fp.asm.tavg3_2d_aer_Nx.{t:%Y%m%d_%H}30.V01.nc4"
LAT = -90 + 0.25 * np.arange(721)
LON = -180 + 0.3125 * np.arange(1152)
_spec = scale(KG2UG)


class GEOSFPAer(FieldProduct):
    name = "geosfp_aer"
    title = "GEOS-FP aerosols (tavg3_2d_aer_Nx)"
    freq = "3h"
    start = pd.Timestamp("2025-08-01 03:00")
    file_workers = 6
    source = "NCCS HTTPS portal GEOS.fp.asm.tavg3_2d_aer_Nx (range reads)"
    notes = ("0.25x0.3125 deg, 3-hourly means; GOCART dry mass, PM2.5 = DU25+SS25+BC+1.4*OC+SO4*132.14/96.06 "
             "(nitrate stored separately); MODIS AOD assimilated, no surface PM")
    variables = {
        "pm25": Var(["DUSMASS25", "SSSMASS25", "BCSMASS", "OCSMASS", "SO4SMASS"], "pm", "ug m-3",
                    total(DUSMASS25=KG2UG, SSSMASS25=KG2UG, BCSMASS=KG2UG, OCSMASS=1.4 * KG2UG,
                          SO4SMASS=SO4_TO_AS * KG2UG), {"rh_basis": "dry", "oc_factor": 1.4}),
        "pm10": Var(["DUSMASS", "SSSMASS", "BCSMASS", "OCSMASS", "SO4SMASS"], "pm", "ug m-3",
                    total(DUSMASS=KG2UG, SSSMASS=KG2UG, BCSMASS=KG2UG, OCSMASS=1.4 * KG2UG,
                          SO4SMASS=SO4_TO_AS * KG2UG), {"rh_basis": "dry", "oc_factor": 1.4}),
        "pm25_du": Var(["DUSMASS25"], "spec", "ug m-3", _spec),
        "pm10_du": Var(["DUSMASS"], "spec", "ug m-3", _spec),
        "pm25_ss": Var(["SSSMASS25"], "spec", "ug m-3", _spec),
        "pm10_ss": Var(["SSSMASS"], "spec", "ug m-3", _spec),
        "pm25_bc": Var(["BCSMASS"], "spec", "ug m-3", _spec),
        "pm25_oc": Var(["OCSMASS"], "spec", "ug m-3", _spec),
        "pm25_so4": Var(["SO4SMASS"], "spec", "ug m-3", _spec),
        "pm25_no3": Var(["NISMASS25"], "spec", "ug m-3", _spec),
    }

    def grid(self) -> Grid:
        return Grid(LAT, LON, x_periodic=360.0)

    def available_end(self) -> pd.Timestamp:
        now = pd.Timestamp.now().floor("D")
        for back in range(0, 8):
            d = now - pd.Timedelta(days=back)
            r = http.session().get(f"{BASE}/Y{d:%Y}/M{d:%m}/D{d:%d}/", timeout=120)
            if r.status_code != 200:
                continue
            hrs = sorted(int(h) for h in re.findall(r"tavg3_2d_aer_Nx\.\d{8}_(\d{2})30\.V01\.nc4", r.text))
            if hrs:
                return d + pd.Timedelta(hours=hrs[-1] + 2)  # file HH:30 covers HH-1:30..HH+1:30
        raise RuntimeError("no recent GEOS-FP aer files found")

    def _read(self, args):
        t_end, st = args
        url = FILE.format(base=BASE, t=t_end - pd.Timedelta(hours=1.5))
        srcs = sorted({s for v in self.variables.values() for s in v.src})
        for attempt in range(5):
            try:
                a = read_vars(url, srcs, workers=4)
                break
            except FileNotFoundError:
                return None
            except Exception:
                if attempt == 4:
                    raise
        out = {s: sample_field(x, st).astype("f4") for s, x in a.items()}  # (nsite, 4, 1)
        del a
        return t_end, out

    def fetch(self, sites, st, t0, t1):
        ids = list(sites.site_id)
        steps = pd.date_range(max(t0, self.start).ceil("3h"), t1, freq="3h")
        # one Block per calendar month
        for _, grp in pd.Series(steps, index=steps).groupby(steps.to_period("M")):
            parts = [r for r in bounded_map(self._read, [(t, st) for t in grp], self.file_workers) if r is not None]
            if not parts:
                continue
            times = pd.DatetimeIndex([p[0] for p in parts])
            raw = {k: np.concatenate([p[1][k] for p in parts], axis=-1) for k in parts[0][1]}
            yield Block(ids, times, self.convert_all(raw))
