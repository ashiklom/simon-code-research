"""Low-cost sensors: Sensor.Community (archive.sensor.community, ODbL; no key).

Locations come from the live list (data.sensor.community/static/v2/data.json): outdoor nodes
with an optical PM sensor (SDS011 or Plantower PMS*) and a humidity sensor (BME280, DHT22,
SHT3x/SHT85, HTU21D) at the same location id. A node is kept only if its PM sensor has archive
files at both ends of the window (2023-01..2024-12).

Selection (about 80 nodes): (a) nodes outside Europe, spread >= 50 km apart, preferring
regions with few reference monitors; (b) nodes within 3 km of a Tier-1/2 reference site, so the
sensor can be scored against the monitor as well as against the products.

QC and correction, per 2.5-5 min record -> hourly mean:
* drop PM2.5 < 0 or > 1000, and hours with < 6 records;
* drop hours with RH > 75 % (optical sensors swell particles; uncorrectable above ~80 %);
* hygroscopic growth correction (kappa-Koehler, Crilley et al. 2018/2020 style):
  PM_dry = PM_raw / (1 + kappa * aw / (1 - aw)), aw = RH/100, kappa = 0.4.
Raw and corrected hourly values are both stored (pm25_raw, pm25). Site ids: ``SC:<location id>``.
"""

from __future__ import annotations

import gzip
import io
import json
import re
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from .. import config
from ..grid import haversine_km
from ..http import get, session

ARCH = "https://archive.sensor.community"
CACHE = config.CACHE / "sensorcommunity"
PM_TYPES = {"SDS011", "PMS1003", "PMS3003", "PMS5003", "PMS6003", "PMS7003", "SPS30"}
RH_TYPES = {"BME280", "DHT22", "SHT31", "SHT30", "SHT35", "SHT85", "HTU21D"}
WINDOW = (pd.Timestamp("2023-01-01"), pd.Timestamp("2024-12-31"))
EUROPE = set("AD AL AT BA BE BG BY CH CY CZ DE DK EE ES FI FR GB GR HR HU IE IS IT LI LT LU LV MC MD ME MK MT NL NO PL PT RO RS RU SE SI SK SM UA XK VA".split())
KAPPA = 0.4


def live_nodes() -> pd.DataFrame:
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / "data.json"
    if not p.exists():
        p.write_bytes(get("https://data.sensor.community/static/v2/data.json", timeout=300).content)
    rows = []
    for r in json.loads(p.read_text()):
        loc, sen = r["location"], r["sensor"]
        if int(loc.get("indoor") or 0):
            continue
        try:
            lat, lon = float(loc["latitude"]), float(loc["longitude"])
        except (TypeError, ValueError):
            continue
        rows.append({"loc": int(loc["id"]), "lat": lat, "lon": lon, "country": loc.get("country") or "",
                     "sensor": int(sen["id"]), "type": sen["sensor_type"]["name"].upper()})
    df = pd.DataFrame(rows).drop_duplicates(["loc", "sensor"])
    pm = df[df.type.isin(PM_TYPES)].drop_duplicates("loc")
    rh = df[df.type.isin(RH_TYPES)].drop_duplicates("loc")[["loc", "sensor", "type"]]
    return pm.merge(rh, on="loc", suffixes=("", "_rh"))


def _day_listing(day: pd.Timestamp) -> set[str]:
    try:
        return _day_listing_raw(day)
    except Exception:  # a few archive days are missing (404)
        return set()


def _day_listing_raw(day: pd.Timestamp) -> set[str]:
    txt = get(f"{ARCH}/{day:%Y}/{day:%Y-%m-%d}/", timeout=300).text if day.year < pd.Timestamp.now().year else \
        get(f"{ARCH}/{day:%Y-%m-%d}/", timeout=300).text
    return set(re.findall(r'href="([^"]+\.csv(?:\.gz)?)"', txt))


def _fname(day: pd.Timestamp, typ: str, sensor: int, listing: set[str]) -> str | None:
    base = f"{day:%Y-%m-%d}_{typ.lower()}_sensor_{sensor}.csv"
    for f in (base + ".gz", base):
        if f in listing:
            return f
    return None


def sites(reference: pd.DataFrame, n_sparse: int = 45, n_coloc: int = 35, n_europe: int = 20, log=print) -> pd.DataFrame:
    nodes = live_nodes()
    ends = [_day_listing(WINDOW[0] + pd.Timedelta(days=14)), _day_listing(WINDOW[1] - pd.Timedelta(days=14))]
    d0, d1 = WINDOW[0] + pd.Timedelta(days=14), WINDOW[1] - pd.Timedelta(days=14)
    ok = [all(_fname(d, r.type, r.sensor, L) for d, L in ((d0, ends[0]), (d1, ends[1]))) for r in nodes.itertuples()]
    nodes = nodes[ok].reset_index(drop=True)
    log(f"[SC] {len(nodes)} outdoor PM+RH nodes active through {WINDOW[0]:%Y}-{WINDOW[1]:%Y}")
    # (b) co-located with a reference site
    dist = haversine_km(nodes.lat.values[:, None], nodes.lon.values[:, None], reference.lat.values[None],
                        reference.lon.values[None])
    j = dist.argmin(axis=1)
    nodes["ref_site"] = reference.site_id.values[j]
    nodes["ref_km"] = dist[np.arange(len(nodes)), j]
    co = nodes[nodes.ref_km <= 3].sort_values("ref_km").drop_duplicates("ref_site")
    co = co.sample(min(n_coloc, len(co)), random_state=0) if len(co) > n_coloc else co
    # (a) outside Europe, spread out, round-robin over countries
    rest = nodes[~nodes.country.isin(EUROPE) & ~nodes["loc"].isin(co["loc"])].sample(frac=1, random_state=0)
    chosen = []
    order = rest.assign(k=rest.groupby("country").cumcount()).sort_values("k")
    for r in order.itertuples():
        if len(chosen) >= n_sparse:
            break
        if all(haversine_km(r.lat, r.lon, c.lat, c.lon) >= 50 for c in chosen):
            chosen.append(r)
    sp = pd.DataFrame(chosen).drop(columns=["Index", "k"], errors="ignore")
    # (c) a thin European sample (the network's home region), >= 300 km apart
    eu = nodes[nodes.country.isin(EUROPE) & ~nodes["loc"].isin(co["loc"])].sample(frac=1, random_state=1)
    picked = []
    for r in eu.itertuples():
        if len(picked) >= n_europe:
            break
        if all(haversine_km(r.lat, r.lon, c.lat, c.lon) >= 300 for c in picked):
            picked.append(r)
    ep = pd.DataFrame(picked).drop(columns=["Index"], errors="ignore")
    sel = pd.concat([co.assign(group="co-located"), sp.assign(group="sparse"), ep.assign(group="europe")],
                    ignore_index=True)
    log(f"[SC] selected {len(sel)} nodes: {sel.group.value_counts().to_dict()}")
    return pd.DataFrame({"site_id": "SC:" + sel["loc"].astype(str), "network": "SensorCommunity", "tier": 3,
                         "name": sel.type + " node " + sel["loc"].astype(str) + " (" + sel.country + ")",
                         "lat": sel.lat, "lon": sel.lon, "elev": np.nan, "country": sel.country, "region": "",
                         "setting": "", "utc_offset": 0.0, "params": "pm25,pm10",
                         "note": sel.group + np.where(sel.group == "co-located",
                                                      " with " + sel.ref_site + f" (" + sel.ref_km.round(2).astype(str) + " km)", ""),
                         "pm_sensor": sel.sensor, "pm_type": sel.type, "rh_sensor": sel.sensor_rh, "rh_type": sel.type_rh})


def _read(day, typ, sensor, listing) -> pd.DataFrame | None:
    f = _fname(day, typ, sensor, listing)
    if f is None:
        return None
    url = f"{ARCH}/{day:%Y}/{day:%Y-%m-%d}/{f}" if day.year < pd.Timestamp.now().year else f"{ARCH}/{day:%Y-%m-%d}/{f}"
    try:
        r = session().get(url, timeout=60)
        r.raise_for_status()
    except Exception:
        return None
    raw = gzip.decompress(r.content) if f.endswith(".gz") else r.content
    try:
        return pd.read_csv(io.BytesIO(raw), sep=";", low_memory=False)
    except Exception:
        return None


def hourly(site_table: pd.DataFrame, workers: int = 24, log=print) -> dict[str, pd.DataFrame]:
    days = pd.date_range(*WINDOW, freq="D")
    listings = {}

    def listing(d):
        if d not in listings:
            listings[d] = _day_listing(d)
        return listings[d]

    with ThreadPoolExecutor(8) as ex:
        for d, L in zip(days, ex.map(_day_listing, days)):
            listings[d] = L
    log(f"[SC] {len(days)} day listings")
    jobs = [(s, d) for s in site_table.itertuples() for d in days]

    def one(job):
        s, d = job
        pm = _read(d, s.pm_type, int(s.pm_sensor), listings[d])
        if pm is None or "P2" not in pm:
            return None
        rh = _read(d, s.rh_type, int(s.rh_sensor), listings[d])
        t = pd.to_datetime(pm.timestamp, errors="coerce")
        x = pd.DataFrame({"time": t.dt.floor("h") + pd.Timedelta(hours=1),
                          "pm25": pd.to_numeric(pm.P2, errors="coerce"), "pm10": pd.to_numeric(pm.P1, errors="coerce")})
        x = x[(x.pm25 >= 0) & (x.pm25 <= 1000)]
        h = x.groupby("time").agg(pm25=("pm25", "mean"), pm10=("pm10", "mean"), n=("pm25", "size"))
        if rh is not None and "humidity" in rh:
            tr = pd.to_datetime(rh.timestamp, errors="coerce").dt.floor("h") + pd.Timedelta(hours=1)
            hr = pd.to_numeric(rh.humidity, errors="coerce")
            h["rh"] = hr[(hr >= 0) & (hr <= 100)].groupby(tr).mean()
        else:
            h["rh"] = np.nan
        h["site_id"] = s.site_id
        return h.reset_index()

    out = []
    with ThreadPoolExecutor(workers) as ex:
        for k, r in enumerate(ex.map(one, jobs)):
            if r is not None:
                out.append(r)
            if k % 5000 == 0:
                log(f"[SC] {k}/{len(jobs)} files")
    h = pd.concat(out)
    h = h[h.n >= 6]
    aw = (h.rh / 100).clip(upper=0.99)
    growth = 1 + KAPPA * aw / (1 - aw)
    ok = h.rh.notna() & (h.rh <= 75)
    frames = {
        "pm25_raw": h[["site_id", "time"]].assign(value=h.pm25),
        "pm25": h.loc[ok, ["site_id", "time"]].assign(value=(h.pm25 / growth)[ok]),
        "pm10": h.loc[ok, ["site_id", "time"]].assign(value=(h.pm10 / growth)[ok]),
        "rh": h[["site_id", "time"]].assign(value=h.rh),
    }
    return frames
