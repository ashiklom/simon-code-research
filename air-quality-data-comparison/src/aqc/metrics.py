"""Skill metrics: products vs observations (Tiers 1-3) and products vs each other (Tier 4).

Rows: site x product x var x scale (hourly|daily|monthly) x window x method (nearest|bilinear).
Variables compared (obs name = product name unless noted):
  pm25, pm10, no2              hourly, daily LST mean, monthly
  o3                           hourly; daily = MDA8 ("o3_mda8"); monthly mean of MDA8
  pm25 vs pm25_frm (AQS 24-h filter FRM, daily)
  species (IMPROVE/CSN filters, daily): so4, no3, nh4, om (= 1.8 x OC), bc (= EC), dust (= fine
  soil), ss (= 1.8 x Cl); product components are mapped by ``product_species``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from . import analysis as A
from . import config

WINDOWS = {"full": (None, None), "common": config.W_COMMON, "recent": config.W_RECENT, "v1v2": config.W_V1V2}
MIN_N = {"hourly": 24 * 60, "daily": 60, "monthly": 12, "filter": 30, "smoke": 5}
GASES = ("o3", "no2")
PM_THRESH = {"pm25": (15.0, 35.0), "pm25_frm": (15.0, 35.0), "o3_mda8": (70.0,)}
AQI_PM25 = [0, 9.05, 35.45, 55.45, 125.45, 225.45, np.inf]  # US AQI 24-h PM2.5 breakpoints (2024)

OBS_OM_PER_OC = 1.8  # IMPROVE (Malm & Hand 2007 / revised algorithm)


def product_species(df: pd.DataFrame, name: str) -> pd.DataFrame:
    """Canonical PM2.5 components (ug m-3) from a product's own component names."""
    c = df.columns
    out = {}

    def pick(*names):
        for n in names:
            if n in c:
                return df[n]
        return None

    out["so4"] = pick("pm25_so4", "pm25_su", "pm25_sulfate")
    out["no3"] = pick("pm25_no3", "pm25_nit", "pm25_ni", "pm25_nitrate")
    out["nh4"] = pick("pm25_nh4", "pm25_ammonium")
    out["bc"] = pick("pm25_bc", "pm25_ec")
    out["dust"] = pick("pm25_du", "pm25_dust")
    out["ss"] = pick("pm25_ss", "pm25_seasalt")
    om = pick("pm25_om")
    if om is None:
        oc = pick("pm25_oc")
        if oc is not None:
            if name.startswith(("merra2", "geosfp")):
                om = oc * 1.4  # GOCART OC -> OM (Buchard et al. 2016), as in the PM2.5 total
            else:
                om = oc
            soa = pick("pm25_soa")
            if soa is not None:
                om = om + soa
    out["om"] = om
    return pd.DataFrame({k: v for k, v in out.items() if v is not None}, index=df.index)


def obs_species(spec: pd.DataFrame) -> pd.DataFrame:
    out = {}
    for k, v in (("so4", "pm25_so4"), ("no3", "pm25_no3"), ("nh4", "pm25_nh4"), ("bc", "pm25_ec"),
                 ("dust", "pm25_soil"), ("ss", "pm25_ss")):
        if v in spec:
            out[k] = spec[v]
    if "pm25_oc" in spec:
        out["om"] = OBS_OM_PER_OC * spec["pm25_oc"]
    return pd.DataFrame(out, index=spec.index)


# --- metric functions --------------------------------------------------------------------


def _cont(o: np.ndarray, p: np.ndarray) -> dict:
    d = p - o
    so, sp = o.std(), p.std()
    r = float(np.corrcoef(o, p)[0, 1]) if so > 0 and sp > 0 else np.nan
    alpha = sp / so if so > 0 else np.nan
    beta = p.mean() / o.mean() if abs(o.mean()) > 1e-9 else np.nan
    kge = 1 - np.sqrt((r - 1) ** 2 + (alpha - 1) ** 2 + (beta - 1) ** 2) if np.isfinite([r, alpha, beta]).all() else np.nan
    so_ = np.abs(o).sum()
    return {"mean_obs": o.mean(), "mean_prod": p.mean(), "bias": d.mean(), "mae": np.abs(d).mean(),
            "rmse": np.sqrt((d ** 2).mean()), "ubrmse": np.sqrt(((d - d.mean()) ** 2).mean()), "r": r,
            "rho": float(spearmanr(o, p).statistic) if so > 0 and sp > 0 else np.nan,
            "nmb": d.sum() / so_ if so_ > 0 else np.nan, "nme": np.abs(d).sum() / so_ if so_ > 0 else np.nan,
            "alpha": alpha, "beta": beta, "kge": kge,
            "p95_obs": np.percentile(o, 95), "p95_prod": np.percentile(p, 95)}


def _exceed(o: np.ndarray, p: np.ndarray, var: str) -> dict:
    m = {}
    for t in PM_THRESH.get(var, ()):
        ow, pw = o > t, p > t
        hits, miss, fa = (ow & pw).sum(), (ow & ~pw).sum(), (~ow & pw).sum()
        tt = int(t)
        m[f"n_exc_{tt}"] = int(ow.sum())
        m[f"pod_{tt}"] = hits / (hits + miss) if hits + miss else np.nan
        m[f"far_{tt}"] = fa / (hits + fa) if hits + fa else np.nan
        m[f"csi_{tt}"] = hits / (hits + miss + fa) if hits + miss + fa else np.nan
    if var in ("pm25", "pm25_frm"):
        m["aqi_agree"] = float((np.digitize(o, AQI_PM25) == np.digitize(p, AQI_PM25)).mean())
    return m


def compute(o: pd.Series, p: pd.Series, scale: str, var: str) -> dict | None:
    j = pd.concat([o.rename("o"), p.rename("p")], axis=1).dropna()
    if len(j) < MIN_N[scale]:
        return None
    m = _cont(j.o.values, j.p.values)
    if scale in ("daily", "filter", "smoke"):
        m.update(_exceed(j.o.values, j.p.values, var))
    m["n"] = len(j)
    m["start"], m["end"] = j.index[0], j.index[-1]
    return m


def _window(s: pd.Series, w: str) -> pd.Series:
    a, b = WINDOWS[w]
    return s if a is None else s[(s.index >= a) & (s.index <= b)]


def _windows_for(product: str) -> list[str]:
    return ["full", "common", "recent", "v1v2"] if product.startswith("geoscf") else ["full", "common", "recent"]


# --- observations at a site --------------------------------------------------------------


def site_obs(site: pd.Series, root: str | None = None) -> dict:
    """{'hourly': df, 'daily': df, 'filter_daily': df, 'species': df} (any may be None)."""
    off = A.site_offset(site)
    net = {"AQS": "AQS", "Embassy": "Embassy", "SPARTAN": "SPARTAN", "SensorCommunity": "SensorCommunity"}.get(site.network)
    out = {"hourly": None, "daily": None, "frm": None, "species": None}
    if net:
        h = A.obs_series(net, site.site_id, "1h", root)
        if net == "AQS":  # preliminary AirNow fills the months AQS has not released yet
            an = A.obs_series("AirNow", site.site_id, "1h", root)
            if an is not None and not an.empty:
                if h is not None and not h.empty:
                    an = an[an.index > h.dropna(how="all").index.max()]
                    h = pd.concat([h, an]).sort_index()
                    h = h[~h.index.duplicated()]
                else:
                    h = an
        if h is not None and not h.empty:
            out["hourly"] = h
            d = A.daily(h.drop(columns=[c for c in h if c in ("o3", "rh", "pm25_raw")], errors="ignore"), off)
            if "o3" in h:
                d["o3_mda8"] = A.mda8(h["o3"], off)
            out["daily"] = d
    if site.network == "AQS":
        f = A.obs_series("AQS", site.site_id, "1d", root)
        if f is not None and "pm25_frm" in f:
            out["frm"] = f[["pm25_frm"]]
    if site.network in ("AQS", "IMPROVE", "CSN"):
        s = A.obs_series("SPEC", site.site_id, "1d", root)
        if s is not None and not s.empty:
            out["species"] = obs_species(s)
    return out


# --- per-site driver ---------------------------------------------------------------------


def _product_scales(df: pd.DataFrame, off: float):
    """(scale, frame) pairs: hourly (if sub-daily), daily LST (or the product's day), monthly."""
    freq = df.attrs.get("freq", "1h")
    vmeta = df.attrs.get("variables", {})
    any_meta = next(iter(vmeta.values()), {}) if vmeta else {}
    if any_meta.get("period") == "month":
        return [("monthly", df)], None
    if freq in ("1h", "3h"):
        step = 1.0 if freq == "1h" else 3.0
        stamp = any_meta.get("stamp", "end")
        d = A.daily(df.drop(columns=[c for c in df if c in ("o3", "qflag")], errors="ignore"), off, step, stamp)
        if "o3" in df and freq == "1h":
            d["o3_mda8"] = A.mda8(df["o3"], off)
        elif "o3" in df:  # 3-hourly: daily max of the instantaneous values as an MDA8 proxy
            lab = A._local_start(df.index, step, off, stamp).floor("D")
            g = df["o3"].groupby(lab)
            d["o3_mda8"] = g.max().where(g.count() >= 6)
        return [("hourly", df), ("daily", d)], None
    day_def = any_meta.get("day_def", "LST")
    return [("daily", df)], ("UTC" if day_def.upper().startswith("UTC") else "LST")


SMOKE_DAY = 20.0  # HRRR-Smoke daily-mean near-surface smoke (ug m-3) defining a smoke day


def smoke_days(site: pd.Series, off: float, root: str | None = None) -> pd.DatetimeIndex | None:
    s = A.product_series("hrrr_smoke", site.site_id, root, "bilinear")
    if s is None or "pm25_smoke" not in s:
        return None
    d = A.daily(s[["pm25_smoke"]], off, 1.0, "instant")["pm25_smoke"]
    return d.index[d >= SMOKE_DAY]


def site_metrics(site: pd.Series, products: list[str], root: str | None = None) -> list[dict]:
    obs = site_obs(site, root)
    if all(v is None for v in obs.values()):
        return []
    off = A.site_offset(site)
    smoke = smoke_days(site, off, root) if site.network == "AQS" else None
    obs_utc_daily = None
    rows = []
    for name in products:
        for method in ("nearest", "bilinear"):
            df = A.product_series(name, site.site_id, root, method)
            if df is None or df.empty:
                continue
            spp = product_species(df, name)
            scales, day_def = _product_scales(df, off)
            for scale, pdf in scales:
                pairs = []  # (obs series, product series, var, scale)
                if scale == "hourly" and obs["hourly"] is not None:
                    for v in ("pm25", "pm10", "o3", "no2"):
                        if v in pdf and v in obs["hourly"]:
                            pairs.append((obs["hourly"][v], pdf[v], v, "hourly"))
                if scale == "daily":
                    od = obs["daily"]
                    if day_def == "UTC" and obs["hourly"] is not None:
                        if obs_utc_daily is None:
                            h = obs["hourly"]
                            obs_utc_daily = A.daily(h.drop(columns=[c for c in h if c in ("rh", "pm25_raw")], errors="ignore"), 0.0)
                        od = obs_utc_daily
                    if od is not None:
                        for v in ("pm25", "pm10", "no2", "o3_mda8"):
                            if v in pdf and v in od:
                                pairs.append((od[v], pdf[v], v, "daily"))
                                pairs.append((A.monthly(od[[v]])[v], A.monthly(pdf[[v]])[v], v, "monthly"))
                    if obs["frm"] is not None and "pm25" in pdf:
                        pairs.append((obs["frm"]["pm25_frm"], pdf["pm25"], "pm25_frm", "filter"))
                    if obs["species"] is not None and not spp.empty:
                        sd = A.daily(spp, off, 1.0 if df.attrs.get("freq") == "1h" else 3.0) \
                            if df.attrs.get("freq") in ("1h", "3h") else spp
                        for v in sd.columns:
                            if v in obs["species"]:
                                pairs.append((obs["species"][v], sd[v], f"spec_{v}", "filter"))
                if scale == "monthly":
                    od = obs["daily"]
                    if od is not None:
                        om = A.monthly(od)
                        for v in ("pm25", "pm10", "no2"):
                            if v in pdf and v in om:
                                pairs.append((om[v], pdf[v], v, "monthly"))
                    if obs["species"] is not None and not spp.empty:
                        osm = obs["species"].groupby(obs["species"].index.to_period("M")).mean()
                        osm.index = osm.index.to_timestamp()
                        cnt = obs["species"].groupby(obs["species"].index.to_period("M")).count()
                        osm = osm.where(cnt.values >= 6)
                        for v in spp.columns:
                            if v in osm:
                                pairs.append((osm[v], spp[v], f"spec_{v}", "monthly"))
                for o, p, v, sc in pairs:
                    wins = _windows_for(name)
                    if smoke is not None and len(smoke) and sc in ("daily", "filter") and v in ("pm25", "pm25_frm"):
                        wins = wins + ["smoke"]
                    for w in wins:
                        if w == "smoke":
                            oo, pp = o[o.index.isin(smoke)], p[p.index.isin(smoke)]
                            m = compute(oo, pp, "smoke", v)
                        else:
                            m = compute(_window(o, w), _window(p, w), "filter" if sc == "filter" else sc, v)
                        if m is None:
                            continue
                        if sc == "filter":
                            sc_out = "daily"
                        else:
                            sc_out = sc
                        rows.append({"site": site.site_id, "network": site.network, "tier": int(site.tier),
                                     "region": site.region, "product": name, "var": v, "scale": sc_out,
                                     "window": w, "method": method, **m})
    # low-cost sensor vs its co-located reference monitor
    if site.network == "SensorCommunity" and "with " in str(site.note) and obs["hourly"] is not None:
        ref_id = str(site.note).split("with ")[1].split(" ")[0]
        ref_net = "AQS" if ref_id.startswith("AQS:") else ("Embassy" if ref_id.startswith("EMB:") else "SPARTAN")
        ref = A.obs_series(ref_net, ref_id, "1h", root)
        if ref is not None and "pm25" in ref:
            for v in ("pm25", "pm25_raw"):
                if v in obs["hourly"]:
                    for w in ("full",):
                        for sc, o, p in (("hourly", ref["pm25"], obs["hourly"][v]),
                                         ("daily", A.daily(ref[["pm25"]], off)["pm25"], A.daily(obs["hourly"][[v]], off)[v])):
                            m = compute(o, p, sc, "pm25")
                            if m:
                                rows.append({"site": site.site_id, "network": site.network, "tier": 3,
                                             "region": site.region, "product": f"sensor_{v}", "var": "pm25",
                                             "scale": sc, "window": w, "method": "point", "reference_site": ref_id, **m})
    return rows


REMOTE_VARS = ["pm25", "pm10", "o3_mda8", "no2"]


def remote_metrics(site: pd.Series, products: list[str], root: str | None = None, min_products: int = 3) -> list[dict]:
    """Each product vs the median of the OTHER products (leave-one-out), monthly means."""
    off = A.site_offset(site)
    series = {v: {} for v in REMOTE_VARS}
    for name in products:
        df = A.product_series(name, site.site_id, root, "bilinear")
        if df is None or df.empty:
            continue
        scales, _ = _product_scales(df, off)
        sd = dict(scales)
        mon = sd["monthly"] if "monthly" in sd else A.monthly(sd["daily"])
        for v in REMOTE_VARS:
            if v in mon:
                series[v][name] = mon[v]
    rows = []
    for v, sdict in series.items():
        if len(sdict) < min_products:
            continue
        M = pd.DataFrame(sdict)
        for name in M.columns:
            others = M.drop(columns=name)
            ref = others.median(axis=1).where(others.notna().sum(axis=1) >= min_products - 1)
            for w in ("full", "common", "recent"):
                m = compute(_window(ref, w), _window(M[name], w), "monthly", v)
                if m is None:
                    continue
                rows.append({"site": site.site_id, "network": "Remote", "tier": 4, "region": site.region,
                             "product": name, "var": v, "scale": "monthly", "window": w, "method": "bilinear",
                             "reference": "median of other products", "n_products": M.shape[1], **m})
    return rows
