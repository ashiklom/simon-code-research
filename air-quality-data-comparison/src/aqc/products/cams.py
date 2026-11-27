"""CAMS (ECMWF) global composition from the Atmosphere Data Store (ADS) API.

    cams-global-reanalysis-eac4                    0.75 deg, 3-hourly, 2003 -> ~1 year ago
    cams-global-atmospheric-composition-forecasts  0.4 deg, hourly leads; 00 UTC run, leads 1-24 h

Auth: env ``CDSAPI_KEY`` (ECMWF personal access token, shared by CDS and ADS) against
``https://ads.atmosphere.copernicus.eu/api``. The account must have accepted the ADS terms of
use and data-protection statement (and the dataset licences) on the ADS website, else the API
answers 403 "user didn't accept all required site policies".

Variables: surface PM2.5/PM10 (kg m-3 -> ug m-3; CAMS PM is computed from the aerosol tracers
at ambient RH... see the CAMS documentation; recorded as attr rh_basis="ambient (CAMS)") and O3/NO2
mass mixing ratio at the LOWEST model level (EAC4 level 60 of 60, forecasts level 137 of 137;
kg kg-1 -> ppb with molar masses 48.00 / 46.0055 and air 28.9644). Fields are instantaneous and
stamped at their valid time (UTC). One request per month (EAC4: surface and model-level are two
requests) or per day (forecasts); each global NetCDF is sampled at all sites and deleted.
"""

from __future__ import annotations

import contextlib
import fcntl
import functools
import os
import tempfile
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from .. import config
from ..http import get
from .base import ChunkedStoreProduct, FieldProduct, Grid, Var, sample_field, scale

ADS = "https://ads.atmosphere.copernicus.eu/api"
M_AIR = 28.9644
CACHE = config.CACHE / "cams"

_pm = scale(1e9)  # kg m-3 -> ug m-3
_o3 = scale(M_AIR / 48.00 * 1e9)  # kg kg-1 -> ppb
_no2 = scale(M_AIR / 46.0055 * 1e9)


def _key() -> str:
    key = os.environ.get("ADSAPI_KEY") or os.environ.get("CDSAPI_KEY")
    if not key:
        raise RuntimeError("set CDSAPI_KEY (ECMWF personal access token) for the ADS")
    return key


JOB_STATES = ("accepted", "running", "successful")  # jobs we can still wait on / download


def _norm(x):
    """Request in a canonical form: dict keys kept, lists compared as sorted strings."""
    if isinstance(x, dict):
        return {k: _norm(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return sorted(str(v) for v in x)
    return str(x)


def same_request(a: dict, b: dict) -> bool:
    return _norm(a) == _norm(b)


def pick_job(jobs: list[dict], dataset: str, since: pd.Timestamp, request_of) -> str | None:
    """jobID of the newest job for `dataset` created after `since`, still usable, whose request
    (``request_of(jobID)``) equals ours; ``request_of`` returns None for no match."""
    for j in sorted(jobs, key=lambda j: j.get("created", ""), reverse=True):
        if j.get("processID") != dataset or j.get("status") not in JOB_STATES:
            continue
        if pd.Timestamp(j["created"]) < since:
            continue
        if request_of(j["jobID"]):
            return j["jobID"]
    return None


def _find_job(dataset: str, request: dict, days: int = 3) -> str | None:
    """An earlier ADS job with this exact request (e.g. submitted by a run killed by a container
    restart): reattaching keeps its place in the ADS queue (hours) instead of resubmitting."""
    h = {"PRIVATE-TOKEN": _key()}
    jobs = get(f"{ADS}/retrieve/v1/jobs", params={"limit": 100}, headers=h).json().get("jobs", [])

    def matches(jid):
        r = get(f"{ADS}/retrieve/v1/jobs/{jid}", params={"request": "true"}, headers=h).json()
        return same_request(r.get("metadata", {}).get("request", {}).get("ids", {}), request)

    return pick_job(jobs, dataset, pd.Timestamp.utcnow().tz_localize(None) - pd.Timedelta(days=days), matches)


def catalogue_end(dataset: str) -> pd.Timestamp:
    j = get(f"{ADS}/catalogue/v1/collections/{dataset}").json()
    return pd.Timestamp(j["extent"]["temporal"]["interval"][0][1]).tz_localize(None)


@contextlib.contextmanager
def _ads_slot():
    """One ADS request in flight per machine. ECMWF's Data Stores protection measures (Oct 2026) ask
    for requests to be submitted sequentially, not in parallel, and have disabled accounts that did
    otherwise. An flock is shared by every thread and process here (the global-store build, the
    forecast extraction), so all ADS traffic queues behind it."""
    CACHE.mkdir(parents=True, exist_ok=True)
    with open(CACHE / ".ads.lock", "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _retrieve(dataset: str, request: dict) -> list[Path]:
    with _ads_slot():
        return _retrieve_one(dataset, request)


PART = 64 << 20  # bytes per ranged GET of an ADS result


def _range_get(url: str, headers: dict):
    import requests

    return requests.get(url, headers=headers, stream=True, timeout=(30, 300))


def fetch_ranges(url: str, size: int, target: Path, get=_range_get, part: int = PART, tries: int = 10) -> None:
    """Download `size` bytes of `url` into `target` as consecutive ranged GETs, each checked for a
    206 with the requested Content-Range and the full length; a failed part is fetched again and
    written at its own offset. (The datastores client resumes by appending after an interruption,
    which here grew a 526 MB result past 1.2 GB without ever finishing.)"""
    import requests

    pos, fails = 0, 0
    with open(target, "wb") as f:
        while pos < size:
            end = min(pos + part, size) - 1
            try:
                r = get(url, {"Range": f"bytes={pos}-{end}"})
                r.raise_for_status()
                cr = r.headers.get("content-range", "")
                if r.status_code != 206 or not cr.startswith(f"bytes {pos}-{end}/"):
                    raise OSError(f"range {pos}-{end}: HTTP {r.status_code}, content-range {cr!r}")
                f.seek(pos)
                n = 0
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
                    n += len(chunk)
                if n != end - pos + 1:
                    raise OSError(f"range {pos}-{end}: got {n} bytes")
                pos, fails = end + 1, 0
            except (requests.RequestException, OSError) as e:
                fails += 1
                if fails > tries:
                    raise
                print(f"[cams] download {pos}/{size}: {e!r}; retry {fails}/{tries}")
                time.sleep(min(15 * 2**fails, 600))
        f.truncate(size)
    if (got := target.stat().st_size) != size:
        raise OSError(f"downloaded {got} of {size} bytes")


def _retrieve_one(dataset: str, request: dict) -> list[Path]:
    from ecmwf.datastores import Client

    CACHE.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=CACHE, suffix=".download")
    os.close(fd)
    try:
        job = _find_job(dataset, request)
    except Exception as e:  # the lookup is an optimisation only
        print(f"[cams] ADS job lookup failed ({e!r}); submitting")
        job = None
    client = Client(url=ADS, key=_key(), progress=False)
    if job:
        print(f"[cams] reattaching to ADS job {job}")
    else:
        job = client.submit(dataset, request).request_id
        print(f"[cams] submitted ADS job {job}")
    res = client.get_results(job)  # waits in the ADS queue
    fetch_ranges(res.location, res.content_length, Path(tmp))
    p = Path(tmp)
    if zipfile.is_zipfile(p):
        out = []
        with zipfile.ZipFile(p) as z:
            for n in z.namelist():
                if n.endswith(".nc"):
                    q = CACHE / f"{p.stem}_{Path(n).name}"
                    q.write_bytes(z.read(n))
                    out.append(q)
        p.unlink()
        return out
    q = p.with_suffix(".nc")
    p.rename(q)
    return [q]


def _fields(paths: list[Path], st, lat_ref: np.ndarray) -> tuple[pd.DatetimeIndex, dict[str, np.ndarray]]:
    """Open the returned NetCDF(s); -> valid times and raw[var] (nsite, 4, ntime)."""
    out, times = {}, None
    try:
        for p in paths:
            with xr.open_dataset(p, engine="netcdf4") as ds:
                ds = ds.squeeze(drop=False)
                if "forecast_reference_time" in ds.dims or "forecast_period" in ds.dims:
                    if "forecast_reference_time" not in ds.dims:
                        ds = ds.expand_dims("forecast_reference_time")
                    ds = ds.stack(t=("forecast_reference_time", "forecast_period"))
                    vt = (pd.to_datetime(ds.forecast_reference_time.values)
                          + pd.to_timedelta(ds.forecast_period.values))
                    tdim = "t"
                else:
                    tdim = "valid_time" if "valid_time" in ds.dims else "time"
                    vt = pd.to_datetime(ds[tdim].values)
                lat = ds.latitude.values
                if lat[0] < lat[-1]:
                    ds = ds.isel(latitude=slice(None, None, -1))
                lon = ds.longitude.values
                if lon.min() < 0:  # -> 0..360 order
                    ds = ds.roll(longitude=int((lon < 0).sum()), roll_coords=True)
                if ds.sizes["latitude"] != len(lat_ref):
                    raise ValueError(f"unexpected grid {dict(ds.sizes)}")
                for v in ds.data_vars:
                    da = ds[v]
                    extra = [d for d in da.dims if d not in (tdim, "latitude", "longitude")]
                    if extra:
                        da = da.isel({d: -1 for d in extra})  # lowest model level is the last
                    da = da.transpose(tdim, "latitude", "longitude")
                    out[v] = sample_field(da.values.astype("f4"), st)  # (nsite, 4, nt)
                times = pd.DatetimeIndex(vt)
    finally:
        for p in paths:
            p.unlink(missing_ok=True)
    order = np.argsort(times)
    return times[order], {k: v[..., order] for k, v in out.items()}


class _CAMS(FieldProduct):
    dataset = ""
    dlat = 0.75
    block_workers = 2

    def grid(self) -> Grid:
        n = int(round(180 / self.dlat)) + 1
        lat = np.round(90 - self.dlat * np.arange(n), 4)
        lon = np.round(self.dlat * np.arange(int(round(360 / self.dlat))), 4)
        return Grid(y=lat, x=lon, x_periodic=360.0, lon360=True)


class CAMSEAC4(ChunkedStoreProduct):
    """EAC4 at the sites, read from our global analysis-ready copy (``aqc cams-store``, repo
    ``global-cams_eac4``), which is built from the ADS. Species are at model level 60 in ug m-3."""

    name = "cams_eac4"
    title = "CAMS global reanalysis EAC4"
    freq = "3h"
    start = pd.Timestamp("2018-01-01")
    site_workers = 8
    source = "ADS cams-global-reanalysis-eac4 (CDSAPI_KEY), via our global Icechunk copy global-cams_eac4"
    notes = ("0.75 deg, 3-hourly instantaneous; PM at surface, gases and PM components at the lowest model level "
             "(60); assimilates satellite AOD/O3/NO2/CO only. No nitrate/ammonium; dust < 0.9 um only.")
    variables = {
        "pm25": Var(["pm25"], "pm", "ug m-3", None, attrs={"rh_basis": "ambient (CAMS)", "instantaneous": True}),
        "pm10": Var(["pm10"], "pm", "ug m-3", None, attrs={"rh_basis": "ambient (CAMS)", "instantaneous": True}),
        "o3": Var(["o3"], "ppb", "ppb", None, attrs={"level": "model level 60", "instantaneous": True}),
        "no2": Var(["no2"], "ppb", "ppb", None, attrs={"level": "model level 60", "instantaneous": True}),
        "pm25_so4": Var(["pm25_so4"], "spec", "ug m-3", None, attrs={"level": "model level 60"}),
        "pm25_om": Var(["pm25_om"], "spec", "ug m-3", None, attrs={"level": "model level 60"}),
        "pm25_bc": Var(["pm25_bc"], "spec", "ug m-3", None, attrs={"level": "model level 60"}),
        "pm25_ss": Var(["pm25_ss"], "spec", "ug m-3", None, attrs={"level": "model level 60", "desc": "dry, bins 1-2"}),
        "pm25_du": Var(["pm25_du"], "spec", "ug m-3", None,
                       attrs={"level": "model level 60", "desc": "dust < 0.9 um (lower bound for PM2.5 dust)"}),
    }

    @functools.cached_property
    def group(self):
        import zarr

        from .. import cams_store, store

        repo = store.open_repo(cams_store.NAME, create=False)
        return zarr.open_group(repo.readonly_session("main").store, mode="r", path=cams_store.PATH)

    def grid(self) -> Grid:
        g = self.group
        return Grid(y=g["lat"][:], x=g["lon"][:], x_periodic=360.0, lon360=True)

    def arrays(self):
        return {k: self.group[k] for k in {s for v in self.variables.values() for s in v.src}}

    @functools.cache
    def source_times(self):
        from .. import cams_store

        done = set(self.group.attrs.get("blocks_done", []))
        t = cams_store.times()
        # available: the contiguous run of finished blocks from the one holding self.start
        b = int((self.start - cams_store.T0) // pd.Timedelta(days=cams_store.DAYS))
        while b in done:
            b += 1
        return t[: min(len(t), b * cams_store.BLOCK)]

    def available_end(self) -> pd.Timestamp:
        t = self.source_times()
        return t[-1] if len(t) else self.start


class CAMSForecast(_CAMS):
    name = "cams_fcst"
    title = "CAMS global composition forecast (00 UTC, +1..24 h)"
    dataset = "cams-global-atmospheric-composition-forecasts"
    freq = "1h"
    dlat = 0.4
    start = pd.Timestamp("2025-08-01 01:00")
    source = "ADS API cams-global-atmospheric-composition-forecasts, 00 UTC run, leads 1-24 h (CDSAPI_KEY)"
    notes = "0.4 deg hourly instantaneous; PM at surface, O3/NO2 at the lowest model level (137)"
    variables = {
        "pm25": Var(["pm2p5"], "pm", "ug m-3", _pm, attrs={"rh_basis": "ambient (CAMS)", "instantaneous": True}),
        "pm10": Var(["pm10"], "pm", "ug m-3", _pm, attrs={"rh_basis": "ambient (CAMS)", "instantaneous": True}),
        "o3": Var(["go3"], "ppb", "ppb", _o3, attrs={"level": "model level 137", "instantaneous": True}),
        "no2": Var(["no2"], "ppb", "ppb", _no2, attrs={"level": "model level 137", "instantaneous": True}),
    }

    def available_end(self) -> pd.Timestamp:
        return catalogue_end(self.dataset).normalize() + pd.Timedelta(hours=24)

    def blocks(self, t0, t1):
        # run date d covers valid times d 01:00 .. d+1 00:00. One key per calendar month of run dates
        # (first and last clipped): ADS serves a month of 00 UTC runs in one request (cost 1488 of a
        # 10000 limit), so ~30x fewer queued requests than one per day.
        d0 = (pd.Timestamp(t0) - pd.Timedelta(hours=1)).normalize()
        d1 = (pd.Timestamp(t1) - pd.Timedelta(hours=1)).normalize()
        return [(max(m, d0), min(m + pd.offsets.MonthEnd(0), d1))
                for m in pd.date_range(d0.replace(day=1), d1, freq="MS")]

    def read_block(self, key, st):
        a, b = key
        lat = self.grid().y
        req = {"date": f"{a:%Y-%m-%d}/{b:%Y-%m-%d}", "time": ["00:00"], "type": ["forecast"],
               "leadtime_hour": [str(h) for h in range(1, 25)], "data_format": "netcdf"}
        reqs = [{**req, "variable": ["particulate_matter_2.5um", "particulate_matter_10um"]},
                {**req, "variable": ["ozone", "nitrogen_dioxide"], "model_level": ["137"]}]
        paths = [_retrieve(self.dataset, r) for r in reqs]  # one at a time (see _ads_slot)
        t1, raw = _fields(paths[0], st, lat)
        t2, raw2 = _fields(paths[1], st, lat)
        if not t1.equals(t2):
            raw2 = {k: _align(t2, v, t1) for k, v in raw2.items()}
        return t1, {**raw, **raw2}


def _align(t_src: pd.DatetimeIndex, v: np.ndarray, t_dst: pd.DatetimeIndex) -> np.ndarray:
    idx = t_src.get_indexer(t_dst)
    out = np.full(v.shape[:-1] + (len(t_dst),), np.nan)
    out[..., idx >= 0] = v[..., idx[idx >= 0]]
    return out
