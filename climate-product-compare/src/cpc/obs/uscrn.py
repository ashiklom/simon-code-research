"""USCRN station data (NCEI). hourly02 for everything except wind; subhourly01 for 1.5 m wind.

All series are stamped in UTC at the end of the hour. Only QC-good values (flag 0) are kept;
missing sentinels (-9999, -99) become NaN. Derived: dewpoint, VPD, specific humidity not
(no pressure observed).
"""

from __future__ import annotations

import io
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from .. import config, http
from ..physics import dewpoint_from_rh, vpd_kpa

BASE = "https://www.ncei.noaa.gov/pub/data/uscrn/products"
NETWORK = "USCRN"

H_COLS = ("WBANNO UTC_DATE UTC_TIME LST_DATE LST_TIME CRX_VN LONGITUDE LATITUDE T_CALC T_HR_AVG T_MAX T_MIN "
          "P_CALC SOLARAD SOLARAD_FLAG SOLARAD_MAX SOLARAD_MAX_FLAG SOLARAD_MIN SOLARAD_MIN_FLAG SUR_TEMP_TYPE "
          "SUR_TEMP SUR_TEMP_FLAG SUR_TEMP_MAX SUR_TEMP_MAX_FLAG SUR_TEMP_MIN SUR_TEMP_MIN_FLAG RH_HR_AVG "
          "RH_HR_AVG_FLAG SOIL_MOISTURE_5 SOIL_MOISTURE_10 SOIL_MOISTURE_20 SOIL_MOISTURE_50 SOIL_MOISTURE_100 "
          "SOIL_TEMP_5 SOIL_TEMP_10 SOIL_TEMP_20 SOIL_TEMP_50 SOIL_TEMP_100").split()
S_COLS = ("WBANNO UTC_DATE UTC_TIME LST_DATE LST_TIME CRX_VN LONGITUDE LATITUDE AIR_TEMPERATURE PRECIPITATION "
          "SOLAR_RADIATION SR_FLAG SURFACE_TEMPERATURE ST_TYPE ST_FLAG RELATIVE_HUMIDITY RH_FLAG SOIL_MOISTURE_5 "
          "SOIL_TEMPERATURE_5 WETNESS WET_FLAG WIND_1_5 WIND_FLAG").split()

# canonical variable -> (kind, units, attrs)
VARS = {
    "tair": ("temp", "degC", {"desc": "hourly mean air temperature (T_HR_AVG)"}),
    "tmax": ("temp", "degC", {"desc": "max of 5-min air temperature within hour (T_MAX)"}),
    "tmin": ("temp", "degC", {"desc": "min of 5-min air temperature within hour (T_MIN)"}),
    "pr": ("precip", "mm", {"desc": "precipitation total over hour (P_CALC)"}),
    "sw": ("rad", "W m-2", {"desc": "mean global solar radiation (SOLARAD)"}),
    "tsurf": ("temp", "degC", {"desc": "mean infrared surface temperature (SUR_TEMP)"}),
    "rh": ("rh", "%", {"desc": "mean relative humidity (RH_HR_AVG)"}),
    "tdew": ("temp", "degC", {"desc": "dewpoint from T_HR_AVG and RH_HR_AVG (Magnus)"}),
    "vpd": ("vpd", "kPa", {"desc": "vapour pressure deficit from T_HR_AVG and RH_HR_AVG"}),
    "wind": ("wind", "m s-1", {"desc": "mean wind speed at 1.5 m (subhourly WIND_1_5)", "height_m": 1.5}),
    **{f"sm{d:02d}": ("sm", "m3 m-3", {"desc": f"soil moisture at {d} cm", "depth_cm": d}) for d in (5, 10, 20, 50, 100)},
    **{f"ts{d:02d}": ("temp", "degC", {"desc": f"soil temperature at {d} cm", "depth_cm": d}) for d in (5, 10, 20, 50, 100)},
}


def stations() -> pd.DataFrame:
    """Commissioned, operational USCRN stations in the US."""
    txt = http.get(f"{BASE}/stations.tsv").content.decode("utf-8")
    df = pd.read_csv(io.StringIO(txt), sep="\t", dtype=str)
    ok_status = (df.STATUS == "Commissioned") | ((df.STATUS == "Experimental") & (df.STATE == "HI"))
    df = df[(df.NETWORK == "USCRN") & ok_status & (df.OPERATION == "Operational") & (df.COUNTRY == "US")
            & df.WBAN.str.fullmatch(r"\d{5}")]
    out = pd.DataFrame({
        "site_id": "USCRN:" + df.WBAN,
        "network": NETWORK,
        "tier": 1,
        "name": df.STATE + " " + df.LOCATION + " " + df.VECTOR.fillna(""),
        "state": df.STATE,
        "lat": df.LATITUDE.astype(float),
        "lon": df.LONGITUDE.astype(float),
        "elev_m": (df.ELEVATION.astype(float) * 0.3048).round(1),
        "start": pd.to_datetime(df.COMMISSIONING).dt.normalize(),
        "file_stub": (df.STATE + "_" + df.LOCATION + "_" + df.VECTOR.fillna("")).map(_ascii).str.replace(" ", "_").str.rstrip("_"),
        "wban": df.WBAN,
    })
    return out.reset_index(drop=True)


def _ascii(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


_listing_cache: dict[tuple[str, int], list[str]] = {}


def _year_files(product: str, year: int) -> list[str]:
    key = (product, year)
    if key not in _listing_cache:
        html = http.get(f"{BASE}/{product}/{year}/").text
        _listing_cache[key] = sorted(set(re.findall(r'href="([^"]+\.txt)"', html)))
    return _listing_cache[key]


def _file_for(product: str, prefix: str, year: int, stub: str) -> str | None:
    want = f"{prefix}-{year}-{stub}.txt"
    files = _year_files(product, year)
    if want in files:
        return f"{BASE}/{product}/{year}/{want}"
    # tolerate small naming differences (e.g. punctuation in LOCATION)
    norm = lambda s: re.sub(r"[^A-Za-z0-9]", "", s).lower()  # noqa: E731
    for f in files:
        if norm(f) == norm(want):
            return f"{BASE}/{product}/{year}/{f}"
    return None


def _read(url: str, cols: list[str]) -> pd.DataFrame:
    txt = http.get(url, timeout=300).text
    return pd.read_csv(io.StringIO(txt), sep=r"\s+", header=None, names=cols,
                       dtype={"UTC_DATE": str, "UTC_TIME": str, "LST_DATE": str, "LST_TIME": str, "CRX_VN": str,
                              "SUR_TEMP_TYPE": str, "ST_TYPE": str})


def _utc(df: pd.DataFrame) -> pd.DatetimeIndex:
    return pd.to_datetime(df.UTC_DATE + df.UTC_TIME.str.zfill(4), format="%Y%m%d%H%M")


def hourly_year(stub: str, year: int) -> pd.DataFrame | None:
    url = _file_for("hourly02", "CRNH0203", year, stub)
    if url is None:
        return None
    d = _read(url, H_COLS)
    num = d.select_dtypes("number").columns
    d[num] = d[num].mask(d[num] <= -9999)  # -9999 and -99999 sentinels
    d = d.replace([-99.0], np.nan)
    good = lambda f: d[f] == 0  # noqa: E731
    out = pd.DataFrame(index=_utc(d))
    out["tair"] = d.T_HR_AVG.values
    out["tmax"] = d.T_MAX.values
    out["tmin"] = d.T_MIN.values
    out["pr"] = d.P_CALC.values
    out["sw"] = d.SOLARAD.where(good("SOLARAD_FLAG")).values
    out["tsurf"] = d.SUR_TEMP.where(good("SUR_TEMP_FLAG") & d.SUR_TEMP_TYPE.isin(["C", "R"])).values
    out["rh"] = d.RH_HR_AVG.where(good("RH_HR_AVG_FLAG")).values
    for dep in (5, 10, 20, 50, 100):
        sm = d[f"SOIL_MOISTURE_{dep}"]
        out[f"sm{dep:02d}"] = sm.where((sm >= 0) & (sm <= 0.6)).values
        out[f"ts{dep:02d}"] = d[f"SOIL_TEMP_{dep}"].values
    out["tdew"] = dewpoint_from_rh(out.tair.values, out.rh.values)
    out["vpd"] = vpd_kpa(out.tair.values, out.rh.values)
    out.index.name = "time"
    return out[~out.index.duplicated()]


def wind_year(stub: str, year: int) -> pd.Series | None:
    """Hourly mean 1.5 m wind from 5-minute data (>= 10 of 12 good values)."""
    url = _file_for("subhourly01", "CRNS0101-05", year, stub)
    if url is None:
        return None
    d = _read(url, S_COLS)
    t = _utc(d)
    w = d.WIND_1_5.where((d.WIND_FLAG == 0) & (d.WIND_1_5 > -99)).values
    s = pd.Series(w, index=t)
    # 5-min stamps are end-of-period; hour ending at H covers (H-1h, H]
    hr = s.index.ceil("h")
    g = s.groupby(hr)
    mean, n = g.mean(), g.count()
    return mean.where(n >= 10).rename("wind")


def fetch_stub(stub: str, years: list[int], wind: bool = True) -> pd.DataFrame:
    parts = []
    for y in years:
        h = hourly_year(stub, y)
        if h is None:
            continue
        if wind:
            w = wind_year(stub, y)
            h["wind"] = w.reindex(h.index) if w is not None else np.nan
        parts.append(h)
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts).sort_index()


def fetch_site(row, years) -> pd.DataFrame:
    return fetch_stub(row.file_stub, years, wind=True)


def ingest(writer, sites: pd.DataFrame, years: list[int], *, wind: bool = True, workers: int = 6, log=print):
    """Fetch hourly series for `sites` and write them through a store.GroupWriter."""
    from ..store import VarSpec

    specs = {k: VarSpec(k, *v) for k, v in VARS.items()}
    tax = pd.date_range(pd.Timestamp(f"{min(years)}-01-01 01:00"), pd.Timestamp(f"{max(years) + 1}-01-01 00:00"), freq="h")

    def one(row):
        df = fetch_stub(row.file_stub, years, wind=wind)
        return row.site_id, df

    with ThreadPoolExecutor(workers) as ex:
        for sid, df in ex.map(one, sites.itertuples()):
            if df.empty:
                log(f"  {sid}: no data")
                continue
            df = df.reindex(tax[(tax >= df.index[0]) & (tax <= df.index[-1])])
            data = {k: df[k].to_numpy()[None, :] for k in VARS if k in df}
            writer.write([sid], df.index, data, specs)
            log(f"  {sid}: {df.index[0]:%Y-%m-%d} .. {df.index[-1]:%Y-%m-%d}, {df.tair.notna().sum()} h tair")


def available_end() -> pd.Timestamp:
    """Latest hour in the current-year hourly02 file of a long-running station."""
    y = pd.Timestamp.now(tz="UTC").year
    d = hourly_year("TX_Monahans_6_ENE", y)
    return d.index[d.tair.notna()][-1] if d is not None else pd.Timestamp(f"{y}-01-01")


_ = config  # noqa
