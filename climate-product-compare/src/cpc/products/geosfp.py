"""GEOS-FP assimilation (tavg1_2d_{slv,flx,rad,lnd}_Nx) from the NCCS HTTPS data portal.

Each hourly NetCDF4 file stores one full-field HDF5 chunk per variable, so we read the needed
variables over HTTP range requests (h5py + fsspec) and sample every site's stencil from the
field. tavg1 files are centred at HH:30 and cover HH:00-HH+1:00 -> stamped HH+1:00.
"""

from __future__ import annotations

import re
import fsspec
import h5py
import numpy as np
import pandas as pd

from .. import http
from ..parallel import process_map
from ..physics import K0, dewpoint_from_vp, esat_kpa, vp_from_q
from .base import Block, Grid, Product, Var

BASE = "https://portal.nccs.nasa.gov/datashare/gmao/geos-fp/das"
FILE = "{base}/Y{t:%Y}/M{t:%m}/D{t:%d}/GEOS.fp.asm.tavg1_2d_{c}_Nx.{t:%Y%m%d_%H}30.V01.nc4"
LAT = -90 + 0.25 * np.arange(721)
LON = -180 + 0.3125 * np.arange(1152)
COLLECTIONS = {
    "slv": ["T2M", "QV2M", "PS", "U2M", "V2M", "U10M", "V10M", "TS"],
    "flx": ["PRECTOT"],
    "rad": ["SWGDN"],
    "lnd": ["SFMC", "RZMC", "TSOIL1", "TSOIL2", "TSOIL3", "TSOIL4", "SNODP", "SNOMAS"],
}
TSOIL = [(0, 9.88), (9.88, 29.4), (29.4, 68), (68, 144.4)]


def _e(**a):
    return vp_from_q(a["QV2M"], a["PS"])


class GEOSFP(Product):
    name = "geosfp"
    title = "GEOS-FP (assimilation)"
    freq = "1h"
    start = pd.Timestamp("2025-11-01 01:00")
    source = "NCCS HTTPS portal, GEOS.fp.asm.tavg1_2d_{slv,flx,rad,lnd}_Nx (range reads)"
    notes = "GMAO forward-processing analysis, last ~12 months. GEOS 5.43 upgrade on 2026-02-26 06Z."
    hour_workers = 16
    block_days = 31  # each block rewrites every site's time chunk, so fewer, larger blocks are much faster
    variables = {
        "tair": Var(["T2M"], "temp", "degC", lambda **a: a["T2M"] - K0, {"height_m": 2, "desc": "2 m temperature, hour mean"}),
        "q": Var(["QV2M"], "q", "g kg-1", lambda **a: a["QV2M"] * 1000, {}),
        "tdew": Var(["QV2M", "PS"], "temp", "degC", lambda **a: dewpoint_from_vp(_e(**a)), {}),
        "rh": Var(["T2M", "QV2M", "PS"], "rh", "%", lambda **a: np.clip(100 * _e(**a) / esat_kpa(a["T2M"] - K0), 0, 100), {}),
        "vpd": Var(["T2M", "QV2M", "PS"], "vpd", "kPa", lambda **a: np.maximum(esat_kpa(a["T2M"] - K0) - _e(**a), 0), {}),
        "ps": Var(["PS"], "pres", "Pa", None, {}),
        "wind": Var(["U10M", "V10M"], "wind", "m s-1", lambda **a: np.hypot(a["U10M"], a["V10M"]), {"height_m": 10}),
        "wind2m": Var(["U2M", "V2M"], "wind", "m s-1", lambda **a: np.hypot(a["U2M"], a["V2M"]), {"height_m": 2}),
        "tsurf": Var(["TS"], "temp", "degC", lambda **a: a["TS"] - K0, {"desc": "surface skin temperature"}),
        "pr": Var(["PRECTOT"], "precip", "mm", lambda **a: np.maximum(a["PRECTOT"], 0) * 3600, {}),
        "sw": Var(["SWGDN"], "rad", "W m-2", None, {"desc": "surface incoming shortwave, hour mean"}),
        "soilm_top": Var(["SFMC"], "sm", "m3 m-3", None, {"depth_top_cm": 0, "depth_bot_cm": 5}),
        "soilm_root": Var(["RZMC"], "sm", "m3 m-3", None, {"depth_top_cm": 0, "depth_bot_cm": 100}),
        **{f"tsoil{i}": Var([f"TSOIL{i}"], "temp", "degC", (lambda n: (lambda **a: a[n] - K0))(f"TSOIL{i}"),
                            {"depth_top_cm": a, "depth_bot_cm": b}) for i, (a, b) in enumerate(TSOIL, 1)},
        "snowd": Var(["SNODP"], "snowd", "m", None, {}),
        "swe": Var(["SNOMAS"], "swe", "mm", None, {}),
    }

    def grid(self):
        return Grid(LAT, LON, x_periodic=360.0)

    def available_end(self):
        now = pd.Timestamp.now().floor("D")
        for back in range(0, 6):
            d = now - pd.Timedelta(days=back)
            r = http.session().get(f"{BASE}/Y{d:%Y}/M{d:%m}/D{d:%d}/", timeout=120)
            if r.status_code != 200:
                continue
            hrs = sorted(int(h) for h in re.findall(r"tavg1_2d_lnd_Nx\.\d{8}_(\d{2})30\.V01\.nc4", r.text))
            if hrs:
                return d + pd.Timedelta(hours=hrs[-1] + 1)
        raise RuntimeError("no recent GEOS-FP files found")

    def fetch(self, sites, st, t0, t1):
        iy, ix = st.px_index()  # (nsite, 4)
        hours = pd.date_range(max(t0, self.start), t1, freq="h")
        for b0 in range(0, len(hours), 24 * self.block_days):
            th = hours[b0:b0 + 24 * self.block_days]
            raw = {n: np.full((len(sites), 4, len(th)), np.nan) for ns in COLLECTIONS.values() for n in ns}
            for j, vals in enumerate(process_map(_read_hour, [(t, iy, ix) for t in th], self.hour_workers)):
                for n, v in vals.items():
                    raw[n][:, :, j] = v
            yield Block(list(sites.site_id), th, self.convert_all(raw))


def _read_hour(args) -> dict[str, np.ndarray]:
    """Read the needed variables of the 4 collections for the hour ending at t_end."""
    import time

    t_end, iy, ix = args
    tc = t_end - pd.Timedelta(hours=1)  # file hour (centre HH:30)
    out = {}
    for c, names in COLLECTIONS.items():
        url = FILE.format(base=BASE, t=tc, c=c)
        for attempt in range(5):
            try:
                with http.fsspec_open(url) as f, h5py.File(f, "r") as h:
                    for n in names:
                        v = h[n][0][iy, ix].astype("f8")
                        v[np.abs(v) > 1e14] = np.nan
                        out[n] = v
                break
            except FileNotFoundError:
                break
            except Exception:
                if attempt == 4:
                    raise
                time.sleep(3 * (attempt + 1))
    return out
