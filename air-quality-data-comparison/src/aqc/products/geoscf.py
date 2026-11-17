"""GEOS-CF v1 and v2 replay from NASA SMCE public Zarr stores (anonymous S3, us-west-2).

    s3://smce-geos-cf-public/geos-cf-rpl.zarr      v1 replay, 2018-01-01 -> 2026-01-02
    s3://smce-geos-cf-public/geos-cf-v2-rpl.zarr   v2 replay, 2025-08-04 -> ~present

Zarr v2, (time, lev=1, lat=721, lon=1440), chunks (744|663 h, 1, 50, 50), blosc-lz4. Hourly
means stamped at HH:30 ("hours since ... 00:30") -> shifted +30 min to end-of-interval.
Months that were re-appended appear twice on the time axis; the LAST occurrence of each time
is used. Reads go time-chunk by time-chunk; within one, only the 50x50 tiles that hold site
stencils are fetched, and each tile is read once for all sites in it.
"""

from __future__ import annotations

import functools
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import zarr

from .base import FieldProduct, Grid, Var, scale

BUCKET = "smce-geos-cf-public"
MISSING = 1e14


_ppb = scale(1e9)  # mol mol-1 -> ppb


@functools.cache
def _group(name: str):
    return zarr.open_group(f"s3://{BUCKET}/{name}", mode="r",
                           storage_options={"anon": True, "client_kwargs": {"region_name": "us-west-2"}})


class _GEOSCF(FieldProduct):
    store_name = ""
    freq = "1h"
    block_workers = 2
    tile_workers = 16
    per_tile_reads = True  # cost scales with the tiles holding the sites, so keep groups separate

    def grid(self) -> Grid:
        g = _group(self.store_name)
        return Grid(y=g["lat"][:], x=g["lon"][:], x_periodic=360.0)

    @functools.cached_property
    def _time(self):
        """(times at end of interval for the kept indices, kept store indices), sorted by time."""
        g = _group(self.store_name)
        t = g["time"][:]
        units = g["time"].attrs["units"]  # 'hours since YYYY-MM-DD HH:MM:SS'
        origin = pd.Timestamp(units.split("since")[1].strip())
        # last occurrence of each value
        rev = t[::-1]
        _, first_rev = np.unique(rev, return_index=True)
        keep = np.sort(len(t) - 1 - first_rev)
        keep = keep[np.argsort(t[keep], kind="stable")]
        times = origin + pd.to_timedelta(t[keep], unit="h") + pd.Timedelta(minutes=30)
        return pd.DatetimeIndex(times), keep

    def _valid_end(self) -> pd.Timestamp:
        times, keep = self._time
        g = _group(self.store_name)
        a = g[self.variables[next(iter(self.variables))].src[0]]
        # the time axis can be pre-allocated past the data: probe the last chunks at one pixel
        n = len(keep)
        lo = max(0, n - 3000)
        x = a.get_orthogonal_selection((keep[lo:], 0, 400, 700))
        ok = np.where(np.isfinite(x) & (np.abs(x) < MISSING))[0]
        return times[lo + ok[-1]] if len(ok) else times[0]

    def available_end(self) -> pd.Timestamp:
        return self._valid_end()

    def blocks(self, t0, t1):
        times, keep = self._time
        m = (times >= t0) & (times <= t1)
        idx = keep[m]
        tt = times[m]
        cl = self._chunk_len
        out = defaultdict(list)
        for i, t in zip(idx, tt):
            out[int(i // cl)].append((int(i), t))
        return [v for _, v in sorted(out.items(), key=lambda kv: kv[1][0][1])]

    @functools.cached_property
    def _chunk_len(self) -> int:
        g = _group(self.store_name)
        return g[self.variables[next(iter(self.variables))].src[0]].chunks[0]

    def read_block(self, key, st):
        idx = np.array([i for i, _ in key])
        times = pd.DatetimeIndex([t for _, t in key])
        order = np.argsort(times)
        idx, times = idx[order], times[order]
        g = _group(self.store_name)
        iy, ix = st.px_index()  # (nsite, 4)
        ok = iy >= 0
        ty, tx = iy // 50, ix // 50
        tiles = sorted({(int(a), int(b)) for a, b in zip(ty[ok], tx[ok])})
        srcs = sorted({s for v in self.variables.values() for s in v.src})
        out = {s: np.full(iy.shape + (len(idx),), np.nan) for s in srcs}
        i0, i1 = int(idx.min()), int(idx.max()) + 1

        def read_tile(args):
            s, (a, b) = args
            arr = g[s]
            y0, x0 = a * 50, b * 50
            blk = np.asarray(arr[i0:i1, 0, y0:y0 + 50, x0:x0 + 50], dtype="f8")[idx - i0]
            blk[~(np.abs(blk) < MISSING)] = np.nan
            sel = ok & (ty == a) & (tx == b)
            ks, ps = np.nonzero(sel)
            return s, ks, ps, blk[:, iy[ks, ps] - y0, ix[ks, ps] - x0].T

        jobs = [(s, t) for s in srcs for t in tiles]
        with ThreadPoolExecutor(self.tile_workers) as ex:
            for s, ks, ps, vals in ex.map(read_tile, jobs):
                out[s][ks, ps, :] = vals
        return times, out


class GEOSCFv1(_GEOSCF):
    name = "geoscf_v1"
    title = "GEOS-CF v1 (replay)"
    store_name = "geos-cf-rpl.zarr"
    start = pd.Timestamp("2018-01-01 01:00")
    source = "s3://smce-geos-cf-public/geos-cf-rpl.zarr (NASA SMCE public Zarr, anonymous)"
    notes = "0.25 deg hourly; PM2.5 at 35% RH (pm25_rh35_gcc); no surface obs assimilated"
    variables = {
        "pm25": Var(["pm25_rh35_gcc"], "pm", "ug m-3", attrs={"rh_basis": "35%"}),
        "o3": Var(["o3"], "ppb", "ppb", _ppb),
        "no2": Var(["no2"], "ppb", "ppb", _ppb),
        "co": Var(["co"], "ppb", "ppb", _ppb),
    }


class GEOSCFv2(_GEOSCF):
    name = "geoscf_v2"
    title = "GEOS-CF v2 (replay)"
    store_name = "geos-cf-v2-rpl.zarr"
    start = pd.Timestamp("2025-08-04 10:00")
    source = "s3://smce-geos-cf-public/geos-cf-v2-rpl.zarr (NASA SMCE public Zarr, anonymous)"
    notes = "0.25 deg hourly; PM at 35% RH; satellite O3 assimilated, no surface obs"
    variables = {
        "pm25": Var(["pm25_rh35"], "pm", "ug m-3", attrs={"rh_basis": "35%"}),
        "pm10": Var(["pm10_rh35"], "pm", "ug m-3", attrs={"rh_basis": "35%"}),
        **{f"pm25_{c}": Var([f"pm25{c}_rh35"], "spec", "ug m-3", attrs={"rh_basis": "35%"})
           for c in ("bc", "du", "nh4", "nit", "oc", "soa", "ss", "su")},
        "o3": Var(["o3"], "ppb", "ppb", _ppb),
        "no2": Var(["no2"], "ppb", "ppb", _ppb),
        "co": Var(["co"], "ppb", "ppb", _ppb),
    }
