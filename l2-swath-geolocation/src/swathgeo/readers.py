"""Readers compared in the read-performance benchmark (Part C).

Each reader implements  read(access, file_key, var, window) -> np.ndarray  where
  access   = Access(kind="local"|"http"|"s3", ...) describing where the bytes live: a local
             simulated profile (netsim proxy on 127.0.0.1:<port>, bucket "earthdata-sim") or a
             *real* one (Access.from_profile: real AWS S3 bucket/prefix/region with AWS-profile
             credentials, or an HTTPS base URL such as CloudFront),
  file_key = path relative to data/raw (also the HTTP path / S3 key, below access.prefix),
  var      = HDF5 path (or HDF4 SDS name),
  window   = (r0, r1, c0, c1) or None for the full array.
Arrays are returned raw (no scale/offset) so results can be checksummed across readers.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

from . import config

BUCKET = "earthdata-sim"


_CREDS: dict = {}


def aws_profile_credentials(profile: str) -> dict:
    """Temporary credentials of an AWS CLI profile (e.g. a credential_process profile), via
    `aws configure export-credentials`; cached per process and refreshed 5 min before expiry."""
    c = _CREDS.get(profile)
    if c is None or (c.get("Expiration") and datetime.fromisoformat(c["Expiration"]).timestamp() - time.time() < 300):
        out = subprocess.run(["aws", "configure", "export-credentials", "--profile", profile, "--format", "process"],
                             check=True, capture_output=True, text=True).stdout
        c = _CREDS[profile] = json.loads(out)
    return {"key": c["AccessKeyId"], "secret": c["SecretAccessKey"], "token": c.get("SessionToken")}


@dataclass
class Access:
    kind: str  # local | http | s3
    port: int | None = None
    profile: str = "local"
    extra: dict = field(default_factory=dict)
    # real (unsimulated) endpoints; the defaults describe the simulated netsim profiles
    real: bool = False
    bucket: str = BUCKET
    prefix: str = ""  # key prefix in the bucket / path prefix below http_base ("" or ending in "/")
    region: str = "us-west-2"
    http_base: str | None = None  # real HTTP(S) base URL (no trailing "/")
    aws_profile: str | None = None  # real S3: AWS CLI profile for credentials

    @classmethod
    def from_profile(cls, name: str, cfg: dict, port: int | None = None) -> "Access":
        """Access for a profile in config/net_profiles.toml (`real = true` -> no proxy)."""
        if not cfg.get("real"):
            return cls(cfg["kind"], port, name)
        prefix = cfg.get("prefix", "").strip("/")
        prefix = prefix + "/" if prefix else ""
        http_base = None
        if cfg["kind"] == "http":
            http_base = cfg.get("url") or os.environ[cfg["url_env"]]
            http_base = http_base.rstrip("/")
        return cls(cfg["kind"], None, name, real=True, bucket=cfg.get("bucket", BUCKET), prefix=prefix,
                   region=cfg.get("region", "us-east-1"), http_base=http_base, aws_profile=cfg.get("aws_profile"))

    def obj_key(self, key):
        return self.prefix + key

    def url(self, key):
        if self.kind == "local":
            return str(config.RAW / key)
        if self.kind == "http":
            base = self.http_base if self.real else f"http://127.0.0.1:{self.port}"
            return f"{base}/{self.prefix}{key}"
        return f"s3://{self.bucket}/{self.prefix}{key}"

    @property
    def endpoint(self):
        """S3 endpoint URL override (None = real AWS) / simulated HTTP base."""
        if self.real:
            return None if self.kind == "s3" else self.http_base
        return f"http://127.0.0.1:{self.port}"

    @property
    def creds(self) -> dict:
        """S3 credentials {key, secret, token}."""
        if not self.real:
            return {"key": "testing", "secret": "testing", "token": None}
        if self.aws_profile:
            return aws_profile_credentials(self.aws_profile)
        return {"key": None, "secret": None, "token": None}  # library default chain


S3_KW = dict(key="testing", secret="testing")


def s3fs_kwargs(access: Access) -> dict:
    """Keyword arguments for s3fs.S3FileSystem / fsspec storage_options."""
    if not access.real:
        return {"endpoint_url": access.endpoint, **S3_KW, "client_kwargs": {"region_name": access.region}}
    c = access.creds
    kw = {"client_kwargs": {"region_name": access.region}}
    if c["key"]:
        kw.update(key=c["key"], secret=c["secret"], token=c["token"])
    return kw


def http_kwargs(access: Access) -> dict:
    """fsspec HTTP storage_options: simulated profiles bypass any proxy; real ones honour
    HTTPS_PROXY / SSL_CERT_FILE like the other libraries (requests, curl, botocore, reqwest)."""
    return {"client_kwargs": {"trust_env": access.real}}


def fsspec_open(access: Access, key: str, cache_type=None, block_size=None):
    """fsspec file object; cache_type/block_size None -> the library defaults
    (HTTP: "bytes" cache, 5 MiB blocks; s3fs: "readahead", 50 MiB blocks)."""
    import fsspec

    kw = {}
    if cache_type:
        kw["cache_type"] = cache_type
    if block_size:
        kw["block_size"] = block_size
    if access.kind == "http":
        fs = fsspec.filesystem("http", skip_instance_cache=True, **http_kwargs(access))
        return fs.open(access.url(key), "rb", **kw)
    if access.kind == "s3":
        fs = fsspec.filesystem("s3", skip_instance_cache=True, **s3fs_kwargs(access),
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

    def __init__(self, cache_type=None, block_size=None, name="h5py"):
        self.cache_type, self.block_size, self.name = cache_type, block_size, name

    def read_many(self, access, key, vars_, window):
        import h5py

        if access.kind == "local":
            f = h5py.File(access.url(key), "r")
        else:
            f = h5py.File(fsspec_open(access, key, self.cache_type, self.block_size), "r")
        with f:
            return {v: np.asarray(f[v][_win(window)]) for v in vars_}


class H5pyRos3Reader(Reader):
    """HDF5's native read-only S3 driver (ROS3), also works for plain HTTP(S) URLs."""

    name = "h5py_ros3"
    formats = ("hdf5",)
    kinds = ("http", "s3")

    def read_many(self, access, key, vars_, window):
        import h5py

        if access.kind == "s3" and access.real:
            url = f"https://{access.bucket}.s3.{access.region}.amazonaws.com/{access.obj_key(key)}"
            c = access.creds
            f = h5py.File(url, "r", driver="ros3", aws_region=access.region.encode(), secret_id=c["key"].encode(),
                          secret_key=c["secret"].encode(), session_token=(c["token"] or "").encode())
        elif access.kind == "s3":
            url = f"{access.endpoint}/{BUCKET}/{key}"
            f = h5py.File(url, "r", driver="ros3", aws_region=b"us-west-2", secret_id=b"testing",
                          secret_key=b"testing")
        else:
            f = h5py.File(access.url(key), "r", driver="ros3")
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
        return f"/vsis3/{access.bucket}/{access.obj_key(key)}"

    def read_many(self, access, key, vars_, window):
        from osgeo import gdal

        gdal.UseExceptions()
        opts = dict(GDAL_TUNED if self.tuned else GDAL_BASE)
        if access.kind == "s3" and access.real:  # real AWS endpoint; explicit creds beat env/profile
            c = access.creds
            opts.update({"AWS_ACCESS_KEY_ID": c["key"], "AWS_SECRET_ACCESS_KEY": c["secret"],
                         "AWS_SESSION_TOKEN": c["token"] or "", "AWS_REGION": access.region})
        elif access.kind == "s3":
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
                s.trust_env = access.real  # real endpoints: honour HTTPS_PROXY / CA bundle
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

                st = obstore_s3(access)
                k = access.obj_key(key)
                obstore.download(st, k, str(dest)) if hasattr(obstore, "download") else \
                    dest.write_bytes(obstore.get(st, k).bytes())
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

    def __init__(self, repo_root: Path, concurrency: int = 16, app_retries: int = 0):
        self.repo_root = repo_root
        self.concurrency = concurrency
        self.app_retries = app_retries  # icechunk 2.3 does not retry 5xx on HTTP virtual chunks
        self.name = "icechunk_virtual" + ("_retry" if app_retries else "")
        self.retries_used = 0

    def read_many(self, access, key, vars_, window):
        import zarr

        repo_path = self.repo_root / access.profile / key.replace("/", "__")
        repo = open_repo(repo_path, access, self.concurrency)
        session = repo.readonly_session("main")
        root = zarr.open_group(session.store, mode="r")
        out = {}
        for v in vars_:
            arr = root[v]
            for attempt in range(self.app_retries + 1):
                try:
                    out[v] = np.asarray(arr[_win(window)] if window else arr[...])
                    break
                except Exception:  # noqa: BLE001
                    if attempt == self.app_retries:
                        raise
                    self.retries_used += 1
        return out


def container_prefix(access: Access) -> str:
    """Virtual-chunk-container prefix; container_prefix(access) + file_key is the chunk URL."""
    if access.kind in ("s3", "http"):
        return access.url("")
    return "file://" + str(config.RAW) + "/"


def container(access: Access):
    import icechunk

    if access.kind == "s3" and access.real:
        store = icechunk.s3_store(region=access.region)
    elif access.kind == "s3":
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
    cfg.max_concurrent_requests = concurrency
    if access.kind == "s3":
        c = access.creds
        cred = (icechunk.s3_credentials(access_key_id=c["key"], secret_access_key=c["secret"], session_token=c["token"])
                if c["key"] else icechunk.s3_credentials(from_env=True))
        creds = icechunk.containers_credentials({container_prefix(access): cred})
    else:
        creds = icechunk.containers_credentials({container_prefix(access): None})
    storage = icechunk.local_filesystem_storage(str(repo_path))
    if create:
        return icechunk.Repository.create(storage, config=cfg, authorize_virtual_chunk_access=creds)
    return icechunk.Repository.open(storage, config=cfg, authorize_virtual_chunk_access=creds)


def _retry():
    from datetime import timedelta

    return {"max_retries": 8, "retry_timeout": timedelta(seconds=600),
            "backoff": {"init_backoff": timedelta(seconds=0.2), "max_backoff": timedelta(seconds=5), "base": 2}}


RETRY = _retry()


def obstore_s3(access: Access):
    from obstore.store import S3Store

    if not access.real:
        return S3Store(BUCKET, endpoint=access.endpoint, access_key_id="testing", secret_access_key="testing",
                       region="us-west-2", client_options={"allow_http": True}, retry_config=RETRY)
    c = access.creds
    kw = dict(access_key_id=c["key"], secret_access_key=c["secret"], token=c["token"]) if c["key"] else {}
    return S3Store(access.bucket, region=access.region, retry_config=RETRY, **kw)


def obstore_registry(access: Access):
    from obspec_utils.registry import ObjectStoreRegistry
    from obstore.store import HTTPStore, LocalStore

    if access.kind == "s3":
        return ObjectStoreRegistry({f"s3://{access.bucket}": obstore_s3(access)})
    if access.kind == "http" and access.real:
        return ObjectStoreRegistry({access.http_base: HTTPStore.from_url(access.http_base, retry_config=RETRY)})
    if access.kind == "http":
        st = HTTPStore.from_url(f"http://127.0.0.1:{access.port}", client_options={"allow_http": True},
                                retry_config=RETRY)
        return ObjectStoreRegistry({f"http://127.0.0.1:{access.port}": st})
    return ObjectStoreRegistry({"file://": LocalStore()})
