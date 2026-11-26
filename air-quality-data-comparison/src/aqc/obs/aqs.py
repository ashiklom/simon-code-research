"""US EPA AQS pre-generated files (https://aqs.epa.gov/aqsweb/airdata/download_files.html).

Validated regulatory data, no key. Hourly continuous monitors (FEM/non-FEM) for PM2.5 (88101,
falling back to 88502), PM10 (81102), O3 (44201) and NO2 (42602); daily 24-h filter FRM PM2.5
(88101, 24 HOUR samples) for the filter comparison. Site ids: ``AQS:SS-CCC-NNNN``.

Several monitors (POCs) at a site are averaged. Where a site reports both raw and "Corrected"
Teledyne T640 PM2.5 for the same hour, the raw T640 values are dropped (they read high).
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from .. import config
from ..http import get

BASE = "https://aqs.epa.gov/aqsweb/airdata"
CACHE = config.CACHE / "aqs"
YEARS = range(2018, 2026)
COMMON_YEARS = range(2018, 2024)

HOURLY = {"pm25": [88101, 88502], "pm10": [81102], "o3": [44201], "no2": [42602]}
UNIT_SCALE = {"Parts per million": 1000.0, "Parts per billion": 1.0, "Micrograms/cubic meter (LC)": 1.0,
              "Micrograms/cubic meter (25 C)": 1.0}


def download(name: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{name}.zip"
    if not p.exists():
        r = get(f"{BASE}/{name}.zip", timeout=1800)
        tmp = p.with_suffix(".part")
        tmp.write_bytes(r.content)
        tmp.rename(p)
    return p


def read_zip_csv(name: str, **kw) -> pd.DataFrame:
    with zipfile.ZipFile(download(name)) as z:
        return pd.read_csv(z.open(z.namelist()[0]), low_memory=False, **kw)


def site_id(df: pd.DataFrame) -> pd.Series:
    return "AQS:" + df["State Code"].astype(str).str.zfill(2) + "-" + df["County Code"].astype(str).str.zfill(3) + "-" \
        + df[[c for c in ("Site Num", "Site Number") if c in df][0]].astype(str).str.zfill(4)


def completeness() -> pd.DataFrame:
    """Per site x variable: number of common-window years with >= 75 % hourly (or 24-h) completeness."""
    rows = []
    for y in YEARS:
        d = read_zip_csv(f"annual_conc_by_monitor_{y}", dtype={"State Code": str, "County Code": str, "Site Num": str})
        d = d[d["Parameter Code"].isin([88101, 88502, 81102, 44201, 42602])]
        d = d[d["Sample Duration"].isin(["1 HOUR", "24 HOUR"])]
        d["site_id"] = site_id(d)
        rows.append(d[["site_id", "Parameter Code", "Sample Duration", "Year", "Observation Percent", "Latitude", "Longitude"]])
    a = pd.concat(rows)
    var = {88101: "pm25", 88502: "pm25", 81102: "pm10", 44201: "o3", 42602: "no2"}
    a["var"] = a["Parameter Code"].map(var)
    a.loc[(a["Sample Duration"] == "24 HOUR") & (a["Parameter Code"] == 88101), "var"] = "pm25_frm"
    a = a[(a["Sample Duration"] == "1 HOUR") | (a["var"] == "pm25_frm")]
    best = a.groupby(["site_id", "var", "Year"])["Observation Percent"].max().reset_index()
    good = best[(best["Observation Percent"] >= 75) & best.Year.isin(COMMON_YEARS)]
    n = good.groupby(["site_id", "var"]).size().unstack(fill_value=0)
    loc = a.groupby("site_id")[["Latitude", "Longitude"]].median()
    return n.join(loc)


def select_sites(min_years: int = 4, cell_deg: float = 0.25) -> pd.DataFrame:
    """Tier-1 AQS sites: >= min_years good common-window years for any variable, thinned to one
    site per `cell_deg` cell (the site with the most qualifying variables, then most years)."""
    n = completeness()
    vars_ = [c for c in ("pm25", "pm10", "o3", "no2", "pm25_frm") if c in n]
    q = n[vars_] >= min_years
    n = n[q.any(axis=1)].copy()
    n["nvars"] = q.loc[n.index].sum(axis=1)
    n["nyears"] = n[vars_].sum(axis=1)
    n["params"] = q.loc[n.index].apply(lambda r: ",".join(v for v in vars_ if r[v]), axis=1)
    n["cell"] = (np.floor(n.Latitude / cell_deg).astype(int).astype(str) + "_"
                 + np.floor(n.Longitude / cell_deg).astype(int).astype(str))
    n = n.sort_values(["nvars", "nyears"], ascending=False)
    chosen = n.groupby("cell").head(1)
    meta = read_zip_csv("aqs_sites", dtype={"State Code": str, "County Code": str, "Site Number": str})
    meta["site_id"] = site_id(meta)
    meta = meta.set_index("site_id")
    out = chosen.join(meta[["Elevation", "Location Setting", "Land Use", "Local Site Name", "City Name", "State Name",
                            "GMT Offset"]], how="left")
    out = out.reset_index().rename(columns={"index": "site_id"})
    return pd.DataFrame({
        "site_id": out.site_id, "network": "AQS", "tier": 1,
        "name": out["Local Site Name"].fillna(out["City Name"]).fillna("").astype(str).str.title(),
        "lat": out.Latitude.round(6), "lon": out.Longitude.round(6), "elev": out.Elevation,
        "country": "US", "region": "North America", "setting": out["Location Setting"].fillna("").str.lower(),
        "utc_offset": out["GMT Offset"], "params": out.params,
        "note": out.State.astype(str) if "State" in out else out["State Name"],
    })


def _hourly_year(param: int, year: int, site_ids: set[str]) -> pd.DataFrame:
    cols = ["State Code", "County Code", "Site Num", "POC", "Date GMT", "Time GMT", "Sample Measurement",
            "Units of Measure", "Method Name"]
    import pyarrow as pa
    import pyarrow.csv as pacsv

    strs = ["State Code", "County Code", "Site Num", "Date GMT", "Time GMT", "Units of Measure", "Method Name"]
    parts = []
    with zipfile.ZipFile(download(f"hourly_{param}_{year}")) as z, z.open(z.namelist()[0]) as fh:
        # stream 64 MB blocks and keep only our sites: a year's file is ~10 M rows (several GB in pandas)
        reader = pacsv.open_csv(fh, read_options=pacsv.ReadOptions(block_size=64 << 20),
                                convert_options=pacsv.ConvertOptions(include_columns=cols,
                                                                     column_types={c: pa.string() for c in strs}))
        for batch in reader:
            b = batch.to_pandas()
            b["site_id"] = site_id(b)
            b = b[b.site_id.isin(site_ids)]
            if b.empty:
                continue
            # numeric-only per block: AQS hours are labelled by their start; stamp at the end (UTC)
            parts.append(pd.DataFrame({
                "site_id": b["site_id"].astype("category"),
                "time": pd.to_datetime(b["Date GMT"] + " " + b["Time GMT"]) + pd.Timedelta(hours=1),
                "value": (b["Sample Measurement"] * b["Units of Measure"].map(UNIT_SCALE).fillna(1.0)).astype("f4"),
                "t640": b["Method Name"].str.contains("T640", na=False).values,
                "corrected": b["Method Name"].str.contains("Corrected", na=False).values}))
    if not parts:
        return pd.DataFrame(columns=["site_id", "time", "value"])
    d = pd.concat(parts, ignore_index=True)
    del parts
    d["site_id"] = d["site_id"].astype(str).astype("category")
    if param in (88101, 88502):  # prefer the corrected T640 series where both are reported
        # (bracket access: ``d.corr`` would be DataFrame.corr, not the column)
        t640, corr = d["t640"], d["corrected"]
        has_corr = d[t640 & corr].groupby(["site_id", "time"], observed=True).size()
        key = pd.MultiIndex.from_frame(d[["site_id", "time"]])
        d = d[~(t640 & ~corr & key.isin(has_corr.index))]
    out = d.groupby(["site_id", "time"], observed=True)["value"].mean().reset_index()
    out["value"] = out["value"].astype("f4")
    return out


def hourly(sites: pd.DataFrame, var: str, years=YEARS, log=print) -> pd.DataFrame:
    """Long frame (site_id, time, value) for one variable; PM2.5 prefers 88101 over 88502 per site-hour."""
    ids = set(sites.site_id)
    out = []
    for y in years:
        parts = []
        for k, param in enumerate(HOURLY[var]):
            try:
                d = _hourly_year(param, y, ids)
            except requests.HTTPError as e:  # file not (yet) published; anything else is a bug: raise
                if e.response is None or e.response.status_code != 404:
                    raise
                log(f"[AQS] hourly_{param}_{y}: {e!r}")
                continue
            d["prio"] = k
            parts.append(d)
        if parts:
            d = pd.concat(parts).sort_values("prio").drop_duplicates(["site_id", "time"]).drop(columns="prio")
            d["site_id"] = d["site_id"].astype(str).astype("category")
            out.append(d)
            log(f"[AQS] {var} {y}: {len(d):,} site-hours")
    if not out:
        return pd.DataFrame(columns=["site_id", "time", "value"])
    d = pd.concat(out, ignore_index=True)
    d["site_id"] = d["site_id"].astype(str)
    return d


def daily_frm(sites: pd.DataFrame, years=YEARS) -> pd.DataFrame:
    """24-h filter PM2.5 (88101, 24 HOUR): (site_id, date, value), local-day samples."""
    ids = set(sites.site_id)
    out = []
    for y in years:
        d = read_zip_csv(f"daily_88101_{y}", usecols=["State Code", "County Code", "Site Num", "POC", "Sample Duration",
                                                       "Date Local", "Arithmetic Mean"],
                         dtype={"State Code": str, "County Code": str, "Site Num": str})
        d = d[d["Sample Duration"] == "24 HOUR"]
        d["site_id"] = site_id(d)
        d = d[d.site_id.isin(ids)]
        out.append(d.groupby(["site_id", "Date Local"])["Arithmetic Mean"].mean().reset_index())
    d = pd.concat(out).rename(columns={"Date Local": "date", "Arithmetic Mean": "value"})
    d["date"] = pd.to_datetime(d["date"])
    return d
