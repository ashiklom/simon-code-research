"""Icechunk store for extracted series.

The store is a ROOT location holding one Icechunk repo per product / station network
(``<root>/products-<name>.icechunk``, ``<root>/obs-<network>.icechunk``), so extractions can
run concurrently. Backend is chosen by the root URL (``--store`` / ``CPC_STORE`` / default
local path):

    file:///abs/path            local filesystem (read/write)
    s3://bucket/prefix          S3 (read/write; standard AWS env credentials, or anonymous
                                with ?anonymous=1; ?region=..&endpoint=.. supported)
    https://host/prefix         Icechunk HTTP storage (read-only), e.g. CloudFront over S3

Layout (all arrays Zarr v3, pcodec-compressed):

    products/<product>/<freq>/            attrs: product metadata, extracted_end, variables
        time        (time,)  int64 seconds since 1970 UTC (end of interval for mean/sum)
        px_lat, px_lon, px_elev, px_dist_km, w   (site, px=4)
        <var>       (site, px=4, time) float32
    obs/<network>/<freq>/                 attrs: network metadata, extracted_end, variables
        time        (time,)
        <var>       (site, time) float32

Site ids live in the group attribute ``sites`` (ordered list) so arrays can grow along the
site axis. Values are rounded to a per-variable absolute quantum before writing (see
``QUANTA``) unless ``CPC_LOSSLESS=1``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

import icechunk
import numpy as np
import pandas as pd
import xarray as xr
import zarr
from zarr.codecs.numcodecs import PCodec

from . import config

# Absolute quantization step per canonical variable "kind" (PLAN.md, compression study).
QUANTA = {
    "temp": 0.01,  # degC
    "precip": 0.01,  # mm per interval
    "rh": 0.1,  # %
    "rad": 0.1,  # W m-2
    "sm": 0.0001,  # m3 m-3
    "pres": 1.0,  # Pa
    "wind": 0.01,  # m s-1
    "swe": 0.1,  # mm
    "snowd": 0.001,  # m
    "q": 0.001,  # g kg-1
    "vpd": 0.001,  # kPa
    "frac": 0.001,  # 0-1
    "coord": None,
}

FREQ_SECONDS = {"30min": 1800, "1h": 3600, "1d": 86400}
TIME_CHUNK = {"30min": 175200, "1h": 87600, "1d": 16384}


def lossless() -> bool:
    return os.environ.get("CPC_LOSSLESS", "0") == "1"


def quantize(x: np.ndarray, kind: str | None) -> np.ndarray:
    q = QUANTA.get(kind or "", None)
    x = np.asarray(x, dtype="f8")
    if q is None or lossless():
        return x.astype("f4")
    return (np.round(x / q) * q).astype("f4")


# --- backends -----------------------------------------------------------------------


def storage_from_url(url: str) -> icechunk.Storage:
    u = urlsplit(url)
    qs = {k: v[-1] for k, v in parse_qs(u.query).items()}
    if u.scheme in ("", "file"):
        return icechunk.local_filesystem_storage(u.path or url)
    if u.scheme == "s3":
        anon = qs.get("anonymous", "0") == "1"
        kw = dict(bucket=u.netloc, prefix=u.path.lstrip("/"), region=qs.get("region", os.environ.get("AWS_REGION", "us-west-2")))
        if ep := qs.get("endpoint"):
            kw["endpoint_url"] = ep
        if anon:
            kw["anonymous"] = True
        else:
            kw["from_env"] = True
        return icechunk.s3_storage(**kw)
    if u.scheme in ("http", "https"):
        return icechunk.http_storage(url.split("?")[0])
    raise ValueError(f"unsupported store URL: {url}")


def repo_url(root: str, name: str) -> str:
    base, _, q = root.partition("?")
    return f"{base.rstrip('/')}/{name}.icechunk" + (f"?{q}" if q else "")


def open_repo(name: str, root: str | None = None, *, create: bool = True) -> icechunk.Repository:
    """Open (or create) the repo `name` (e.g. 'products-era5') under the store root."""
    root = root or config.store_url()
    url = repo_url(root, name)
    st = storage_from_url(url)
    if icechunk.Repository.exists(st):
        return icechunk.Repository.open(st)
    if not create or urlsplit(url).scheme in ("http", "https"):
        raise FileNotFoundError(f"no Icechunk repo at {url}")
    return icechunk.Repository.create(st)


def list_repos(root: str | None = None) -> list[str]:
    """Repo names under a local root (remote roots: names from the known product/obs lists)."""
    root = root or config.store_url()
    u = urlsplit(root)
    if u.scheme in ("", "file"):
        from pathlib import Path

        p = Path(u.path or root)
        return sorted(d.name.removesuffix(".icechunk") for d in p.glob("*.icechunk")) if p.exists() else []
    from .products import registry

    names = [f"products-{n}" for n in registry.names()] + ["obs-USCRN"]
    out = []
    for n in names:
        try:
            open_repo(n, root, create=False)
            out.append(n)
        except Exception:
            pass
    return out


def copy_store(src_root: str, dst_root: str) -> None:
    for name in list_repos(src_root):
        print(f"copy {name}")
        copy_repo(repo_url(src_root, name), repo_url(dst_root, name))


def _open_url(url: str, create: bool) -> icechunk.Repository:
    st = storage_from_url(url)
    if icechunk.Repository.exists(st):
        return icechunk.Repository.open(st)
    if not create:
        raise FileNotFoundError(url)
    return icechunk.Repository.create(st)


def copy_repo(src: str, dst: str) -> None:
    """Copy the latest snapshot of `main` from one repo URL to another (data, not history)."""
    s_repo = _open_url(src, create=False)
    d_repo = _open_url(dst, create=True)
    s = s_repo.readonly_session("main")
    d = d_repo.writable_session("main")
    sroot = zarr.open_group(s.store, mode="r")
    droot = zarr.open_group(d.store, mode="a")

    def walk(sg, dg):
        dg.attrs.update(dict(sg.attrs))
        for name, arr in sg.arrays():
            da = dg.create_array(name, shape=arr.shape, dtype=arr.dtype, chunks=arr.chunks,
                                 serializer=_serializer(), fill_value=arr.fill_value, overwrite=True,
                                 dimension_names=arr.metadata.dimension_names)
            da.attrs.update(dict(arr.attrs))
            da[...] = arr[...]
        for name, sub in sg.groups():
            walk(sub, dg.require_group(name))

    walk(sroot, droot)
    d.commit(f"copy from {src}")


def _serializer():
    return PCodec(level=8)


# --- writing ------------------------------------------------------------------------


@dataclass
class VarSpec:
    name: str
    kind: str
    units: str
    attrs: dict


def group_path(kind: str, name: str, freq: str) -> str:
    return f"{kind}/{name}/{freq}"


def repo_name(kind: str, name: str) -> str:
    return f"{kind}-{name}"


def readonly(kind: str, name: str, root: str | None = None) -> icechunk.Session:
    return open_repo(repo_name(kind, name), root, create=False).readonly_session("main")


def time_axis(t0: pd.Timestamp, t1: pd.Timestamp, freq: str) -> np.ndarray:
    return pd.date_range(t0, t1, freq=freq.replace("1d", "D").replace("1h", "h")).values


def _to_seconds(t) -> np.ndarray:
    return pd.DatetimeIndex(t).as_unit("s").asi8.astype("i8")


class GroupWriter:
    """Write (site, [px,] time) series into one product/obs group of an open session."""

    def __init__(self, session: icechunk.Session, path: str, freq: str, *, has_px: bool, attrs: dict | None = None):
        self.root = zarr.open_group(session.store, mode="a")
        self.g = self.root.require_group(path)
        self.freq = freq
        self.dt = FREQ_SECONDS[freq]
        self.has_px = has_px
        if attrs:
            self.g.attrs.update(attrs)
        self.g.attrs.setdefault("sites", [])
        self.g.attrs.setdefault("variables", {})
        self.g.attrs["freq"] = freq

    # -- axes
    @property
    def sites(self) -> list[str]:
        return list(self.g.attrs["sites"])

    def _ensure_time(self, t_end: np.datetime64, t_start: np.datetime64) -> np.ndarray:
        """Make sure the time axis covers [t_start, t_end] (only extends at the end)."""
        t_end_s = int(pd.Timestamp(t_end).value // 10**9)
        if "time" not in self.g:
            t0 = int(pd.Timestamp(t_start).value // 10**9)
            n = (t_end_s - t0) // self.dt + 1
            arr = self.g.create_array("time", shape=(n,), dtype="i8", chunks=(1 << 20,), serializer=_serializer(),
                                      fill_value=0, dimension_names=["time"])
            arr[:] = t0 + self.dt * np.arange(n, dtype="i8")
            arr.attrs.update({"units": "seconds since 1970-01-01T00:00:00Z", "calendar": "proleptic_gregorian"})
            return arr[:]
        arr = self.g["time"]
        t = arr[:]
        if t_end_s > t[-1]:
            n_new = (t_end_s - t[0]) // self.dt + 1
            arr.resize((n_new,))
            arr[len(t):] = t[0] + self.dt * np.arange(len(t), n_new, dtype="i8")
            for name, a in self.g.arrays():
                if name != "time" and "time" in (a.metadata.dimension_names or ()):
                    shape = list(a.shape)
                    shape[-1] = n_new
                    a.resize(tuple(shape))
            t = arr[:]
        if int(pd.Timestamp(t_start).value // 10**9) < t[0]:
            raise ValueError(f"{self.g.path}: data starts before existing time axis ({t_start})")
        return t

    def _site_index(self, site_ids: list[str]) -> np.ndarray:
        sites = self.sites
        new = [s for s in site_ids if s not in sites]
        if new:
            sites = sites + new
            self.g.attrs["sites"] = sites
            for name, a in self.g.arrays():
                if name != "time" and (a.metadata.dimension_names or ())[:1] == ("site",):
                    shape = list(a.shape)
                    shape[0] = len(sites)
                    a.resize(tuple(shape))
        pos = {s: i for i, s in enumerate(sites)}
        return np.array([pos[s] for s in site_ids])

    def _ensure_var(self, name: str, shape_tail: tuple, ntime: int | None, dims: list[str], dtype="f4", attrs=None):
        if name in self.g:
            return self.g[name]
        nsite = len(self.sites)
        shape = (nsite, *shape_tail) + ((ntime,) if ntime else ())
        chunks = (1, *shape_tail) + ((TIME_CHUNK[self.freq],) if ntime else ())
        a = self.g.create_array(name, shape=shape, dtype=dtype, chunks=chunks, serializer=_serializer(),
                                fill_value=np.nan, dimension_names=dims)
        if attrs:
            a.attrs.update(attrs)
        return a

    # -- public
    def write_stencil(self, site_ids, px_lat, px_lon, w, px_elev=None, px_dist_km=None):
        idx = self._site_index(list(site_ids))
        for name, val in (("px_lat", px_lat), ("px_lon", px_lon), ("w", w), ("px_elev", px_elev), ("px_dist_km", px_dist_km)):
            if val is None:
                continue
            a = self._ensure_var(name, (4,), None, ["site", "px"], dtype="f8" if name in ("px_lat", "px_lon") else "f4")
            a[idx, :] = np.asarray(val)

    def write(self, site_ids, times, data: dict[str, np.ndarray], specs: dict[str, VarSpec]):
        """data[var]: (nsite, 4, ntime) if has_px else (nsite, ntime), aligned to `times`."""
        times = pd.DatetimeIndex(times)
        if len(times) == 0:
            return
        idx = self._site_index(list(site_ids))
        tax = self._ensure_time(times[-1].to_datetime64(), times[0].to_datetime64())
        ts = _to_seconds(times)
        it = (ts - tax[0]) // self.dt
        if not np.all(tax[it] == ts):
            raise ValueError(f"{self.g.path}: times not aligned to {self.freq} axis")
        sl = slice(int(it[0]), int(it[-1]) + 1)
        contiguous = (it[-1] - it[0] + 1) == len(it)
        vmeta = dict(self.g.attrs["variables"])
        for var, arr in data.items():
            sp = specs[var]
            dims = ["site", "px", "time"] if self.has_px else ["site", "time"]
            tail = (4,) if self.has_px else ()
            a = self._ensure_var(var, tail, len(tax), dims, attrs={"units": sp.units, "kind": sp.kind, **sp.attrs})
            vals = quantize(arr, sp.kind)
            # write site-by-site in sorted contiguous runs (cheap, and chunk-aligned on site)
            for k, si in enumerate(idx):
                if contiguous:
                    a[(si, ..., sl)] = vals[k]
                else:
                    a.set_orthogonal_selection((si, *([slice(None)] if self.has_px else []), it), vals[k])
            vmeta[var] = {"units": sp.units, "kind": sp.kind, **sp.attrs}
        self.g.attrs["variables"] = vmeta

    def set_extracted_end(self, t: pd.Timestamp):
        self.g.attrs["extracted_end"] = pd.Timestamp(t).isoformat()

    def site_done(self, site_id: str, tag: str) -> bool:
        return tag in self.g.attrs.get("done", {}).get(site_id, [])

    def mark_done(self, site_ids, tag: str):
        done = dict(self.g.attrs.get("done", {}))
        for s in site_ids:
            done[s] = sorted(set(done.get(s, [])) | {tag})
        self.g.attrs["done"] = done


# --- reading ------------------------------------------------------------------------


def list_groups(session: icechunk.Session, kind: str) -> list[str]:
    root = zarr.open_group(session.store, mode="r")
    if kind not in root:
        return []
    out = []
    for name, g in root[kind].groups():
        for f, _ in g.groups():
            out.append(f"{kind}/{name}/{f}")
    return out


def read_group(session: icechunk.Session, path: str, variables: list[str] | None = None,
               sites: list[str] | None = None, t0=None, t1=None) -> xr.Dataset:
    g = zarr.open_group(session.store, mode="r", path=path)
    all_sites = list(g.attrs["sites"])
    t = pd.to_datetime(g["time"][:], unit="s")
    isel_t = slice(None)
    if t0 is not None or t1 is not None:
        lo = 0 if t0 is None else int(t.searchsorted(pd.Timestamp(t0)))
        hi = len(t) if t1 is None else int(t.searchsorted(pd.Timestamp(t1), side="right"))
        isel_t = slice(lo, hi)
    si = np.arange(len(all_sites)) if sites is None else np.array([all_sites.index(s) for s in sites if s in all_sites], dtype=int)
    sid = [all_sites[i] for i in si]
    ds = xr.Dataset(coords={"site": sid, "time": t[isel_t]})
    vmeta = g.attrs.get("variables", {})
    names = variables or list(vmeta)
    for name in ("px_lat", "px_lon", "px_elev", "px_dist_km", "w"):
        if name in g:
            ds[name] = (("site", "px"), g[name].get_orthogonal_selection((si, slice(None))))
    for v in names:
        if v not in g:
            continue
        a = g[v]
        dims = tuple(a.metadata.dimension_names)
        sel = (si, slice(None), isel_t) if len(dims) == 3 else (si, isel_t)
        ds[v] = (dims, a.get_orthogonal_selection(sel))
        ds[v].attrs.update(dict(a.attrs))
    ds.attrs.update({k: v for k, v in g.attrs.items() if k not in ("sites", "done")})
    return ds


def group_attrs(session: icechunk.Session, path: str) -> dict:
    return dict(zarr.open_group(session.store, mode="r", path=path).attrs)
