"""US Department of State embassy/consulate PM2.5 monitors (AirNow "EmbassyHistorical" files).

    s3://files.airnowtech.org/airnow/EmbassyHistorical/<Folder>/<YYYY>/<Folder>_PM2.5_<YYYY>_YTD.csv

Anonymous HTTPS (S3 website-style listing). Hourly raw PM2.5 ("Raw Conc.", QC "Valid" only),
local standard time, hour-beginning. Coordinates and UTC offsets come from AirNow's
``Monitoring_Site_Locations_V2.dat`` (agency "U.S. Department of State ..."), matched by site
name. Site ids: ``EMB:<Folder>``.
"""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

from .. import config
from ..http import get

S3 = "https://s3-us-west-1.amazonaws.com/files.airnowtech.org"
PREFIX = "airnow/EmbassyHistorical/"
CACHE = config.CACHE / "embassy"
YEARS = range(2018, 2027)


def _list(prefix: str, delimiter: str | None = "/") -> tuple[list[str], list[str]]:
    keys, prefixes, token = [], [], None
    while True:
        url = f"{S3}/?list-type=2&prefix={prefix}" + (f"&delimiter={delimiter}" if delimiter else "")
        if token:
            url += f"&continuation-token={token}"
        root = ET.fromstring(get(url).content)
        ns = {"s": root.tag.split("}")[0].strip("{")}
        keys += [e.text for e in root.findall("s:Contents/s:Key", ns)]
        prefixes += [e.text for e in root.findall("s:CommonPrefixes/s:Prefix", ns)]
        tok = root.find("s:NextContinuationToken", ns)
        if tok is None:
            return keys, prefixes
        token = tok.text


def _norm(s: str) -> str:
    return re.sub(r"[^a-z]", "", str(s).lower())


def locations() -> pd.DataFrame:
    """AirNow DOS PM2.5 monitor list (latest daily folder that has one)."""
    r = None
    for k in range(1, 15):
        d = pd.Timestamp.now().normalize() - pd.Timedelta(days=k)
        try:
            r = get(f"{S3}/airnow/{d:%Y}/{d:%Y%m%d}/Monitoring_Site_Locations_V2.dat")
            break
        except Exception:
            continue
    if r is None:
        raise RuntimeError("no AirNow Monitoring_Site_Locations_V2.dat in the last 14 days")
    df = pd.read_csv(io.StringIO(r.text), sep="|", dtype=str)
    df = df[df.AgencyName.str.contains("Department of State", na=False) & (df.Parameter == "PM2.5")]
    df["Latitude"] = df.Latitude.astype(float)
    df["Longitude"] = df.Longitude.astype(float)
    df = df[(df.Latitude != 0) | (df.Longitude != 0)]
    return df


def folders() -> list[str]:
    _, pre = _list(PREFIX)
    return [p[len(PREFIX):].strip("/") for p in pre]


def _ytd(folder: str, year: int) -> pd.DataFrame | None:
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{folder}_{year}.csv"
    if not p.exists() or year >= pd.Timestamp.now().year:
        keys, _ = _list(f"{PREFIX}{folder}/{year}/", None)
        ytd = [k for k in keys if k.endswith(f"_{year}_YTD.csv")]
        if ytd:
            p.write_bytes(get(f"{S3}/{ytd[0]}").content)
        else:  # some years only have monthly files
            mtd = [k for k in keys if re.search(rf"_{year}_\d+_MTD\.csv$", k)]
            if not mtd:
                return None
            parts = [get(f"{S3}/{k}").content.decode("utf-8", "replace") for k in sorted(mtd)]
            p.write_text(parts[0] + "".join(x.split("\n", 1)[1] if "\n" in x else "" for x in parts[1:]))
    try:
        return pd.read_csv(p)
    except Exception:
        return None


def sites(log=print) -> pd.DataFrame:
    loc = locations()
    loc["key"] = loc.SiteName.map(_norm)
    rows = []
    for f in folders():
        d = None
        for y in (2024, 2023, 2022, 2025, 2021, 2019):
            d = _ytd(f, y)
            if d is not None and len(d):
                break
        if d is None or not len(d):
            log(f"[EMB] {f}: no data")
            continue
        name = str(d["Site"].iloc[0])
        cand = loc[loc.key == _norm(name)]
        if cand.empty:
            cand = loc[loc.key == _norm(f)]
        if cand.empty:  # e.g. "EmbassyKathmandu" vs "Embassy Kathmandu", "KhartoumEmbassy"
            cand = loc[loc.key.apply(lambda k: k and (k in _norm(f) or _norm(f) in k))]
        if cand.empty:
            log(f"[EMB] {f} ({name}): no coordinates")
            continue
        c = cand.iloc[0]
        rows.append({"site_id": f"EMB:{f}", "network": "Embassy", "tier": 2, "name": name, "lat": c.Latitude,
                     "lon": c.Longitude, "elev": np.nan, "country": c.CountryFIPS, "region": "",
                     "setting": "urban", "utc_offset": float(c.GMTOffset), "params": "pm25",
                     "note": c.AgencyName})
    return pd.DataFrame(rows)


def hourly(site_table: pd.DataFrame, years=YEARS) -> pd.DataFrame:
    out = []
    for _, s in site_table.iterrows():
        f = s.site_id.split(":", 1)[1]
        for y in years:
            d = _ytd(f, y)
            if d is None or not len(d):
                continue
            d = d[d["QC Name"] == "Valid"]
            v = pd.to_numeric(d["Raw Conc."], errors="coerce")
            lt = pd.to_datetime(dict(year=d.Year, month=d.Month, day=d.Day, hour=d.Hour), errors="coerce")
            t = lt - pd.Timedelta(hours=float(s.utc_offset)) + pd.Timedelta(hours=1)
            dd = pd.DataFrame({"site_id": s.site_id, "time": t.dt.round("h"), "value": v})
            out.append(dd[(dd.value >= 0) & (dd.value < 2000)].dropna())
    d = pd.concat(out)
    return d.groupby(["site_id", "time"])["value"].mean().reset_index()
