"""WashU ACAG satellite-derived PM2.5 (van Donkelaar/Martin group), public S3 ``satpmdata``.

    V6GL03/CNNPM25/Monthly/GL/V6GL03.CNNPM25.GL.YYYYMM-YYYYMM.nc   global 0.01 deg PM2.5 (60S-70N)
    V6NA01/CNN<SP>/Monthly/V6NA01.CNNPM25.<SP>.YYYYMM-YYYYMM.nc    North America 0.01 deg PM2.5
                                                                    and composition (10N-70N, 170W-40W)

Anonymous HTTPS (https://satpmdata.s3.amazonaws.com). Files are NetCDF4/HDF5 (shuffle +
deflate, ~4 MB compressed chunks, ~450 MB per global month). Only the chunks that hold site
stencils are fetched, with parallel HTTP range requests decoded here (h5py serializes I/O).
Monthly means, labelled at the first day of the month (00:00 UTC) on a daily axis, attr
``period=month``: use at monthly scale only. Calibrated to ground monitors (not independent).
The NA grid is the global grid shifted by (7000 rows, 1000 cols).
"""

from __future__ import annotations

import functools
import zlib
from concurrent.futures import ThreadPoolExecutor

import fsspec
import h5py
import numpy as np
import pandas as pd

from ..http import session
from .base import FieldProduct, Grid, Var

BASE = "https://satpmdata.s3.amazonaws.com"
NA_SPECIES = {"PM25": "pm25_na", "SO4": "pm25_so4", "NO3": "pm25_no3", "NH4": "pm25_nh4", "OM": "pm25_om",
              "BC": "pm25_bc", "DUST": "pm25_dust", "SS": "pm25_ss"}
NA_DY, NA_DX = 7000, 1000  # NA (lat 10.005.., lon -169.995..) inside the GL grid (lat -59.995.., lon -179.995..)


def gl_url(m: pd.Timestamp) -> str:
    return f"{BASE}/V6GL03/CNNPM25/Monthly/GL/V6GL03.CNNPM25.GL.{m:%Y%m}-{m:%Y%m}.nc"


def na_url(sp: str, m: pd.Timestamp) -> str:
    return f"{BASE}/V6NA01/CNN{sp}/Monthly/V6NA01.CNNPM25.{sp}.{m:%Y%m}-{m:%Y%m}.nc"


def _exists(url: str) -> bool:
    return session().head(url, timeout=60).status_code == 200


def read_points(url: str, var: str, iy: np.ndarray, ix: np.ndarray, workers: int = 16) -> np.ndarray:
    """Values of `var` at integer pixel indices (iy, ix) (any shape; -1 = missing) via chunk range reads."""
    with fsspec.open(url, block_size=2**16, cache_type="none").open() as f:
        h = h5py.File(f, "r")
        d = h[var]
        cy, cx = d.chunks
        ny, nx = d.shape
        fill = d.fillvalue
        shuffle = d.shuffle
        ok = (iy >= 0) & (iy < ny) & (ix >= 0) & (ix < nx)
        keys = sorted({(int(a) // cy, int(b) // cx) for a, b in zip(iy[ok], ix[ok])})
        info = {k: d.id.get_chunk_info_by_coord((k[0] * cy, k[1] * cx)) for k in keys}
    out = np.full(iy.shape, np.nan)

    def fetch(k):
        ci = info[k]
        r = session().get(url, headers={"Range": f"bytes={ci.byte_offset}-{ci.byte_offset + ci.size - 1}"}, timeout=300)
        r.raise_for_status()
        raw = np.frombuffer(zlib.decompress(r.content), dtype=np.uint8)
        if shuffle:
            raw = raw.reshape(4, -1).T.reshape(-1)
        return k, raw.view("<f4").reshape(cy, cx)

    with ThreadPoolExecutor(workers) as ex:
        for (a, b), blk in ex.map(fetch, keys):
            m = ok & (iy // cy == a) & (ix // cx == b)
            v = blk[iy[m] - a * cy, ix[m] - b * cx].astype("f8")
            v[(v == fill) | (np.abs(v) > 1e30)] = np.nan
            out[m] = v
    return out


class ACAG(FieldProduct):
    name = "acag"
    title = "ACAG V6.GL.03 (+V6.NA.01 composition)"
    freq = "1d"
    start = pd.Timestamp("2018-01-01")
    block_workers = 2
    source = "s3://satpmdata (WashU ACAG; V6GL03 global, V6NA01 North America composition), anonymous"
    notes = "0.01 deg monthly means labelled at the 1st of the month; CNN calibrated to ground monitors"
    variables = {
        "pm25": Var(["pm25"], "pm", "ug m-3", attrs={"period": "month"}),
        **{v: Var([v], "pm" if v == "pm25_na" else "spec", "ug m-3", attrs={"period": "month"})
           for v in NA_SPECIES.values()},
    }

    def grid(self) -> Grid:
        lat = np.round(-59.995 + 0.01 * np.arange(13000), 3)
        lon = np.round(-179.995 + 0.01 * np.arange(36000), 3)
        return Grid(y=lat, x=lon, x_periodic=360.0)

    @functools.cached_property
    def _ends(self) -> tuple[pd.Timestamp, pd.Timestamp]:
        def last(fn, m):
            while m >= pd.Timestamp("2018-01-01"):
                if _exists(fn(m)):
                    return m
                m -= pd.offsets.MonthBegin(1)
            return None
        now = pd.Timestamp.now().normalize().replace(day=1)
        return last(gl_url, now), last(lambda m: na_url("PM25", m), now)

    def available_end(self) -> pd.Timestamp:
        return max(e for e in self._ends if e is not None)

    def blocks(self, t0, t1):
        return list(pd.date_range(pd.Timestamp(t0).replace(day=1).normalize(), t1, freq="MS"))

    def read_block(self, m, st):
        iy, ix = st.px_index()
        out = {}
        gl_end, na_end = self._ends
        if gl_end is not None and m <= gl_end:
            out["pm25"] = read_points(gl_url(m), "PM25", iy, ix)
        if na_end is not None and m <= na_end:
            jy, jx = iy - NA_DY, ix - NA_DX
            jy = np.where(iy < 0, -1, jy)
            for sp, v in NA_SPECIES.items():
                try:
                    out[v] = read_points(na_url(sp, m), sp, jy, jx)
                except FileNotFoundError:
                    pass
        if not out:
            raise FileNotFoundError(m)
        nan = np.full(iy.shape, np.nan)
        raw = {k: out.get(k, nan)[..., None] for k in ["pm25", *NA_SPECIES.values()]}
        return pd.DatetimeIndex([m]), raw
