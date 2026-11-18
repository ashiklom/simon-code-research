"""Analysis-ready CONUS gridded store (Icechunk, Zarr v3) for gridMET, complete record.

Repo ``conus-gridmet`` under the store root (``CPC_STORE``), group ``gridmet/1d``:

    time        (time,) int64 seconds since 1970 UTC (day END, 07 UTC next day; see gridmet.py)
    lat, lon    (lat,), (lon,) float64 cell centres (lat descending, as in gridMET)
    <var>       (time, lat, lon) float32, quantized to store.QUANTA[kind], pcodec

Each variable is sharded as one 366-day x full-grid shard (one S3 object per variable and
366-day block, ~30-80 MB), with (366, 32, 32) inner chunks, so a point's complete record is 47
small byte-range reads. Blocks are aligned to the first day (1979-01-01), not to calendar years;
each block is assembled from the one or two annual source files it spans
(``https://www.northwestknowledge.net/metdata/data/<v>_<year>.nc``), which are deleted after use.
The build is resumable: the group attribute ``blocks_done`` lists finished (variable, block) pairs.
"""

from __future__ import annotations

import json
import time as _time

import numpy as np
import pandas as pd
import xarray as xr
import zarr

from . import config, http, store
from .products import gridmet

NAME = "conus-gridmet"
PATH = "gridmet/1d"
BLOCK = 366
INNER = (BLOCK, 32, 32)
FILE_URL = "https://www.northwestknowledge.net/metdata/data/{v}_{y}.nc"
SRC_VAR = {"tmmx": "air_temperature", "tmmn": "air_temperature", "pr": "precipitation_amount",
           "rmax": "relative_humidity", "rmin": "relative_humidity", "sph": "specific_humidity",
           "srad": "surface_downwelling_shortwave_flux_in_air", "vs": "wind_speed",
           "vpd": "mean_vapor_pressure_deficit"}
CACHE = config.DATA / "cache" / "gridmet_annual"


def _annual(v: str, year: int) -> xr.DataArray:
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{v}_{year}.nc"
    if not f.exists():
        tmp = f.with_suffix(".part")
        for k in range(5):
            try:
                with http.session().get(FILE_URL.format(v=v, y=year), stream=True, timeout=600) as r:
                    r.raise_for_status()
                    with open(tmp, "wb") as fh:
                        for b in r.iter_content(1 << 22):
                            fh.write(b)
                tmp.rename(f)
                break
            except Exception:
                if k == 4:
                    raise
                _time.sleep(10 * (k + 1))
    ds = xr.open_dataset(f, mask_and_scale=False, cache=False)  # packed uint16: decoded per block in float32 (memory)
    return ds[SRC_VAR[v]]


def _decode(da: xr.DataArray) -> np.ndarray:
    raw = da.values
    a = da.attrs
    x = raw.astype("f4")
    for k in ("_FillValue", "missing_value"):
        if a.get(k) is not None:
            x[raw == np.asarray(a[k]).astype(raw.dtype)] = np.nan
    if a.get("scale_factor") is not None:
        x *= np.float32(a["scale_factor"])
    if a.get("add_offset") is not None:
        x += np.float32(a["add_offset"])
    return x


def _drop_old(v: str, keep_years: set[int]):
    for f in CACHE.glob(f"{v}_*.nc"):
        if int(f.stem.split("_")[1]) not in keep_years:
            f.unlink()


def build(end: pd.Timestamp | None = None, variables: list[str] | None = None, root: str | None = None, log=print):
    prod = gridmet.GridMET()
    end = pd.Timestamp(end) if end is not None else prod.available_end()
    days = pd.date_range(prod.start, end, freq="D")
    nblock = -(-len(days) // BLOCK)
    lat0 = _annual("tmmx", 1979)
    lat, lon = lat0.lat.values, lat0.lon.values
    repo = store.open_repo(NAME, root)
    s = repo.writable_session("main")
    g = zarr.open_group(s.store, mode="a", path=PATH)
    meta = prod.meta() | {"layout": "time-series sharded; see cpc/conus_store.py", "block_days": BLOCK,
                          "time_stamp": "day end (07 UTC next day)"}
    g.attrs.update(meta)
    t_end = (days + pd.Timedelta(hours=gridmet.DAY["day_end_offset_h"]))
    tsec = (t_end - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)
    if "time" not in g or g["time"].shape[0] != len(days):
        g.create_array("time", data=np.asarray(tsec, "i8"), chunks=(len(days),), overwrite=True,
                       dimension_names=["time"])
        g.create_array("lat", data=lat, overwrite=True, dimension_names=["lat"])
        g.create_array("lon", data=lon, overwrite=True, dimension_names=["lon"])
    names = variables or list(prod.variables)
    for name in names:
        var = prod.variables[name]
        kind = var.kind
        if name not in g or g[name].shape[0] != len(days):
            if name in g:  # extend along time (new days since the last build)
                g[name].resize((len(days), len(lat), len(lon)))
            else:
                a = g.create_array(name, shape=(len(days), len(lat), len(lon)), dtype="f4", chunks=INNER,
                                   shards=(BLOCK, -(-len(lat) // INNER[1]) * INNER[1], -(-len(lon) // INNER[2]) * INNER[2]), serializer=store._serializer(),
                                   fill_value=np.nan, dimension_names=["time", "lat", "lon"])
                a.attrs.update({"units": var.units, "kind": kind, "quantum": store.QUANTA.get(kind), **var.attrs})
    if s.has_uncommitted_changes:  # nothing to do when resuming
        s.commit(f"{NAME}: layout to {end:%Y-%m-%d}")
    for name in names:
        src = prod.variables[name].src[0]
        for b in range(nblock):
            s = repo.writable_session("main")
            g = zarr.open_group(s.store, mode="a", path=PATH)
            done = set(json.loads(g.attrs.get("blocks_done", "[]")) if isinstance(g.attrs.get("blocks_done"), str)
                       else g.attrs.get("blocks_done", []))
            key = f"{name}:{b}"
            bd = days[b * BLOCK:(b + 1) * BLOCK]
            full = len(bd) == BLOCK
            if key in done:
                continue
            years = sorted(set(bd.year))
            parts = []
            for y in years:
                da = _annual(src, y)
                t = pd.DatetimeIndex(da.day.values)
                sel = da.isel(day=np.flatnonzero(t.isin(bd)))
                parts.append(_decode(sel))
            x = np.concatenate(parts, axis=0)
            if x.shape[0] != len(bd):
                raise RuntimeError(f"{key}: {x.shape[0]} days in source, expected {len(bd)}")
            var = prod.variables[name]
            if var.convert is not None:  # float32 throughout: a block is ~0.3 G values
                x = np.asarray(var.convert(**{src: x}), dtype="f4")
            q = store.QUANTA.get(var.kind)
            if q is not None and not store.lossless():
                x = (np.round(x / np.float32(q)) * np.float32(q)).astype("f4")
            g[name][b * BLOCK:b * BLOCK + len(bd)] = x
            if full:  # a partial last block is rewritten on the next build
                done.add(key)
            g.attrs["blocks_done"] = sorted(done)
            g.attrs["extracted_end"] = str(end)
            s.commit(f"{NAME}: {key}")
            _drop_old(src, {bd[-1].year, bd[-1].year + 1})
            log(f"[{NAME}] {key} {bd[0]:%Y-%m-%d}..{bd[-1]:%Y-%m-%d} written")
    for f in CACHE.glob("*.nc"):
        f.unlink()
