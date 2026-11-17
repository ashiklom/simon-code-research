"""Loading, interpolation and time aggregation for comparisons.

Conventions: series are UTC. Interval means are stamped at the END of their interval
(product attr ``stamp = "end"``, the default); instantaneous fields (CAMS, 3-hourly) carry
``stamp = "instant"``. Daily values are local-standard-time (LST) days unless a daily product
declares ``day_def = "UTC"``; monthly products carry ``period = "month"``.
"""

from __future__ import annotations

import functools

import numpy as np
import pandas as pd

from . import store

DAY_MIN_FRAC = 18 / 24  # completeness for daily means (AQS uses 18 of 24 hours)
MONTH_MIN_FRAC = 0.75


# --- interpolation (vendored from climate-product-compare/src/cpc/analysis.py) ------------


def nearest(values: np.ndarray, w: np.ndarray) -> np.ndarray:
    return values[int(np.nanargmax(w))]


def bilinear(values: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Bilinear with weights renormalized over non-missing pixels."""
    ww = np.where(np.isnan(values), 0.0, w[:, None])
    s = ww.sum(0)
    return np.nansum(np.nan_to_num(values) * ww, axis=0) / np.where(s > 0, s, np.nan)


# --- loading -----------------------------------------------------------------------------


@functools.lru_cache(maxsize=8)
def _product_groups(root: str | None):
    from .products import registry

    out = {}
    for name in registry.names():
        try:
            p = registry.get(name)
            out[name] = (store.readonly("products", name, root), store.group_path("products", name, p.freq), p.freq)
        except Exception:
            continue
    return out


def available_products(root: str | None = None) -> list[str]:
    return list(_product_groups(root))


def product_series(name: str, site: str, root: str | None = None, method: str = "bilinear",
                   variables: list[str] | None = None) -> pd.DataFrame | None:
    groups = _product_groups(root)
    if name not in groups:
        return None
    sess, path, freq = groups[name]
    try:
        ds = store.read_group(sess, path, sites=[site], variables=variables)
    except Exception:
        return None
    if ds.sizes.get("site", 0) == 0:
        return None
    w = ds.w.values[0]
    if not np.isfinite(w).any():
        return None
    f = nearest if method == "nearest" else bilinear
    vmeta = ds.attrs.get("variables", {})
    cols = {v: f(ds[v].values[0], w) for v in vmeta if v in ds}
    df = pd.DataFrame(cols, index=pd.DatetimeIndex(ds.time.values))
    df.attrs.update({"variables": vmeta, "freq": freq, "title": ds.attrs.get("title", name)})
    return df.dropna(how="all")


@functools.lru_cache(maxsize=16)
def _obs_group(network: str, freq: str, root: str | None):
    sess = store.readonly("obs", network, root)
    return sess, store.group_path("obs", network, freq)


def obs_series(network: str, site: str, freq: str = "1h", root: str | None = None) -> pd.DataFrame | None:
    try:
        sess, path = _obs_group(network, freq, root)
        ds = store.read_group(sess, path, sites=[site])
    except Exception:
        return None
    if ds.sizes.get("site", 0) == 0:
        return None
    df = pd.DataFrame({v: ds[v].values[0] for v in ds.attrs.get("variables", {}) if v in ds},
                      index=pd.DatetimeIndex(ds.time.values))
    return df.dropna(how="all")


# --- aggregation -------------------------------------------------------------------------


def _local_start(index: pd.DatetimeIndex, step_h: float, offset_h: float, stamp: str) -> pd.DatetimeIndex:
    """Local-standard-time instant identifying which day a value belongs to."""
    t = index + pd.Timedelta(hours=offset_h)
    if stamp == "end":
        t = t - pd.Timedelta(hours=step_h)  # interval start
    return t


def daily(df: pd.DataFrame, offset_h: float, step_h: float = 1.0, stamp: str = "end") -> pd.DataFrame:
    """Daily means over LST days (offset_h = UTC offset; 0 for UTC days). Index = local date."""
    lab = _local_start(df.index, step_h, offset_h, stamp).floor("D")
    g = df.groupby(lab)
    n = g.count()
    need = DAY_MIN_FRAC * 24 / step_h
    res = g.mean().where(n >= need - 1e-9)
    res.index.name = "date"
    return res


def mda8(o3: pd.Series, offset_h: float) -> pd.Series:
    """Daily maximum 8-hour average O3 (hourly, end-stamped input). Windows need >= 6 of 8 hours;
    a day needs >= 18 valid windows (US EPA convention, simplified). Index = local date."""
    s = o3.asfreq("h")
    roll = s.rolling(8, min_periods=6).mean()  # labelled at the window's last hour END
    start = roll.index - pd.Timedelta(hours=8) + pd.Timedelta(hours=offset_h)  # local window start
    r = pd.Series(roll.values, index=start.floor("D"))
    g = r.groupby(level=0)
    out = g.max().where(g.count() >= 18)
    out.index.name = "date"
    return out


def monthly(dfd: pd.DataFrame, min_frac: float = MONTH_MIN_FRAC) -> pd.DataFrame:
    g = dfd.groupby(dfd.index.to_period("M"))
    n = g.count()
    days = pd.Series({p: p.days_in_month for p in g.groups}).reindex(n.index)
    res = g.mean().where(n.ge(min_frac * days.values, axis=0))
    res.index = res.index.to_timestamp()
    return res


@functools.lru_cache(maxsize=4096)
def std_offset(lat: float, lon: float) -> float:
    """UTC offset (h) of local standard time at a point (IANA zone via timezonefinder)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from timezonefinder import TimezoneFinder

    tz = _tf().timezone_at(lat=lat, lng=lon)
    if tz is None:
        return float(round(lon / 15.0))
    z = ZoneInfo(tz)
    return min(datetime(2023, m, 15, tzinfo=z).utcoffset().total_seconds() / 3600 for m in (1, 7))


@functools.cache
def _tf():
    from timezonefinder import TimezoneFinder

    return TimezoneFinder()


def site_offset(site) -> float:
    off = getattr(site, "utc_offset", np.nan)
    try:
        off = float(off)
    except (TypeError, ValueError):
        off = np.nan
    if site.network == "SensorCommunity" or not np.isfinite(off):
        return std_offset(float(site.lat), float(site.lon))
    return off
