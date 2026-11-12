"""Pairing of product variables with station variables, and skill metrics.

For every site x product x variable we compare at three scales (hourly where the product is
sub-daily; daily using the product's own day window; monthly from daily), three windows
(full overlap, W-common, W-recent) and two spatial methods (nearest, bilinear).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import analysis as A
from . import config

WINDOWS = {"full": (None, None), "common": config.W_COMMON, "recent": config.W_RECENT}
DIRECT = {"tair", "tmax", "tmin", "pr", "sw", "tsurf", "rh", "tdew", "vpd", "q", "vp", "rhmax", "rhmin", "vpdmax", "vpdmin"}
OBS_SM = {5: "sm05", 10: "sm10", 20: "sm20", 50: "sm50", 100: "sm100"}
OBS_TS = {5: "ts05", 10: "ts10", 20: "ts20", 50: "ts50", 100: "ts100"}
Z0 = 0.03  # m, roughness for log-law wind height adjustment (short grass, typical USCRN siting)
OBS_WIND_H = 1.5
PRECIP_THRESH = (0.25, 1.0, 10.0)  # mm/day


def _depths(obs_cols, prefix):
    import re

    out = {}
    for c in obs_cols or []:
        m = re.fullmatch(prefix + r"(\d+)", c)
        if m:
            out[int(m.group(1))] = c
    return out


def pairs_for(var: str, attrs: dict, obs_cols=None) -> list[tuple[str, str]]:
    """(obs_var, pair_kind) matches for a product variable (obs soil columns sm<cm>/ts<cm>)."""
    sm = _depths(obs_cols, "sm") if obs_cols is not None else OBS_SM
    ts = _depths(obs_cols, "ts") if obs_cols is not None else OBS_TS
    if var == "pr_gpcc":
        return [("pr", "precip")]
    if var in DIRECT:
        return [(var, "precip" if var == "pr" else "cont")]
    if var.startswith(("soilm", "wet_", "soilw")):
        top, bot = attrs.get("depth_top_cm"), attrs.get("depth_bot_cm")
        if top is None or bot is None:
            top, bot = (0, 10) if var.endswith("1") else (None, None)
        if top is None:
            return []
        kind = "anom" if attrs.get("wetness") else "sm"
        return [(o, kind) for d, o in sm.items() if top < d <= bot]
    if var.startswith("tsoil"):
        top, bot = attrs.get("depth_top_cm"), attrs.get("depth_bot_cm")
        if top is None:
            return []
        return [(o, "cont") for d, o in ts.items() if top < d <= bot]
    if var in ("wind", "wind2m"):
        return [("wind", "wind")]
    return []


def wind_factor(h: float) -> float:
    return np.log(OBS_WIND_H / Z0) / np.log(h / Z0)


# --- metric functions -----------------------------------------------------------------


def _cont(o: np.ndarray, p: np.ndarray) -> dict:
    d = p - o
    so, sp = o.std(), p.std()
    r = float(np.corrcoef(o, p)[0, 1]) if so > 0 and sp > 0 else np.nan
    alpha = sp / so if so > 0 else np.nan
    beta = p.mean() / o.mean() if abs(o.mean()) > 1e-9 else np.nan
    kge = 1 - np.sqrt((r - 1) ** 2 + (alpha - 1) ** 2 + (beta - 1) ** 2) if np.isfinite([r, alpha, beta]).all() else np.nan
    return {"mean_obs": o.mean(), "mean_prod": p.mean(), "bias": d.mean(), "mae": np.abs(d).mean(),
            "rmse": np.sqrt((d ** 2).mean()), "ubrmse": np.sqrt(((d - d.mean()) ** 2).mean()), "r": r,
            "alpha": alpha, "beta": beta, "kge": kge, "err_p05": np.percentile(d, 5), "err_p95": np.percentile(d, 95)}


def _precip(o: np.ndarray, p: np.ndarray, scale: str) -> dict:
    m = _cont(o, p)
    m["ratio"] = p.sum() / o.sum() if o.sum() > 0 else np.nan
    if scale == "daily":
        for t in PRECIP_THRESH:
            ow, pw = o >= t, p >= t
            hits, miss, fa = (ow & pw).sum(), (ow & ~pw).sum(), (~ow & pw).sum()
            m[f"pod_{t}"] = hits / (hits + miss) if hits + miss else np.nan
            m[f"far_{t}"] = fa / (hits + fa) if hits + fa else np.nan
            m[f"csi_{t}"] = hits / (hits + miss + fa) if hits + miss + fa else np.nan
        m["wetfrac_obs"], m["wetfrac_prod"] = (o >= 1).mean(), (p >= 1).mean()
        wo, wp = o[o >= 1], p[p >= 1]
        if len(wo) >= 20 and len(wp) >= 20:
            m["p95_ratio"] = np.percentile(wp, 95) / np.percentile(wo, 95)
            m["p99_ratio"] = np.percentile(wp, 99) / np.percentile(wo, 99)
    return m


def _anom(o: pd.Series, p: pd.Series) -> dict:
    """Anomaly correlation after removing each series' mean annual cycle (by month)."""
    mo = o.groupby(o.index.month).transform("mean")
    mp = p.groupby(p.index.month).transform("mean")
    ao, ap = (o - mo).values, (p - mp).values
    r = float(np.corrcoef(ao, ap)[0, 1]) if ao.std() > 0 and ap.std() > 0 else np.nan
    ro = float(np.corrcoef(o.values, p.values)[0, 1]) if o.std() > 0 and p.std() > 0 else np.nan
    return {"anom_r": r, "r": ro, "mean_obs": o.mean(), "mean_prod": p.mean()}


def compute(o: pd.Series, p: pd.Series, kind: str, scale: str, min_n: int) -> dict | None:
    j = pd.concat([o.rename("o"), p.rename("p")], axis=1).dropna()
    if len(j) < min_n:
        return None
    if kind == "precip":
        m = _precip(j.o.values, j.p.values, scale)
    elif kind == "anom":
        m = _anom(j.o, j.p)
    elif kind == "sm":
        m = {**_cont(j.o.values, j.p.values), **{k: v for k, v in _anom(j.o, j.p).items() if k == "anom_r"}}
    else:
        m = _cont(j.o.values, j.p.values)
    m["n"] = len(j)
    m["start"], m["end"] = j.index[0], j.index[-1]
    return m


MIN_N = {"hourly": 24 * 60, "daily": 90, "monthly": 12}


def _window(s: pd.Series, w) -> pd.Series:
    a, b = WINDOWS[w]
    return s if a is None else s[(s.index >= a) & (s.index <= b)]


# --- per-site driver -----------------------------------------------------------------


def day_overrides() -> dict[tuple[str, str], float]:
    """(product, var) -> day_end_offset_h from the lag check (USCRN-wide if available, else pilot)."""
    for name in ("uscrn", "pilot"):
        f = config.RESULTS / f"day_window_overrides_{name}.csv"
        if f.exists():
            d = pd.read_csv(f)
            d = d[d.use_h != d.documented_h]
            return {(r.product, r.var): float(r.use_h) for r in d.itertuples()}
    return {}


def site_metrics(site: pd.Series, products: list[str], network: str = "USCRN", root: str | None = None) -> list[dict]:
    obs_h = A.obs_series(network, site.site_id, root)
    if obs_h is None or obs_h.empty:
        return []
    obs_h = A.add_station_humidity(obs_h, float(site.elev_m))
    lst = A.lst_offset_h(site.lon)
    obs_daily_cache: dict[float, pd.DataFrame] = {}

    def obs_daily(E):
        if E not in obs_daily_cache:
            obs_daily_cache[E] = A.station_daily(obs_h, E)
        return obs_daily_cache[E]

    rows = []
    overrides = day_overrides()
    for name in products:
        for method in ("nearest", "bilinear"):
            df = A.product_series(name, site.site_id, root, method)
            if df is None or df.empty:
                continue
            vattrs = df.attrs["variables"]
            freq = df.attrs["freq"]
            sub_daily = freq in ("1h", "30min")
            if freq == "30min":
                df = A.to_hourly(df)
            # wind height adjustment (log law) as extra pseudo-variables
            for wv in ("wind", "wind2m"):
                if wv in df and "height_m" in vattrs.get(wv, {}):
                    df[wv + "_adj"] = df[wv] * wind_factor(vattrs[wv]["height_m"])
                    vattrs = {**vattrs, wv + "_adj": {**vattrs[wv], "adjusted_to_m": OBS_WIND_H}}
            scales = []
            if sub_daily:
                scales.append(("hourly", df, obs_h, None))
                d = df.copy()
                if "tair" in d:
                    d["tmax"] = d.get("tmax", d["tair"])
                    d["tmin"] = d.get("tmin", d["tair"])
                    for c in ("rh", "vpd"):
                        if c in d:
                            d[c + "max"], d[c + "min"] = d[c], d[c]
                pdaily = A.daily(d, 24, 24)
                scales.append(("daily", pdaily, obs_daily(24), 24))
            else:
                # daily products: group variables by day window and compare to matching station days
                for v in df.columns:
                    a = vattrs.get(v, {})
                    E = a.get("day_end_offset_h", 24 - lst if a.get("day_def") == "LST" else 24)
                    E = overrides.get((name, v), E)  # empirically aligned window (see diagnostics.overrides_from)
                    scales.append(("daily", df[[v]], obs_daily(E), E))
            for scale, pdf, odf, E in scales:
                for v in pdf.columns:
                    base_v = v.removesuffix("_adj")
                    a = vattrs.get(v, vattrs.get(base_v, {}))
                    for ov, kind in pairs_for(base_v, a, list(odf.columns)):
                        if ov not in odf:
                            continue
                        o, p = odf[ov], pdf[v]
                        variants = [(scale, o, p)]
                        if scale == "daily":
                            variants.append(("monthly", A.monthly(odf[[ov]])[ov], A.monthly(pdf[[v]])[v]))
                        for sc, oo, pp in variants:
                            for w in WINDOWS:
                                m = compute(_window(oo, w), _window(pp, w), kind, sc, MIN_N[sc])
                                if m is None:
                                    continue
                                rows.append({"site": site.site_id, "network": network, "product": name, "var": v,
                                             "obs_var": ov, "kind": kind, "scale": sc, "window": w, "method": method,
                                             "day_end_offset_h": E, **m})
    return rows
