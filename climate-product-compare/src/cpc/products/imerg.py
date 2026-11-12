"""IMERG Final V07 (GES DISC) daily and half-hourly, via HTTPS range reads of the original files.

Files are resolved once through the Earthdata redirect to a signed CloudFront/S3 URL, then
only the HDF5 chunks covering the sites are read (half-hourly: 14.5 deg longitude strips;
daily: northern-hemisphere half). Arrays are (time, lon, lat). Half-hourly files are stamped
by start time -> we stamp the END of each half hour. Daily = UTC day.
"""

from __future__ import annotations

import functools
import re
import fsspec
import h5py
import numpy as np
import pandas as pd

from .. import http
from ..parallel import process_map
from .base import Block, Grid, Product, Var

BASE = "https://data.gesdisc.earthdata.nasa.gov/data/GPM_L3"
LAT = -89.95 + 0.1 * np.arange(1800)
LON = -179.95 + 0.1 * np.arange(3600)


def resolve(url: str) -> str:
    """Follow Earthdata redirects (with bearer auth) to the final signed URL."""
    h = http.earthdata_headers()
    u = url
    for _ in range(5):
        r = http.session().get(u, headers=h if "earthdata.nasa.gov" in u else {}, allow_redirects=False, stream=True, timeout=120)
        r.close()
        if r.status_code in (301, 302, 303, 307, 308):
            u = r.headers["Location"]
            continue
        if r.status_code == 404:
            raise FileNotFoundError(url)
        r.raise_for_status()
        return u
    raise RuntimeError(f"too many redirects for {url}")


@functools.lru_cache(maxsize=4096)
def listing(url: str) -> list[str]:
    r = http.session().get(url, headers=http.earthdata_headers(), timeout=120)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return sorted(set(re.findall(r'href="(3B-[^"/]+\.(?:HDF5|nc4))"', r.text)))


def read_points(url: str, var: str, ix: np.ndarray, iy: np.ndarray) -> np.ndarray:
    """Values var[0, ix, iy] (lon, lat order) reading only the needed chunks."""
    signed = resolve(url)
    for attempt in range(4):
        try:
            with http.fsspec_open(signed) as f, h5py.File(f, "r") as h:
                v = h[var]
                cl = v.chunks[1]
                out = np.full(ix.shape, np.nan)
                for s in np.unique(ix // cl):
                    strip = v[0, s * cl:(s + 1) * cl, :]
                    m = (ix // cl) == s
                    out[m] = strip[ix[m] - s * cl, iy[m]]
                out[out < 0] = np.nan
                return out
        except FileNotFoundError:
            raise
        except Exception:
            if attempt == 3:
                raise
            signed = resolve(url)
    raise RuntimeError("unreachable")


class _IMERGFinal(Product):
    start = pd.Timestamp("1998-01-01")
    file_workers = 16
    block = "MS"  # yield a block per month

    def grid(self):
        return Grid(LAT, LON, x_periodic=360.0)

    def files(self, t0: pd.Timestamp, t1: pd.Timestamp) -> list[tuple[pd.Timestamp, str]]:
        raise NotImplementedError

    def fetch(self, sites, st, t0, t1):
        iy, ix = st.px_index()
        months = pd.date_range(t0.to_period("M").start_time, t1, freq="MS")
        for m0 in months:
            m1 = min(t1, m0 + pd.offsets.MonthEnd(0) + pd.Timedelta(hours=23, minutes=59))
            files = [(t, u) for t, u in self.files(max(t0, m0), m1)]
            if not files:
                continue

            res = list(process_map(_read_file, [(t, u, self.h5var, ix, iy) for t, u in files], self.file_workers))
            times = pd.DatetimeIndex([t for t, _ in res])
            arr = np.stack([a for _, a in res], axis=-1)  # (nsite, 4, nt)
            yield Block(list(sites.site_id), times, self.convert_all({"precipitation": arr}))


class IMERGFinalDaily(_IMERGFinal):
    name = "imerg_final_daily"
    title = "IMERG Final V07 (daily)"
    freq = "1d"
    h5var = "precipitation"
    source = "GES DISC GPM_3IMERGDF.07 (HTTPS range reads)"
    notes = "Daily (UTC day) gauge-adjusted IMERG Final V07; V07 Final ends 2025-09-30."
    variables = {"pr": Var(["precipitation"], "precip", "mm", None, {"day_end_offset_h": 24, "desc": "daily precipitation, UTC day"})}

    def files(self, t0, t1):
        # V07B names are deterministic; missing files (404) become NaN
        return [(d, f"{BASE}/GPM_3IMERGDF.07/{d:%Y}/{d:%m}/3B-DAY.MS.MRG.3IMERG.{d:%Y%m%d}-S000000-E235959.V07B.nc4")
                for d in pd.date_range(t0.normalize(), t1, freq="D")]

    def available_end(self):
        return _latest("GPM_3IMERGDF.07", daily=True)


class IMERGFinalHH(_IMERGFinal):
    name = "imerg_final_hh"
    title = "IMERG Final V07 (half-hourly)"
    freq = "30min"
    h5var = "Grid/precipitation"
    source = "GES DISC GPM_3IMERGHH.07 (HTTPS range reads)"
    notes = "Half-hourly gauge-adjusted IMERG Final V07, stamped at end of half hour. Extracted for JJA 2025 only."
    # GES DISC serves only per-file HDF5; under load we measured < 0.4 files/s (48 files/day),
    # so the half-hourly Final run is limited to one summer (JJA 2025, ~4400 files). IMERG Final
    # daily covers the full period and IMERG Late covers sub-daily behaviour throughout.
    start = pd.Timestamp("2025-06-01 00:30")
    end = pd.Timestamp("2025-08-31 23:30")
    variables = {"pr": Var(["precipitation"], "precip", "mm", lambda precipitation: precipitation * 0.5,
                           {"desc": "precipitation over half hour ending at stamp (rate mm/h x 0.5 h)"})}

    def files(self, t0, t1):
        out = []
        for tend in pd.date_range(t0.ceil("30min"), t1, freq="30min"):
            ts = tend - pd.Timedelta(minutes=30)
            te = ts + pd.Timedelta(minutes=29, seconds=59)
            mins = ts.hour * 60 + ts.minute
            name = f"3B-HHR.MS.MRG.3IMERG.{ts:%Y%m%d}-S{ts:%H%M%S}-E{te:%H%M%S}.{mins:04d}.V07B.HDF5"
            out.append((tend, f"{BASE}/GPM_3IMERGHH.07/{ts:%Y}/{ts:%j}/{name}"))
        return out

    def available_end(self):
        return min(self.end, _latest("GPM_3IMERGHH.07", daily=False))


def _latest(short: str, daily: bool) -> pd.Timestamp:
    r = http.get("https://cmr.earthdata.nasa.gov/search/granules.json", params={
        "short_name": short.split(".")[0], "version": short.split(".")[1], "sort_key": "-start_date", "page_size": 1}).json()
    e = r["feed"]["entry"][0]
    t = pd.Timestamp(e["time_end"]).tz_localize(None)
    return t.normalize() if daily else t.ceil("30min")


def _read_file(args):
    t, u, var, ix, iy = args
    try:
        return t, read_points(u, var, ix.ravel(), iy.ravel()).reshape(ix.shape)
    except FileNotFoundError:
        return t, np.full(ix.shape, np.nan)
