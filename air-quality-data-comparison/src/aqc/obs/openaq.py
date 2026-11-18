"""OpenAQ: reference monitors outside the US (Tier 2) and AirGradient / AirQo low-cost sensors (Tier 3).

Locations come from the OpenAQ v3 API (needs ``OPENAQ_API_KEY``; the listing is cached in
``data/cache/openaq/locations.json``). Hourly values come from OpenAQ's public archive bucket,
one gzip CSV per location and day:

    https://openaq-data-archive.s3.amazonaws.com/records/csv.gz/locationid=<id>/year=<YYYY>/month=<MM>/location-<id>-<YYYYMMDD>.csv.gz

The archive ``datetime`` is the START of the hour (it equals the API's ``period.datetimeFrom``),
so values are stamped at the end of the hour (+1 h) like every other network here. Gases are
converted to ppb: ppm x 1000; ug/m3 x Vm / M with Vm = 24.06 L/mol (20 C, the EU reference
conditions) for EEA providers and 24.45 L/mol (25 C) otherwise. Several sensors for one
parameter at a location are averaged.

Selection:
* Tier 2 (``OpenAQ``): ``isMonitor`` locations outside the US with PM2.5 from <= 2021-01 to
  >= 2026-06, excluding the ``AirNow`` provider outside Canada (those are the US embassies,
  already Tier 2) and anything within 5 km of a Tier 1/2 site. Greedy by record length, at
  least 50 km apart, at most 30 per country.
* Tier 3 (``OpenAQ-LC``): AirGradient (PMS5003) and AirQo locations with PM2.5 for at least 12
  months up to >= 2026-06: (a) co-located within 3 km of a Tier 1/2 reference site; (b) up to 10
  AirQo/airqoon locations >= 5 km apart (they cluster in Kampala and a few other cities);
  (c) AirGradient at least 100 km apart, round-robin over countries, preferring countries
  outside the US.
  Values are as published by the provider (AirGradient applies its own correction).
Site ids: ``OAQ:<location id>``.
"""

from __future__ import annotations

import gzip
import io
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .. import config
from ..grid import haversine_km
from ..http import session

API = "https://api.openaq.org/v3"
ARCHIVE = "https://openaq-data-archive.s3.amazonaws.com/records/csv.gz"
CACHE = config.CACHE / "openaq"
PARAMS = {"pm25": "pm25", "pm10": "pm10", "o3": "o3", "no2": "no2"}
MW = {"o3": 48.00, "no2": 46.0055}
LC_PROVIDERS = ("AirGradient", "AirQo", "airqoon")
REF_WINDOW = ("2021-01-01", "2026-06-01")
LC_END = "2026-06-01"


def key() -> str | None:
    return os.environ.get("OPENAQ_API_KEY")


def _api(path: str, **params) -> dict:
    if not key():
        raise RuntimeError("OPENAQ_API_KEY not set; skipping OpenAQ")
    s = session()
    for k in range(6):
        r = s.get(f"{API}{path}", params=params, headers={"X-API-Key": key()}, timeout=120)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(int(r.headers.get("Retry-After", 5 * (k + 1))))
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()
    return {}


def locations(refresh: bool = False, log=print) -> list[dict]:
    """Every OpenAQ location reporting PM2.5 (monitors and sensors), cached."""
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / "locations.json"
    if f.exists() and not refresh:
        return json.loads(f.read_text())
    rows = []
    for monitor in ("true", "false"):
        page = 1
        while True:
            res = _api("/locations", parameters_id=2, monitor=monitor, limit=1000, page=page)["results"]
            rows += res
            if len(res) < 1000:
                break
            page += 1
            time.sleep(1.1)  # 60 requests / minute
    f.write_text(json.dumps(rows))
    log(f"[OpenAQ] {len(rows)} PM2.5 locations listed")
    return rows


def _std_offset(tz: str | None) -> float:
    if not tz:
        return np.nan
    z = ZoneInfo(tz)
    offs = [datetime(2024, m, 15, tzinfo=z).utcoffset().total_seconds() / 3600 for m in (1, 7)]
    return float(min(offs))


def _frame(locs: list[dict]) -> pd.DataFrame:
    rows = []
    for x in locs:
        first, last = (x.get("datetimeFirst") or {}).get("utc"), (x.get("datetimeLast") or {}).get("utc")
        if not first or not last or x.get("isMobile"):
            continue
        params = sorted({s["parameter"]["name"] for s in x["sensors"] if s["parameter"]["name"] in PARAMS})
        rows.append({"id": x["id"], "name": x["name"], "lat": x["coordinates"]["latitude"], "lon": x["coordinates"]["longitude"],
                     "country": x["country"]["code"], "provider": x["provider"]["name"], "monitor": x["isMonitor"],
                     "tz": x.get("timezone"), "first": pd.Timestamp(first).tz_localize(None),
                     "last": pd.Timestamp(last).tz_localize(None), "params": ",".join(params)})
    return pd.DataFrame(rows)


def _far(df: pd.DataFrame, ref: pd.DataFrame, km: float) -> np.ndarray:
    if ref.empty or df.empty:
        return np.ones(len(df), bool)
    d = haversine_km(df.lat.values[:, None], df.lon.values[:, None], ref.lat.values[None], ref.lon.values[None])
    return d.min(axis=1) > km


def _greedy(df: pd.DataFrame, min_km: float, n_max: int, per_country: int | None = None) -> pd.DataFrame:
    chosen, per = [], {}
    for r in df.itertuples():
        if len(chosen) >= n_max:
            break
        if per_country is not None and per.get(r.country, 0) >= per_country:
            continue
        if all(haversine_km(r.lat, r.lon, c.lat, c.lon) >= min_km for c in chosen):
            chosen.append(r)
            per[r.country] = per.get(r.country, 0) + 1
    return pd.DataFrame(chosen).drop(columns=["Index"], errors="ignore")


def sites(reference: pd.DataFrame, n_ref: int = 400, n_lc_coloc: int = 40, n_lc_sparse: int = 60,
          n_lc_airqo: int = 10, log=print) -> pd.DataFrame:
    """reference: Tier 1/2 sites already selected (AQS, embassies, SPARTAN)."""
    df = _frame(locations(log=log))
    # ---- Tier 2 reference monitors
    ref = df[df.monitor & (df.country != "US") & (df["first"] <= REF_WINDOW[0]) & (df["last"] >= REF_WINDOW[1])]
    ref = ref[(ref.provider != "AirNow") | (ref.country == "CA")]
    ref = ref[_far(ref, reference, 5)]
    ref = ref.assign(years=(ref["last"] - ref["first"]).dt.days / 365.25,
                     ngas=ref.params.str.count("o3|no2"))
    ref = ref.sort_values(["years", "ngas"], ascending=False)
    t2 = _greedy(ref, 50, n_ref, per_country=30)
    log(f"[OpenAQ] Tier 2: {len(t2)} reference monitors in {t2.country.nunique()} countries "
        f"(of {len(ref)} candidates)")
    # ---- Tier 3 low-cost
    lc = df[df.provider.isin(LC_PROVIDERS) & (df["last"] >= LC_END)
            & (df["last"] - df["first"] >= pd.Timedelta(days=365))].copy()
    allref = pd.concat([reference[["site_id", "lat", "lon"]],
                        t2.assign(site_id="OAQ:" + t2.id.astype(str))[["site_id", "lat", "lon"]]], ignore_index=True)
    d = haversine_km(lc.lat.values[:, None], lc.lon.values[:, None], allref.lat.values[None], allref.lon.values[None])
    j = d.argmin(axis=1)
    lc["ref_site"], lc["ref_km"] = allref.site_id.values[j], d[np.arange(len(lc)), j]
    co = lc[lc.ref_km <= 3].sort_values("ref_km").drop_duplicates("ref_site")
    co = co.sample(n_lc_coloc, random_state=0) if len(co) > n_lc_coloc else co
    rest = lc[~lc.id.isin(co.id)].sample(frac=1, random_state=0)
    # AirQo/airqoon (East Africa, Turkey) cluster in a few cities: up to n_lc_airqo of them >= 5 km apart
    aq = _greedy(rest[rest.provider != "AirGradient"], 5, n_lc_airqo)
    rest = rest[(rest.provider == "AirGradient")]
    rest = rest.assign(us=rest.country == "US", k=rest.groupby("country").cumcount()).sort_values(["us", "k"])
    sp = _greedy(rest, 100, n_lc_sparse)
    t3 = pd.concat([co.assign(group="co-located"), aq.assign(group="sparse"), sp.assign(group="sparse")],
                   ignore_index=True)
    log(f"[OpenAQ] Tier 3: {len(t3)} low-cost ({t3.group.value_counts().to_dict()}, "
        f"{t3.provider.value_counts().to_dict()})")

    def table(x: pd.DataFrame, network: str, tier: int, note) -> pd.DataFrame:
        return pd.DataFrame({"site_id": "OAQ:" + x.id.astype(str), "network": network, "tier": tier, "name": x["name"],
                             "lat": x.lat, "lon": x.lon, "elev": np.nan, "country": x.country, "region": "",
                             "setting": "", "utc_offset": x.tz.map(_std_offset), "params": x.params,
                             "note": note, "provider": x.provider, "first": x["first"].dt.strftime("%Y-%m-%d"),
                             "last": x["last"].dt.strftime("%Y-%m-%d")})

    lc_note = t3.group + np.where(t3.group == "co-located",
                                  " with " + t3.ref_site + " (" + t3.ref_km.round(2).astype(str) + " km)", "")
    return pd.concat([table(t2, "OpenAQ", 2, "OpenAQ " + t2.provider),
                      table(t3, "OpenAQ-LC", 3, lc_note)], ignore_index=True)


# ---- hourly data from the archive ---------------------------------------------------------


def _day(loc: int, day: pd.Timestamp) -> bytes | None:
    f = CACHE / str(loc) / f"{day:%Y%m%d}.csv.gz"
    if f.exists():
        b = f.read_bytes()
        return b or None
    url = f"{ARCHIVE}/locationid={loc}/year={day:%Y}/month={day:%m}/location-{loc}-{day:%Y%m%d}.csv.gz"
    for k in range(4):
        try:
            r = session().get(url, timeout=60)
            if r.status_code in (403, 404):
                b = b""
                break
            r.raise_for_status()
            b = r.content
            break
        except Exception:
            if k == 3:
                return None  # transient: not cached, retried next run
            time.sleep(2 * (k + 1))
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b)
    return b or None


def _parse(b: bytes, eea: bool) -> pd.DataFrame:
    d = pd.read_csv(io.BytesIO(gzip.decompress(b)), usecols=["datetime", "parameter", "units", "value"])
    d = d[d.parameter.isin(PARAMS)]
    if d.empty:
        return pd.DataFrame(columns=["time", "var", "value"])
    t = pd.to_datetime(d.datetime, utc=True, format="ISO8601").dt.tz_localize(None) + pd.Timedelta(hours=1)
    v = d.value.astype(float).to_numpy()
    u = d.units.str.lower().str.replace("µ", "u").str.replace("μ", "u")
    for gas, mw in MW.items():
        m = (d.parameter == gas).to_numpy()
        v = np.where(m & (u == "ppm").to_numpy(), v * 1000, v)
        v = np.where(m & u.str.startswith("ug").to_numpy(), v * (24.06 if eea else 24.45) / mw, v)
    return pd.DataFrame({"time": t.values, "var": d.parameter.map(PARAMS).values, "value": v})


def _site_hourly(row, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    loc = int(row.site_id.split(":", 1)[1])
    eea = str(getattr(row, "provider", "")).startswith("EEA")
    d0 = max(start, pd.Timestamp(getattr(row, "first", start)) - pd.Timedelta(days=1)).normalize()
    d1 = min(end, pd.Timestamp(getattr(row, "last", end)) + pd.Timedelta(days=1)).normalize()
    parts = []
    for day in pd.date_range(d0, d1, freq="D"):
        b = _day(loc, day)
        if b:
            try:
                parts.append(_parse(b, eea))
            except Exception:
                pass
    if not parts:
        return pd.DataFrame(columns=["site_id", "time", "var", "value"])
    d = pd.concat([p for p in parts if len(p)]) if any(len(p) for p in parts) else None
    if d is None:
        return pd.DataFrame(columns=["site_id", "time", "var", "value"])
    lim = {"pm25": 1500, "pm10": 3000, "o3": 500, "no2": 1000}
    d = d[(d.value >= 0) & (d.value < d["var"].map(lim))]
    d = d.groupby(["time", "var"])["value"].mean().reset_index()
    d.insert(0, "site_id", row.site_id)
    return d


def hourly(site_table: pd.DataFrame, start=None, end=None, workers: int = 48, log=print) -> dict[str, pd.DataFrame]:
    """{var: long frame (site_id, time, value)} for pm25, pm10, o3, no2."""
    start = pd.Timestamp(start or config.START)
    end = pd.Timestamp(end or pd.Timestamp.now().floor("D"))
    out = []
    rows = list(site_table.itertuples())
    with ThreadPoolExecutor(max(1, workers // 8)) as ex_sites:
        # sites in parallel; each site's days fetched with its own small pool
        def one(r):
            with ThreadPoolExecutor(8) as ex:
                days = pd.date_range(max(start, pd.Timestamp(getattr(r, "first", start)) - pd.Timedelta(days=1)).normalize(),
                                     min(end, pd.Timestamp(getattr(r, "last", end)) + pd.Timedelta(days=1)).normalize())
                list(ex.map(lambda dd: _day(int(r.site_id.split(":", 1)[1]), dd), days))
            try:
                return _site_hourly(r, start, end)
            except Exception as e:  # one bad location should not stop the network
                log(f"[OpenAQ] {r.site_id}: failed ({e!r}); skipped")
                return None

        for k, d in enumerate(ex_sites.map(one, rows)):
            out.append(d)
            if d is None:
                continue
            if (k + 1) % 20 == 0 or k + 1 == len(rows):
                log(f"[OpenAQ] {k + 1}/{len(rows)} sites")
    d = pd.concat(out, ignore_index=True)
    return {v: g[["site_id", "time", "value"]].reset_index(drop=True) for v, g in d.groupby("var")}
