"""Readers compared in the read-performance benchmark (Part C).

Each reader implements  read(access, file_key, var, window) -> np.ndarray  where
  access   = Access(kind="local"|"http"|"s3", ...) describing where the bytes live,
  file_key = path relative to data/raw (also the HTTP path / S3 key),
  var      = HDF5 path (or HDF4 SDS name),
  window   = (r0, r1, c0, c1) or None for the full array.
Arrays are returned raw (no scale/offset) so results can be checksummed across readers.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import config

BUCKET = "earthdata-sim"


@dataclass
class Access:
    kind: str  # local | http | s3
    port: int | None = None
    profile: str = "local"
    extra: dict = field(default_factory=dict)

    def url(self, key):
        if self.kind == "local":
            return str(config.RAW / key)
        if self.kind == "http":
            return f"http://127.0.0.1:{self.port}/{key}"
        return f"s3://{BUCKET}/{key}"

    @property
    def endpoint(self):
        return f"http://127.0.0.1:{self.port}"


S3_KW = dict(key="testing", secret="testing")


def fsspec_open(access: Access, key: str, cache_type="readahead", block_size=None):
    import fsspec

    kw = {"cache_type": cache_type}
    if block_size:
        kw["block_size"] = block_size
    if access.kind == "http":
        fs = fsspec.filesystem("http", skip_instance_cache=True,
                               client_kwargs={"trust_env": False})
        return fs.open(access.url(key), "rb", **kw)
    if access.kind == "s3":
        fs = fsspec.filesystem("s3", skip_instance_cache=True, endpoint_url=access.endpoint, **S3_KW,
                               client_kwargs={"region_name": "us-west-2"},
                               config_kwargs={"retries": {"max_attempts": 5, "mode": "standard"}})
        return fs.open(access.url(key), "rb", **kw)
    return open(access.url(key), "rb")


def _win(window):
    if window is None:
        return ()
    r0, r1, c0, c1 = window
    return (slice(r0, r1), slice(c0, c1))


class Reader:
    name = "base"
    formats = ("hdf5",)  # which formats it can read
    kinds = ("local", "http", "s3")

    def supports(self, fmt, kind):
        return fmt in self.formats and kind in self.kinds

    def read_many(self, access, key, vars_, window):
        return {v: self.read(access, key, v, window) for v in vars_}


class H5pyReader(Reader):
    formats = ("hdf5",)

    def __init__(self, cache_type="readahead", block_size=None, name="h5py"):
        self.cache_type, self.block_size, self.name = cache_type, block_size, name

    def read_many(self, access, key, vars_, window):
        import h5py

        if access.kind == "local":
            f = h5py.File(access.url(key), "r")
        else:
            f = h5py.File(fsspec_open(access, key, self.cache_type, self.block_size), "r")
        with f:
            return {v: np.asarray(f[v][_win(window)]) for v in vars_}


class XarrayH5netcdfReader(Reader):
    name = "xarray_h5netcdf"
    formats = ("hdf5",)

    def read_many(self, access, key, vars_, window):
        import xarray as xr

        out = {}
        src = access.url(key) if access.kind == "local" else fsspec_open(access, key)
        groups = {}
        for v in vars_:
            g, n = v.rsplit("/", 1)
            groups.setdefault(g, []).append((v, n))
        for g, items in groups.items():
            ds = xr.open_dataset(src, engine="h5netcdf", group=g, phony_dims="sort", mask_and_scale=False,
                                 decode_times=False, cache=False)
            for v, n in items:
                da = ds[n]
                if window is not None:
                    r0, r1, c0, c1 = window
                    da = da.isel({da.dims[0]: slice(r0, r1), da.dims[1]: slice(c0, c1)})
                out[v] = da.values
            ds.close()
        return out


GDAL_BASE = {"GDAL_HTTP_MAX_RETRY": "5", "GDAL_HTTP_RETRY_DELAY": "0.5",
             "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_USE_HEAD": "YES"}
GDAL_TUNED = {**GDAL_BASE, "GDAL_HTTP_MULTIRANGE": "YES", "GDAL_HTTP_MERGE_CONSECUTIVE_RANGES": "YES",
              "CPL_VSIL_CURL_CHUNK_SIZE": str(2 * 2**20), "CPL_VSIL_CURL_CACHE_SIZE": str(512 * 2**20),
              "VSI_CACHE": "TRUE", "VSI_CACHE_SIZE": str(256 * 2**20), "GDAL_INGESTED_BYTES_AT_OPEN": str(2**20)}


class GdalReader(Reader):
    formats = ("hdf5", "hdf4")

    def __init__(self, tuned=False):
        self.tuned = tuned
        self.name = "gdal_tuned" if tuned else "gdal"

    def supports(self, fmt, kind):
        return fmt == "hdf5" or (fmt == "hdf4" and kind == "local")  # HDF4 lib needs a real file

    def _path(self, access, key):
        if access.kind == "local":
            return access.url(key)
        if access.kind == "http":
            return "/vsicurl/" + access.url(key)
        return f"/vsis3/{BUCKET}/{key}"

    def read_many(self, access, key, vars_, window):
        from osgeo import gdal

        gdal.UseExceptions()
        opts = dict(GDAL_TUNED if self.tuned else GDAL_BASE)
        if access.kind == "s3":
            opts.update({"AWS_S3_ENDPOINT": f"127.0.0.1:{access.port}", "AWS_HTTPS": "NO",
                         "AWS_VIRTUAL_HOSTING": "FALSE", "AWS_ACCESS_KEY_ID": "testing",
                         "AWS_SECRET_ACCESS_KEY": "testing", "AWS_REGION": "us-west-2"})
        path = self._path(access, key)
        out = {}
        with gdal.config_options(opts):
            for v in vars_:
                if key.endswith(".hdf"):
                    swath = "MODIS_Swath_Type_GEO" if "D03" in key else "MOD_Swath_LST"
                    spec = f'HDF4_EOS:EOS_SWATH:"{path}":{swath}:{v}'
                else:
                    spec = f'HDF5:"{path}"://{v.replace(" ", "_")}'
                ds = gdal.Open(spec)
                if window is None:
                    a = ds.GetRasterBand(1).ReadAsArray()
                else:
                    r0, r1, c0, c1 = window
                    a = ds.GetRasterBand(1).ReadAsArray(c0, r0, c1 - c0, r1 - r0)
                out[v] = a
                ds = None
            gdal.VSICurlClearCache()
        return out


class PyhdfReader(Reader):
    name = "pyhdf"
    formats = ("hdf4",)
    kinds = ("local",)

    def read_many(self, access, key, vars_, window):
        from pyhdf.SD import SD

        sd = SD(access.url(key))
        out = {}
        for v in vars_:
            ds = sd.select(v)
            out[v] = np.asarray(ds[_win(window)] if window else ds[:])
        sd.end()
        return out


class DownloadThenRead(Reader):
    """Fetch the whole file (one streamed GET), then read it locally."""

    name = "download_then_read"
    formats = ("hdf5", "hdf4")
    kinds = ("http", "s3")

    def read_many(self, access, key, vars_, window):
        tmpdir = Path(tempfile.mkdtemp(dir=config.DATA / "tmp" if (config.DATA / "tmp").exists() else None))
        dest = tmpdir / Path(key).name
        try:
            if access.kind == "http":
                import requests

                s = requests.Session()
                s.trust_env = False
                for i in range(6):
                    try:
                        with s.get(access.url(key), stream=True, timeout=600) as r:
                            r.raise_for_status()
                            with open(dest, "wb") as f:
                                for ch in r.iter_content(1 << 20):
                                    f.write(ch)
                        break
                    except Exception:  # noqa: BLE001
                        if i == 5:
                            raise
            else:
                import obstore
                from obstore.store import S3Store

                st = S3Store(BUCKET, endpoint=access.endpoint, access_key_id="testing", secret_access_key="testing",
                             region="us-west-2", client_options={"allow_http": True},
                             retry_config={"max_retries": 8, "backoff": {"init_backoff": 0.2, "max_backoff": 5, "base": 2},
                                           "retry_timeout": 600})
                obstore.download(st, key, str(dest)) if hasattr(obstore, "download") else \
                    dest.write_bytes(obstore.get(st, key).bytes())
            local = Access("local")
            rel = os.path.relpath(dest, config.RAW)
            inner = PyhdfReader() if key.endswith(".hdf") else H5pyReader()
            return inner.read_many(local, rel, vars_, window)
        finally:
            for p in tmpdir.glob("*"):
                p.unlink()
            tmpdir.rmdir()


class IcechunkVirtualReader(Reader):
    """Read through a pre-built icechunk repo of *virtual* references into the original file."""

    name = "icechunk_virtual"
    formats = ("hdf5", "hdf4")

    def __init__(self, repo_root: Path, concurrency: int = 16):
        self.repo_root = repo_root
        self.concurrency = concurrency

    def read_many(self, access, key, vars_, window):
        import icechunk
        import zarr

        repo_path = self.repo_root / access.profile / key.replace("/", "__")
        repo = open_repo(repo_path, access, self.concurrency)
        session = repo.readonly_session("main")
        root = zarr.open_group(session.store, mode="r")
        out = {}
        for v in vars_:
            arr = root[v]
            out[v] = np.asarray(arr[_win(window)] if window else arr[...])
        return out


def container_prefix(access: Access) -> str:
    if access.kind == "s3":
        return f"s3://{BUCKET}/"
    if access.kind == "http":
        return f"http://127.0.0.1:{access.port}/"
    return "file://" + str(config.RAW) + "/"


def container(access: Access):
    import icechunk

    if access.kind == "s3":
        store = icechunk.s3_store(region="us-west-2", endpoint_url=access.endpoint, allow_http=True,
                                  s3_compatible=True, force_path_style=True)
    elif access.kind == "http":
        store = icechunk.http_store()
    else:
        store = icechunk.local_filesystem_store(str(config.RAW))
    return icechunk.VirtualChunkContainer(container_prefix(access), store)


def open_repo(repo_path: Path, access: Access, concurrency=16, create=False):
    import icechunk

    cfg = icechunk.RepositoryConfig.default()
    cfg.set_virtual_chunk_container(container(access))
    cfg.max_concurrent_requests_for_object = concurrency
    if access.kind == "s3":
        creds = icechunk.containers_credentials(
            {container_prefix(access): icechunk.s3_credentials(access_key_id="testing", secret_access_key="testing")})
    else:
        creds = icechunk.containers_credentials({container_prefix(access): None})
    storage = icechunk.local_filesystem_storage(str(repo_path))
    if create:
        return icechunk.Repository.create(storage, config=cfg, authorize_virtual_chunk_access=creds)
    return icechunk.Repository.open(storage, config=cfg, authorize_virtual_chunk_access=creds)


def obstore_registry(access: Access):
    from obspec_utils.registry import ObjectStoreRegistry
    from obstore.store import HTTPStore, LocalStore, S3Store

    if access.kind == "s3":
        st = S3Store(BUCKET, endpoint=access.endpoint, access_key_id="testing", secret_access_key="testing",
                     region="us-west-2", client_options={"allow_http": True},
                     retry_config={"max_retries": 8, "backoff": {"init_backoff": 0.2, "max_backoff": 5, "base": 2},
                                   "retry_timeout": 600})
        return ObjectStoreRegistry({f"s3://{BUCKET}": st})
    if access.kind == "http":
        st = HTTPStore.from_url(f"http://127.0.0.1:{access.port}", client_options={"allow_http": True},
                                retry_config={"max_retries": 8, "backoff": {"init_backoff": 0.2, "max_backoff": 5, "base": 2},
                                              "retry_timeout": 600})
        return ObjectStoreRegistry({f"http://127.0.0.1:{access.port}": st})
    return ObjectStoreRegistry({"file://": LocalStore()})
