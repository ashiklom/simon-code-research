"""Analysis-ready global CAMS EAC4 store (Icechunk, Zarr v3), complete record 2003-01 .. 2025-12.

Repo ``global-cams_eac4`` under the store root (``AQC_STORE``), group ``cams_eac4/3h``:

    time        (time,) int64 seconds since 1970 UTC (valid time; fields are instantaneous)
    lat, lon    0.75 deg, lat 90 .. -90, lon 0 .. 359.25
    <var>       (time, lat, lon) float32, quantized to store.QUANTA[kind], pcodec

Variables (12): surface pm25, pm10 (ug m-3; CAMS's own diagnostic at ambient RH); at the lowest
model level (60, ~10 m): o3, no2, so2, co (ppb), and PM components in ug m-3 (mass mixing ratio x
air density, rho = 0.9976 ps / (Rd T60)):

    pm25_so4   sulphate
    pm25_om    organic matter (hydrophilic + hydrophobic)
    pm25_bc    black carbon (hydrophilic + hydrophobic)
    pm25_ss    sea salt bins 1-2 (0.03-5 um at 80 % RH, i.e. dry diameter < ~2.5 um) / 4.3 (dry mass)
    pm25_du    dust bins 1-2 (0.03-0.9 um); a lower bound for PM2.5 dust (bin 3 is 0.9-20 um)
    dust_coarse dust bin 3 (0.9-20 um)

EAC4 has no nitrate or ammonium aerosol.

Layout: one shard per variable and 31-day block (248 3-hourly steps x the full grid, one S3
object of ~5-30 MB), (248, 32, 32) inner chunks, so a point's complete record is 271 small byte-
range reads. Each block is two ADS requests (surface; model level 60), downloaded by a few
threads ahead of a single writer. Resumable: ``blocks_done`` lists finished blocks.
"""

from __future__ import annotations

import os
import queue
import threading
import time as _time
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
import zarr

from . import config, store
from .products import cams

NAME = "global-cams_eac4"
PATH = "cams_eac4/3h"
DATASET = "cams-global-reanalysis-eac4"
T0 = pd.Timestamp("2003-01-01 00:00")
T1 = pd.Timestamp("2025-12-31 21:00")
DAYS = 31
BLOCK = DAYS * 8
INNER = (BLOCK, 32, 32)
RD = 287.05
B60 = 0.9976  # full-level pressure / surface pressure at model level 60 of 60
HOURS = [f"{h:02d}:00" for h in range(0, 24, 3)]
SFC = {"particulate_matter_2.5um": "pm2p5", "particulate_matter_10um": "pm10", "surface_pressure": "sp"}
ML = {"ozone": "go3", "nitrogen_dioxide": "no2", "sulphur_dioxide": "so2", "carbon_monoxide": "co",
      "temperature": "t", "sulphate_aerosol_mixing_ratio": "aermr11",
      "hydrophilic_organic_matter_aerosol_mixing_ratio": "aermr07",
      "hydrophobic_organic_matter_aerosol_mixing_ratio": "aermr08",
      "hydrophilic_black_carbon_aerosol_mixing_ratio": "aermr09",
      "hydrophobic_black_carbon_aerosol_mixing_ratio": "aermr10",
      "sea_salt_aerosol_0.03-0.5um_mixing_ratio": "aermr01", "sea_salt_aerosol_0.5-5um_mixing_ratio": "aermr02",
      "dust_aerosol_0.03-0.55um_mixing_ratio": "aermr04", "dust_aerosol_0.55-0.9um_mixing_ratio": "aermr05",
      "dust_aerosol_0.9-20um_mixing_ratio": "aermr06"}
M_AIR = 28.9644
MW = {"go3": 48.00, "no2": 46.0055, "so2": 64.066, "co": 28.010}
VARS = {  # name -> (kind, units, description)
    "pm25": ("pm", "ug m-3", "surface PM2.5 (CAMS diagnostic, ambient RH)"),
    "pm10": ("pm", "ug m-3", "surface PM10 (CAMS diagnostic, ambient RH)"),
    "o3": ("ppb", "ppb", "ozone, model level 60"),
    "no2": ("ppb", "ppb", "nitrogen dioxide, model level 60"),
    "so2": ("ppb", "ppb", "sulphur dioxide, model level 60"),
    "co": ("ppb", "ppb", "carbon monoxide, model level 60"),
    "pm25_so4": ("spec", "ug m-3", "sulphate aerosol, model level 60"),
    "pm25_om": ("spec", "ug m-3", "organic matter (hydrophilic + hydrophobic), model level 60"),
    "pm25_bc": ("spec", "ug m-3", "black carbon (hydrophilic + hydrophobic), model level 60"),
    "pm25_ss": ("spec", "ug m-3", "sea salt bins 1-2 / 4.3 (dry mass, dry diameter < ~2.5 um), model level 60"),
    "pm25_du": ("spec", "ug m-3", "dust bins 1-2 (0.03-0.9 um), lower bound for PM2.5 dust, model level 60"),
    "dust_coarse": ("spec", "ug m-3", "dust bin 3 (0.9-20 um), model level 60"),
}
CACHE = config.CACHE / "cams_eac4_global"


def times() -> pd.DatetimeIndex:
    return pd.date_range(T0, T1, freq="3h")


def nblocks() -> int:
    return -(-len(times()) // BLOCK)


def block_days(b: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    d0 = T0 + pd.Timedelta(days=DAYS * b)
    return d0, min(d0 + pd.Timedelta(days=DAYS - 1), T1.normalize())


def _download(b: int) -> tuple[Path, Path]:
    CACHE.mkdir(parents=True, exist_ok=True)
    d0, d1 = block_days(b)
    date = f"{d0:%Y-%m-%d}/{d1:%Y-%m-%d}"
    out = []
    for tag, req in (("sfc", {"variable": list(SFC)}), ("ml", {"variable": list(ML), "model_level": ["60"]})):
        f = CACHE / f"b{b:03d}_{tag}.nc"
        if not f.exists():
            paths = None
            for k in range(4):
                try:
                    paths = cams._retrieve(DATASET, {**req, "date": date, "time": HOURS, "data_format": "netcdf"})
                    break
                except Exception:
                    if k == 3:
                        raise
                    _time.sleep(60 * (k + 1))
            if len(paths) == 1:
                paths[0].rename(f)
            else:  # several NetCDFs in the zip: merge
                with xr.open_mfdataset(paths, combine="by_coords", compat="override") as ds:
                    ds.load().to_netcdf(f)
                for p in paths:
                    p.unlink(missing_ok=True)
        out.append(f)
    return out[0], out[1]


def _open(f: Path) -> xr.Dataset:
    ds = xr.open_dataset(f, engine="netcdf4")
    tdim = "valid_time" if "valid_time" in ds.dims else "time"
    ds = ds.rename({tdim: "time"})
    for d in [d for d in ds.dims if d not in ("time", "latitude", "longitude")]:
        ds = ds.isel({d: -1})
    if ds.latitude.values[0] < ds.latitude.values[-1]:
        ds = ds.isel(latitude=slice(None, None, -1))
    lon = ds.longitude.values
    if lon.min() < 0:
        ds = ds.roll(longitude=int((lon < 0).sum()), roll_coords=True)
    return ds


def derive(fs: Path, fm: Path) -> tuple[pd.DatetimeIndex, dict[str, np.ndarray]]:
    with _open(fs) as s, _open(fm) as m:
        t = pd.DatetimeIndex(s.time.values)
        if not t.equals(pd.DatetimeIndex(m.time.values)):
            m = m.reindex(time=s.time)
        g = lambda ds, v: ds[v].values.astype("f4")  # noqa: E731
        sp, temp = g(s, "sp"), g(m, "t")
        rho = (B60 * sp / (RD * temp)).astype("f4")  # kg m-3
        mmr = lambda *vs: sum(g(m, v) for v in vs) * rho * np.float32(1e9)  # noqa: E731  kg/kg -> ug m-3
        out = {
            "pm25": g(s, "pm2p5") * np.float32(1e9),
            "pm10": g(s, "pm10") * np.float32(1e9),
            **{k: g(m, src) * np.float32(M_AIR / MW[src] * 1e9) for k, src in
               (("o3", "go3"), ("no2", "no2"), ("so2", "so2"), ("co", "co"))},
            "pm25_so4": mmr("aermr11"),
            "pm25_om": mmr("aermr07", "aermr08"),
            "pm25_bc": mmr("aermr09", "aermr10"),
            "pm25_ss": mmr("aermr01", "aermr02") / np.float32(4.3),
            "pm25_du": mmr("aermr04", "aermr05"),
            "dust_coarse": mmr("aermr06"),
        }
    return t, out


def _layout(g: zarr.Group):
    t = times()
    nlat, nlon = 241, 480
    if "time" not in g:
        tsec = (t - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1)
        g.create_array("time", data=np.asarray(tsec, "i8"), chunks=(len(t),), dimension_names=["time"])
        g.create_array("lat", data=np.round(90 - 0.75 * np.arange(nlat), 4), dimension_names=["lat"])
        g.create_array("lon", data=np.round(0.75 * np.arange(nlon), 4), dimension_names=["lon"])
    shard = (BLOCK, -(-nlat // INNER[1]) * INNER[1], -(-nlon // INNER[2]) * INNER[2])
    for k, (kind, units, desc) in VARS.items():
        if k not in g:
            a = g.create_array(k, shape=(len(t), nlat, nlon), dtype="f4", chunks=INNER, shards=shard,
                               serializer=store._serializer(), fill_value=np.nan,
                               dimension_names=["time", "lat", "lon"])
            a.attrs.update({"units": units, "kind": kind, "desc": desc, "quantum": store.QUANTA.get(kind)})


def build(blocks: list[int] | None = None, root: str | None = None, workers: int = 3, keep_raw: bool = False,
          log=print):
    repo = store.open_repo(NAME, root)
    s = repo.writable_session("main")
    g = zarr.open_group(s.store, mode="a", path=PATH)
    g.attrs.update({"product": "cams_eac4", "title": "CAMS global reanalysis EAC4 (12 surface/lowest-level fields)",
                    "source": "ADS cams-global-reanalysis-eac4", "freq": "3h", "block_steps": BLOCK,
                    "start": str(T0), "end": str(T1), "licence": "CC-BY-4.0 (Copernicus); see README"})
    _layout(g)
    if s.has_uncommitted_changes:
        s.commit(f"{NAME}: layout")
    done = set(g.attrs.get("blocks_done", []))
    todo = [b for b in (blocks if blocks is not None else range(nblocks())) if b not in done]
    log(f"[{NAME}] {len(done)} blocks done, {len(todo)} to go")
    q: queue.Queue = queue.Queue(maxsize=workers)
    errors: list = []

    def producer(items):
        for b in items:
            try:
                q.put((b, _download(b)))
            except Exception as e:  # leave it for the next run
                errors.append((b, repr(e)))
                log(f"[{NAME}] block {b} download failed: {e!r}")

    chunks = [todo[i::workers] for i in range(workers)]
    th = [threading.Thread(target=producer, args=(c,), daemon=True) for c in chunks]
    for x in th:
        x.start()
    tsteps = times()
    n = 0
    while any(x.is_alive() for x in th) or not q.empty():
        try:
            b, (fs, fm) = q.get(timeout=30)
        except queue.Empty:
            continue
        t, data = derive(fs, fm)
        i0 = b * BLOCK
        exp = tsteps[i0:i0 + BLOCK]
        if not t.equals(exp):
            raise RuntimeError(f"block {b}: times {t[0]}..{t[-1]} ({len(t)}) != {exp[0]}..{exp[-1]} ({len(exp)})")
        s = repo.writable_session("main")
        g = zarr.open_group(s.store, mode="a", path=PATH)
        for k, x in data.items():
            g[k][i0:i0 + len(t)] = store.quantize(x, VARS[k][0])
        done = set(g.attrs.get("blocks_done", [])) | {b}
        g.attrs["blocks_done"] = sorted(done)
        s.commit(f"{NAME}: block {b} {t[0]:%Y-%m-%d}..{t[-1]:%Y-%m-%d}")
        if not keep_raw:
            fs.unlink(missing_ok=True)
            fm.unlink(missing_ok=True)
        n += 1
        log(f"[{NAME}] block {b} ({t[0]:%Y-%m-%d}..{t[-1]:%Y-%m-%d}) written; {len(done)}/{nblocks()} done")
    if errors:
        log(f"[{NAME}] {len(errors)} block(s) failed; rerun to retry: {[b for b, _ in errors]}")
    return n
