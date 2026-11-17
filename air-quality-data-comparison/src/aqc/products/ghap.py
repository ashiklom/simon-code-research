"""GHAP GlobalHighPM2.5 V2 (Wei et al. 2023, Nat. Commun. 14:8349), Zenodo, open access.

Per-year Zenodo records hold monthly zips of daily files and monthly NetCDFs:

    https://zenodo.org/api/records/<rec>/files/GHAP_PM2.5_D1K_YYYYMM_V2.zip/content   (~3 GB)
        GHAP_PM2.5_D1K_YYYYMMDD_V2.nc members, STORED (uncompressed), ~100 MB each
    https://zenodo.org/api/records/<rec>/files/GHAP_PM2.5_M1K_YYYYMM_V2.nc/content    (~80 MB)

Variable ``PM2.5`` (uint16 x 0.1 ug m-3, fill 65535), 0.01 deg global land grid (lat 90 ->
-89.99, lon -180 -> 179.99), chunks 180x360. Daily values are 24-h UTC means, labelled at the
date (00:00). Zenodo allows ~133 requests/min for anonymous clients, so a daily member is
fetched with ONE range request into memory and its chunks are read locally; the central
directory of each monthly zip is read once. Ground monitors (OpenAQ, EPA, EEA, CNEMC, ...)
are used in training, so GHAP is not independent of station data.
"""

from __future__ import annotations

import functools
import io
import struct
import threading
import time
import zipfile

import fsspec
import h5py
import numpy as np
import pandas as pd

from ..http import session
from .base import FieldProduct, Grid, Var, sample_field

ZEN = "https://zenodo.org/api/records"
RECORDS = {  # GlobalHighPM2.5 (YYYY) records, version 2 (published 2026-08)
    2017: 21882427, 2018: 21881606, 2019: 21874560, 2020: 21873781, 2021: 21851962, 2022: 18444913,
}
_lock = threading.Lock()
_last = [0.0]


def _throttle(min_interval: float = 0.5):
    """Keep well under Zenodo's 133 requests/min for anonymous clients."""
    with _lock:
        dt = time.time() - _last[0]
        if dt < min_interval:
            time.sleep(min_interval - dt)
        _last[0] = time.time()


def _get(url: str, rng: tuple[int, int] | None = None) -> bytes:
    for attempt in range(8):
        _throttle()
        h = {"Range": f"bytes={rng[0]}-{rng[1]}"} if rng else {}
        r = session().get(url, headers=h, timeout=1800)
        if r.status_code == 429:
            time.sleep(int(r.headers.get("retry-after", 60)) + 1)
            continue
        r.raise_for_status()
        return r.content
    raise RuntimeError(f"Zenodo throttled: {url}")


def d1k_url(m: pd.Timestamp) -> str:
    return f"{ZEN}/{RECORDS[m.year]}/files/GHAP_PM2.5_D1K_{m:%Y%m}_V2.zip/content"


def m1k_url(m: pd.Timestamp) -> str:
    return f"{ZEN}/{RECORDS[m.year]}/files/GHAP_PM2.5_M1K_{m:%Y%m}_V2.nc/content"


@functools.lru_cache(maxsize=4)
def _members(month: pd.Timestamp) -> dict[str, tuple[int, int]]:
    """member name -> (data offset, size) for a monthly daily zip."""
    _throttle()
    with fsspec.open(d1k_url(month), block_size=2**16, cache_type="none").open() as f:
        z = zipfile.ZipFile(f)
        out = {}
        for i in z.infolist():
            if i.compress_type != zipfile.ZIP_STORED:
                raise ValueError(f"{i.filename}: compressed member")
            f.seek(i.header_offset)
            n, m = struct.unpack("<HH", f.read(30)[26:30])
            out[i.filename] = (i.header_offset + 30 + n + m, i.file_size)
        return out


def _sample_h5(buf: bytes, st) -> np.ndarray:
    """(nsite, 4) PM2.5 from an in-memory GHAP NetCDF."""
    with h5py.File(io.BytesIO(buf), "r") as h:
        d = h["PM2.5"]
        iy, ix = st.px_index()
        ok = iy >= 0
        out = np.full(iy.shape, np.nan)
        # read each needed chunk-row band once (bounded memory), then sample
        cy, cx = d.chunks[-2:]
        keys = sorted({(int(a) // cy, int(b) // cx) for a, b in zip(iy[ok], ix[ok])})
        for a, b in keys:
            blk = d[0, a * cy:(a + 1) * cy, b * cx:(b + 1) * cx] if d.ndim == 3 else d[a * cy:(a + 1) * cy, b * cx:(b + 1) * cx]
            m = ok & (iy // cy == a) & (ix // cx == b)
            v = blk[iy[m] - a * cy, ix[m] - b * cx].astype("f8")
            v[v == 65535] = np.nan
            out[m] = v * 0.1
    return out


class _GHAP(FieldProduct):
    freq = "1d"
    start = pd.Timestamp("2018-01-01")

    def grid(self) -> Grid:
        lat = np.round(90 - 0.01 * np.arange(18000), 3)
        lon = np.round(-180 + 0.01 * np.arange(36000), 3)
        return Grid(y=lat, x=lon, x_periodic=360.0)

    def available_end(self) -> pd.Timestamp:
        y = max(RECORDS)
        return pd.Timestamp(f"{y}-12-31")


class GHAP(_GHAP):
    name = "ghap"
    title = "GHAP GlobalHighPM2.5 V2 daily 1 km"
    block_workers = 3  # ~100 MB in memory per in-flight day
    source = "Zenodo GlobalHighPM2.5 per-year records (D1K monthly zips), one range request per day"
    notes = "0.01 deg daily (UTC day) PM2.5 over land; ML trained on ground monitors (not independent)"
    variables = {"pm25": Var(["pm25"], "pm", "ug m-3", attrs={"day_def": "UTC day"})}

    def blocks(self, t0, t1):
        return [d for d in pd.date_range(pd.Timestamp(t0).normalize(), t1, freq="D") if d.year in RECORDS]

    def read_block(self, d, st):
        mem = _members(d.replace(day=1))
        name = f"GHAP_PM2.5_D1K_{d:%Y%m%d}_V2.nc"
        if name not in mem:
            raise FileNotFoundError(name)
        off, size = mem[name]
        buf = _get(d1k_url(d), (off, off + size - 1))
        return pd.DatetimeIndex([d]), {"pm25": _sample_h5(buf, st)[..., None]}


class GHAPMonthly(_GHAP):
    name = "ghap_m"
    title = "GHAP GlobalHighPM2.5 V2 monthly 1 km"
    block_workers = 2
    source = "Zenodo GlobalHighPM2.5 per-year records (M1K monthly NetCDF)"
    notes = "0.01 deg monthly PM2.5 labelled at the 1st of the month; ML trained on ground monitors"
    variables = {"pm25": Var(["pm25"], "pm", "ug m-3", attrs={"period": "month"})}

    def blocks(self, t0, t1):
        return [m for m in pd.date_range(pd.Timestamp(t0).replace(day=1).normalize(), t1, freq="MS") if m.year in RECORDS]

    def read_block(self, m, st):
        buf = _get(m1k_url(m))
        return pd.DatetimeIndex([m]), {"pm25": _sample_h5(buf, st)[..., None]}
