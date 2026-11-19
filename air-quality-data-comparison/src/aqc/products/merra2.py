"""MERRA-2 aerosol diagnostics (M2T1NXAER) and the MERRA2_CNN_HAQAST bias-corrected PM2.5.

Access: GES DISC Earthdata HTTPS (Earthdata Login bearer token, redirected to a signed
CloudFront URL). Granule URLs come from CMR (one query per month), because directory listings
on data.gesdisc.earthdata.nasa.gov return 404 and the stream prefix (MERRA2_400 / _401
reprocessed months) varies. Each daily file is read whole-field for only the needed variables
(``h5remote.read_vars``: merged range requests + local decode), and every site is sampled.

M2T1NXAER: hourly means stamped HH:30 -> stamped at the END of the hour (HH+1:00).
    PM2.5 = DU25 + SS25 + BC + 1.4*OC + SO4*132.14/96.06    (dry; no nitrate)
    PM10  = DU   + SS   + BC + 1.4*OC + SO4*132.14/96.06
The OC factor 1.4 (organic matter / organic carbon) follows Buchard et al. (2016); the GMAO FAQ
uses 1. Components are stored separately (pm25_oc is OC as carried by GOCART), so either total
can be recomputed.

MERRA2_CNN_HAQAST_PM25 V1 (DOI 10.5067/OCKK5HCFW5N3): hourly, 'hours since YYYY-MM-DD 00:30'
-> also end-of-hour. QFLAG (1 low .. 4 highest; 2 = medium over ocean) is a static 2-D field,
stored as a constant series per pixel.
"""

from __future__ import annotations

import os
import functools
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from .. import http
from .base import Block, FieldProduct, Grid, Var, bounded_map, sample_field, scale, total
from .h5remote import read_vars

LAT = -90 + 0.5 * np.arange(361)
LON = -180 + 0.625 * np.arange(576)
CMR = "https://cmr.earthdata.nasa.gov/search/granules.json"
SO4_TO_AS = 132.14 / 96.06
KG2UG = 1e9


def resolve(url: str) -> str:
    """Follow Earthdata redirects (bearer auth) to the signed URL."""
    h = http.earthdata_headers()
    u = url
    for _ in range(6):
        r = http.session().get(u, headers=h if "earthdata.nasa.gov" in u else {}, allow_redirects=False,
                               stream=True, timeout=120)
        r.close()
        if r.status_code in (301, 302, 303, 307, 308):
            u = r.headers["Location"]
            continue
        if r.status_code == 404:
            raise FileNotFoundError(url)
        r.raise_for_status()
        return u
    raise RuntimeError(f"too many redirects: {url}")


@functools.lru_cache(maxsize=1024)
def granules(concept: str, month: str) -> dict[pd.Timestamp, str]:
    """{date: https url} for a collection (CMR concept id or 'short_name/version') and month 'YYYY-MM'."""
    m0 = pd.Timestamp(month + "-01")
    m1 = m0 + pd.offsets.MonthEnd(1)
    q = {"temporal": f"{m0:%Y-%m-%d}T00:00:00Z,{m1:%Y-%m-%d}T23:59:59Z", "page_size": 100}
    if "/" in concept:
        q["short_name"], q["version"] = concept.split("/")
    else:
        q["collection_concept_id"] = concept
    r = http.get(CMR, params=q, timeout=120)
    out = {}
    for e in r.json()["feed"]["entry"]:
        url = next((l["href"] for l in e.get("links", []) if l.get("href", "").startswith("https://data.gesdisc")
                    and l["href"].endswith((".nc4", ".nc"))), None)
        if url:
            out[pd.Timestamp(e["time_start"][:10])] = url
    return out


def latest_granule(concept: str) -> pd.Timestamp:
    q = {"sort_key": "-start_date", "page_size": 1}
    if "/" in concept:
        q["short_name"], q["version"] = concept.split("/")
    else:
        q["collection_concept_id"] = concept
    e = http.get(CMR, params=q, timeout=120).json()["feed"]["entry"][0]
    return pd.Timestamp(e["time_end"][:19])


class _DailyFiles(FieldProduct):
    """Daily global files with 24 hourly fields; one Block per calendar month."""

    concept = ""
    day_workers = int(os.environ.get("AQC_DAY_WORKERS", 2))  # parallel daily files (network-bound)
    static: tuple[str, ...] = ()  # 2-D (lat, lon) variables repeated over time

    def grid(self) -> Grid:
        return Grid(LAT, LON, x_periodic=360.0)

    def available_end(self) -> pd.Timestamp:
        # last hour of the newest daily file, stamped at the end of the hour
        return latest_granule(self.concept).floor("D") + pd.Timedelta(hours=24)

    def _read_day(self, args):
        day, url, st = args
        srcs = sorted({s for v in self.variables.values() for s in v.src})
        for attempt in range(4):
            try:
                a = read_vars(resolve(url), srcs, workers=8)
                break
            except FileNotFoundError:
                return None
            except Exception:
                if attempt == 3:
                    raise
        raw = {}
        for s, x in a.items():
            if s in self.static:
                v = sample_field(x, st).astype("f4")  # (nsite, 4)
                raw[s] = np.repeat(v[..., None], 24, axis=-1)
            else:
                raw[s] = sample_field(x, st).astype("f4")  # (nsite, 4, 24)
        del a
        times = day + pd.to_timedelta(np.arange(1, 25), unit="h")
        return times, raw

    def fetch(self, sites, st, t0, t1):
        ids = list(sites.site_id)
        for month in pd.period_range(t0.to_period("M"), t1.to_period("M"), freq="M"):
            g = granules(self.concept, str(month))
            days = [(d, u, st) for d, u in sorted(g.items())
                    if d + pd.Timedelta(hours=24) >= t0 and d < t1]
            if not days:
                continue
            parts = [r for r in bounded_map(self._read_day, days, self.day_workers) if r is not None]
            if not parts:
                continue
            times = pd.DatetimeIndex(np.concatenate([p[0] for p in parts]))
            raw = {k: np.concatenate([p[1][k] for p in parts], axis=-1) for k in parts[0][1]}
            m = (times >= t0) & (times <= t1)
            yield Block(ids, times[m], self.convert_all({k: v[..., m] for k, v in raw.items()}))


_spec = scale(KG2UG)


class MERRA2(_DailyFiles):
    name = "merra2"
    title = "MERRA-2 aerosols (M2T1NXAER)"
    concept = "M2T1NXAER/5.12.4"
    start = pd.Timestamp("2018-01-01 01:00")
    source = "GES DISC M2T1NXAER.5.12.4 daily files via Earthdata HTTPS (range reads of 7 variables)"
    notes = ("0.5x0.625 deg hourly; dry mass, no nitrate; PM2.5 = DU25+SS25+BC+1.4*OC+SO4*132.14/96.06; "
             "AOD assimilated, no surface PM")
    variables = {
        "pm25": Var(["DUSMASS25", "SSSMASS25", "BCSMASS", "OCSMASS", "SO4SMASS"], "pm", "ug m-3",
                    total(DUSMASS25=KG2UG, SSSMASS25=KG2UG, BCSMASS=KG2UG, OCSMASS=1.4 * KG2UG,
                          SO4SMASS=SO4_TO_AS * KG2UG), {"rh_basis": "dry", "oc_factor": 1.4}),
        "pm10": Var(["DUSMASS", "SSSMASS", "BCSMASS", "OCSMASS", "SO4SMASS"], "pm", "ug m-3",
                    total(DUSMASS=KG2UG, SSSMASS=KG2UG, BCSMASS=KG2UG, OCSMASS=1.4 * KG2UG,
                          SO4SMASS=SO4_TO_AS * KG2UG), {"rh_basis": "dry", "oc_factor": 1.4}),
        "pm25_du": Var(["DUSMASS25"], "spec", "ug m-3", _spec),
        "pm10_du": Var(["DUSMASS"], "spec", "ug m-3", _spec),
        "pm25_ss": Var(["SSSMASS25"], "spec", "ug m-3", _spec),
        "pm10_ss": Var(["SSSMASS"], "spec", "ug m-3", _spec),
        "pm25_bc": Var(["BCSMASS"], "spec", "ug m-3", _spec),
        "pm25_oc": Var(["OCSMASS"], "spec", "ug m-3", _spec, {"desc": "organic carbon as carried by GOCART"}),
        "pm25_so4": Var(["SO4SMASS"], "spec", "ug m-3", _spec, {"desc": "sulfate ion"}),
    }


class MERRA2CNN(_DailyFiles):
    name = "merra2_cnn"
    title = "MERRA-2 CNN HAQAST bias-corrected PM2.5"
    concept = "C3094710982-GES_DISC"
    start = pd.Timestamp("2018-01-01 01:00")
    static = ("QFLAG",)
    source = "GES DISC MERRA2_CNN_HAQAST_PM25.1 daily files via Earthdata HTTPS"
    notes = ("0.5x0.625 deg hourly; CNN ensemble trained on >5000 OpenAQ reference monitors "
             "(not independent of AirNow/AQS/embassy data)")
    variables = {
        "pm25": Var(["MERRA2_CNN_Surface_PM25"], "pm", "ug m-3", None, {"rh_basis": "as training monitors"}),
        "qflag": Var(["QFLAG"], "flag", "1", None, {"desc": "1 low, 2 medium (ocean), 3 high, 4 highest"}),
    }
