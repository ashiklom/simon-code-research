"""Loading, interpolation and time aggregation for comparisons.

Conventions (see products/base.py): all series are UTC, stamped at the END of their interval.
A daily value labelled D with ``day_end_offset_h = E`` covers (D + E - 24 h, D + E].
"""

from __future__ import annotations

import functools

import numpy as np
import pandas as pd

from . import store
from .physics import esat_kpa

# how to aggregate a variable from sub-daily to daily, by canonical name (prefix match)
DAILY_AGG = {
    "tmax": "max", "tmin": "min", "rhmax": "max", "rhmin": "min", "vpdmax": "max", "vpdmin": "min",
    "pr": "sum", "pr_gpcc": "sum",
}
STATE_MIN_FRAC = 22 / 24  # completeness for means
PRECIP_MIN_FRAC = 1.0


def agg_kind(var: str) -> str:
    return DAILY_AGG.get(var, "mean")


# --- interpolation -------------------------------------------------------------------


def nearest(values: np.ndarray, w: np.ndarray) -> np.ndarray:
    """values (4, nt), w (4,) -> (nt,) from the stencil pixel with the largest weight."""
    return values[int(np.nanargmax(w))]


def bilinear(values: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Bilinear with weights renormalized over non-missing pixels (e.g. ocean/land masks)."""
    ww = np.where(np.isnan(values), 0.0, w[:, None])
    s = ww.sum(0)
    out = np.nansum(np.nan_to_num(values) * ww, axis=0) / np.where(s > 0, s, np.nan)
    return out


# --- loading -------------------------------------------------------------------------


@functools.lru_cache(maxsize=64)
def _product_groups(root: str | None):
    from .products import registry

    out = {}
    for name in registry.names():
        p = registry.get(name)
        try:
            out[name] = (store.readonly("products", name, root), store.group_path("products", name, p.freq), p.freq)
        except FileNotFoundError:
            continue
    return out


def product_series(name: str, site: str, root: str | None = None, method: str = "bilinear") -> pd.DataFrame | None:
    """All variables of a product at a site as a DataFrame (time index), NN or bilinear."""
    groups = _product_groups(root)
    if name not in groups:
        return None
    sess, path, freq = groups[name]
    try:
        ds = store.read_group(sess, path, sites=[site])
    except Exception:
        return None
    if ds.sizes.get("site", 0) == 0:
        return None
    w = ds.w.values[0]
    f = nearest if method == "nearest" else bilinear
    cols = {}
    for v in ds.attrs.get("variables", {}):
        if v in ds:
            cols[v] = f(ds[v].values[0], w)
    df = pd.DataFrame(cols, index=pd.DatetimeIndex(ds.time.values))
    df.attrs["variables"] = ds.attrs.get("variables", {})
    df.attrs["freq"] = freq
    df.attrs["px_elev"] = ds.px_elev.values[0] if "px_elev" in ds else None
    return df.dropna(how="all")


def obs_series(network: str, site: str, root: str | None = None) -> pd.DataFrame | None:
    try:
        sess = store.readonly("obs", network, root)
    except FileNotFoundError:
        return None
    ds = store.read_group(sess, store.group_path("obs", network, "1h"), sites=[site])
    if ds.sizes.get("site", 0) == 0:
        return None
    df = pd.DataFrame({v: ds[v].values[0] for v in ds.attrs.get("variables", {}) if v in ds}, index=pd.DatetimeIndex(ds.time.values))
    df.attrs["variables"] = ds.attrs.get("variables", {})
    return df.dropna(how="all")


# --- aggregation ---------------------------------------------------------------------


def to_hourly(df: pd.DataFrame) -> pd.DataFrame:
    """30-min end-stamped -> hourly end-stamped (sum precip, mean others; both halves required)."""
    lab = df.index.ceil("h")
    g = df.groupby(lab)
    n = g.count()
    out = {}
    for c in df.columns:
        a = g[c].sum(min_count=2) if agg_kind(c) == "sum" else g[c].mean()
        out[c] = a.where(n[c] >= 2)
    return pd.DataFrame(out)


def daily(df: pd.DataFrame, end_offset_h: float, steps_per_day: int, vars_: list[str] | None = None,
          kinds: dict[str, str] | None = None) -> pd.DataFrame:
    """Aggregate end-stamped sub-daily series to days ending `end_offset_h` after the label's 00 UTC."""
    vars_ = vars_ or list(df.columns)
    lab = (df.index - pd.Timedelta(hours=end_offset_h)).ceil("D")
    sub = df[vars_]
    g = sub.groupby(lab)
    n = g.count()
    out = {}
    for c in vars_:
        k = (kinds or {}).get(c, agg_kind(c))
        need = steps_per_day * (PRECIP_MIN_FRAC if k == "sum" else STATE_MIN_FRAC)
        a = getattr(g[c], k)()
        out[c] = a.where(n[c] >= need - 1e-9)
    res = pd.DataFrame(out)
    res.index.name = "time"
    return res


def monthly(dfd: pd.DataFrame, min_frac: float = 0.9) -> pd.DataFrame:
    g = dfd.groupby(dfd.index.to_period("M"))
    n = g.count()
    days = pd.Series({p: p.days_in_month for p in g.groups}).reindex(n.index)
    out = {}
    for c in dfd.columns:
        a = g[c].sum() if agg_kind(c) == "sum" else g[c].mean()
        out[c] = a.where(n[c] >= min_frac * days.values)
    res = pd.DataFrame(out)
    res.index = res.index.to_timestamp()
    return res


def lst_offset_h(lon: float) -> int:
    """Local standard time offset (hours, negative west) from longitude."""
    return int(round(lon / 15.0))


def station_daily(obs_h: pd.DataFrame, end_offset_h: float) -> pd.DataFrame:
    """Daily station values for a given day window; adds max/min of RH and VPD."""
    o = obs_h.copy()
    o["rhmax"] = o.get("rh")
    o["rhmin"] = o.get("rh")
    o["vpdmax"] = o.get("vpd")
    o["vpdmin"] = o.get("vpd")
    return daily(o, end_offset_h, 24)


def add_station_humidity(df: pd.DataFrame, elev_m: float) -> pd.DataFrame:
    """Specific humidity (g/kg) and vapour pressure (kPa) from dewpoint + standard-atmosphere pressure."""
    if "tdew" not in df:
        return df
    p = 101325.0 * (1 - 2.25577e-5 * elev_m) ** 5.25588
    e = esat_kpa(df["tdew"].values) * 1000
    df = df.copy()
    df["q"] = 1000 * 0.622 * e / (p - 0.378 * e)
    df["vp"] = e / 1000
    return df
