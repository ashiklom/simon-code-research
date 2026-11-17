"""SPARTAN global PM2.5 network (https://www.spartan-network.org), public S3 ``spartan-cloud``.

    GroupByProduct/TimeResPM25/HourlyEstPM25/TimeResPM25_HourlyEstPM25_<SITE>.csv
        hourly PM2.5 estimated from nephelometer scatter scaled by filter mass (RH 35 %)
    GroupByProduct/FilterBased/ChemSpecPM25/FilterBased_ChemSpecPM25_<SITE>.csv
        filter (multi-day integrated) PM2.5 mass and composition

Times are local standard time; the UTC offset comes from the site's IANA time zone
(timezonefinder) at standard time. Site ids: ``SPARTAN:<code>``. Please cite SPARTAN per its
data policy when using these data.
"""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .. import config
from ..http import get

S3 = "https://spartan-cloud.s3.amazonaws.com"
CACHE = config.CACHE / "spartan"


def _keys(prefix: str) -> list[str]:
    root = ET.fromstring(get(f"{S3}/?list-type=2&prefix={prefix}").content)
    ns = {"s": root.tag.split("}")[0].strip("{")}
    return [e.text for e in root.findall("s:Contents/s:Key", ns)]


def _csv(key: str) -> pd.DataFrame:
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / key.rsplit("/", 1)[1]
    if not p.exists():
        p.write_bytes(get(f"{S3}/{key}").content)
    txt = p.read_text(errors="replace")
    lines = txt.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("Site_Code"))
    return pd.read_csv(io.StringIO("\n".join(lines[start:])), low_memory=False)


def std_offset_h(lat: float, lon: float) -> float:
    from timezonefinder import TimezoneFinder

    tz = TimezoneFinder().timezone_at(lat=lat, lng=lon) or "UTC"
    z = ZoneInfo(tz)
    # standard time = smaller of the January/July offsets
    offs = [datetime(2023, m, 15, tzinfo=z).utcoffset().total_seconds() / 3600 for m in (1, 7)]
    return min(offs) if lat >= 0 else min(offs)


def sites(log=print) -> pd.DataFrame:
    rows = []
    for k in _keys("GroupByProduct/TimeResPM25/HourlyEstPM25/"):
        if not k.endswith(".csv"):
            continue
        d = _csv(k)
        if d.empty:
            continue
        r = d.iloc[0]
        yrs = pd.to_numeric(d.Year_local, errors="coerce")
        if yrs.max() < 2018:
            log(f"[SPARTAN] {r.Site_Code}: ends {int(yrs.max())}, skipped")
            continue
        rows.append({"site_id": f"SPARTAN:{r.Site_Code}", "network": "SPARTAN", "tier": 2,
                     "name": f"{r.City}, {r.Country}", "lat": float(r.Latitude), "lon": float(r.Longitude),
                     "elev": float(r.Elevation_meters), "country": r.Country, "region": "", "setting": "",
                     "utc_offset": std_offset_h(float(r.Latitude), float(r.Longitude)), "params": "pm25",
                     "note": "nephelometer-estimated hourly PM2.5 (RH 35%)"})
    return pd.DataFrame(rows)


def hourly(site_table: pd.DataFrame) -> pd.DataFrame:
    out = []
    for _, s in site_table.iterrows():
        code = s.site_id.split(":", 1)[1]
        d = _csv(f"GroupByProduct/TimeResPM25/HourlyEstPM25/TimeResPM25_HourlyEstPM25_{code}.csv")
        d = d[d.Parameter_Code == 28108]
        lt = pd.to_datetime(dict(year=d.Year_local, month=d.Month_local, day=d.Day_local, hour=d.hour_local),
                            errors="coerce")
        t = lt - pd.Timedelta(hours=float(s.utc_offset)) + pd.Timedelta(hours=1)
        v = pd.to_numeric(d.Value, errors="coerce")
        dd = pd.DataFrame({"site_id": s.site_id, "time": t.dt.round("h"), "value": v}).dropna()
        out.append(dd[(dd.value >= 0) & (dd.time >= config.START)])
    d = pd.concat(out)
    return d.groupby(["site_id", "time"])["value"].mean().reset_index()


SPECIES = {  # SPARTAN parameter name -> canonical (PM2.5 components, ug m-3)
    "Sulfate Ion PM2.5": "pm25_so4", "Nitrate Ion PM2.5": "pm25_no3", "Ammonium Ion PM2.5": "pm25_nh4",
    "Equivalent BC PM2.5": "pm25_bc", "Filter PM2.5 mass": "pm25_filter",
}


def filters(site_table: pd.DataFrame) -> pd.DataFrame:
    """Filter samples: (site_id, start_utc, end_utc, var, value). Multi-day integrated samples."""
    out = []
    for _, s in site_table.iterrows():
        code = s.site_id.split(":", 1)[1]
        try:
            d = _csv(f"GroupByProduct/FilterBased/ChemSpecPM25/FilterBased_ChemSpecPM25_{code}.csv")
        except Exception:
            continue
        d = d[d.Parameter_Name.isin(SPECIES)]
        st = pd.to_datetime(dict(year=d.Start_Year_local, month=d.Start_Month_local, day=d.Start_Day_local,
                                 hour=d.Start_hour_local.astype(float).astype(int)), errors="coerce")
        en = pd.to_datetime(dict(year=d.End_Year_local, month=d.End_Month_local, day=d.End_Day_local,
                                 hour=d.End_hour_local.astype(float).astype(int)), errors="coerce")
        off = pd.Timedelta(hours=float(s.utc_offset))
        out.append(pd.DataFrame({"site_id": s.site_id, "start": st - off, "end": en - off,
                                 "var": d.Parameter_Name.map(SPECIES), "value": pd.to_numeric(d.Value, errors="coerce"),
                                 "hours": pd.to_numeric(d.Hours_sampled, errors="coerce")}))
    d = pd.concat(out).dropna()
    return d[d.end >= config.START]
