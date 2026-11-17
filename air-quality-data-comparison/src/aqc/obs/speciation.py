"""IMPROVE and CSN 24-h filter PM2.5 speciation from AQS ``daily_SPEC_<year>.zip`` (no key).

Network is told apart by method name (IMPROVE Module A/B/C vs CSN SASS/SuperSASS/URG). Values
are local-day 24-h samples (every 3rd or 6th day). Canonical variables (ug m-3, as measured):

    pm25_so4   sulfate ion (88403)
    pm25_no3   total nitrate (88306)
    pm25_nh4   ammonium ion (88301; CSN only — IMPROVE does not measure it)
    pm25_oc    organic carbon, TOR (IMPROVE 88320; CSN 88370)
    pm25_ec    elemental carbon, TOR (IMPROVE 88321; CSN 88380)
    pm25_soil  fine soil = 2.2 Al + 2.49 Si + 1.63 Ca + 2.42 Fe + 1.94 Ti (IMPROVE formula)
    pm25_ss    sea salt = 1.8 x chloride (88203)

Site ids follow AQS (``AQS:SS-CCC-NNNN``), so CSN sites that are also Tier-1 AQS sites share ids.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .aqs import COMMON_YEARS, YEARS, read_zip_csv, site_id

CODES = {88403: "so4", 88306: "no3", 88301: "nh4", 88320: "oc", 88370: "oc", 88321: "ec", 88380: "ec",
         88104: "al", 88165: "si", 88111: "ca", 88126: "fe", 88161: "ti", 88203: "cl"}


def _year(y: int) -> pd.DataFrame:
    d = read_zip_csv(f"daily_SPEC_{y}", usecols=["State Code", "County Code", "Site Num", "Parameter Code", "POC",
                                                 "Latitude", "Longitude", "Date Local", "Arithmetic Mean",
                                                 "Method Name", "Local Site Name", "State Name"],
                     dtype={"State Code": str, "County Code": str, "Site Num": str})
    d = d[d["Parameter Code"].isin(CODES)]
    d["site_id"] = site_id(d)
    m = d["Method Name"].fillna("")
    d["net"] = np.where(m.str.contains("IMPROVE"), "IMPROVE", "CSN")
    d["sp"] = d["Parameter Code"].map(CODES)
    return d


def load(years=YEARS) -> pd.DataFrame:
    """Long frame: site_id, net, date, var, value (+ lat/lon/name)."""
    d = pd.concat([_year(y) for y in years])
    w = d.pivot_table(index=["site_id", "Date Local"], columns="sp", values="Arithmetic Mean", aggfunc="mean")
    out = pd.DataFrame(index=w.index)
    for v in ("so4", "no3", "nh4", "oc", "ec"):
        if v in w:
            out[f"pm25_{v}"] = w[v]
    soil = 2.2 * w.get("al") + 2.49 * w.get("si") + 1.63 * w.get("ca") + 2.42 * w.get("fe") + 1.94 * w.get("ti")
    out["pm25_soil"] = soil
    out["pm25_ss"] = 1.8 * w.get("cl")
    out = out.reset_index().rename(columns={"Date Local": "date"})
    out["date"] = pd.to_datetime(out.date)
    meta = d.groupby("site_id").agg(net=("net", lambda s: s.mode().iat[0]), lat=("Latitude", "median"),
                                    lon=("Longitude", "median"), name=("Local Site Name", "first"),
                                    state=("State Name", "first"))
    return out, meta


def sites(log=print) -> pd.DataFrame:
    """Filter sites with sulfate on >= 50 % of their 1-in-3 schedule in >= 4 common-window years."""
    data, meta = load(COMMON_YEARS)
    data["year"] = data.date.dt.year
    n = data.dropna(subset=["pm25_so4"]).groupby(["site_id", "year"]).size().unstack(fill_value=0)
    good = (n >= 60).sum(axis=1) >= 4
    ids = good[good].index
    m = meta.loc[ids]
    log(f"[SPEC] {len(m)} filter sites ({m.net.value_counts().to_dict()})")
    return pd.DataFrame({"site_id": m.index, "network": m.net.values, "tier": 1,
                         "name": m.name.fillna("").astype(str).str.title().values, "lat": m.lat.values,
                         "lon": m.lon.values, "elev": np.nan, "country": "US", "region": "North America",
                         "setting": np.where(m.net.values == "IMPROVE", "rural", ""), "utc_offset": np.nan,
                         "params": "species", "note": m.state.values})
