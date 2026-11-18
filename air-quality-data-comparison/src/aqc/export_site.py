"""Export per-site data for the static website (site/public/data/...).

Adapted from climate-product-compare/src/cpc/export_site.py.

    sites.json                      site list + metadata
    products.json                   product metadata (title, source, notes, freq, independence)
    summary.json                    medians of metrics across sites (by tier / network / region)
    scales.json                     integer scale per variable
    site/<id>/daily.parquet         daily LST series: obs + every sub-daily/daily product (bilinear)
    site/<id>/monthly.parquet       monthly means: obs + every product (incl. monthly-only ACAG/GHAP-m)
    site/<id>/hourly/<YYYY>.parquet hourly pm25/pm10/o3/no2 (+ smoke) for HOURLY_YEARS
    site/<id>/metrics.json          this site's metrics (full/common/recent windows, both methods)

Columns are "<source>|<var>"; values are int32 = round(value * SCALE[var]) with
DELTA_BINARY_PACKED + ZSTD.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from . import analysis as A
from . import config, metrics as M, store
from .products import registry

OUT = config.ROOT / "site" / "public" / "data"
HOURLY_YEARS = list(range(2018, pd.Timestamp.now().year + 1))  # all years (S3 has room)
HOURLY_VARS = ["pm25", "pm10", "o3", "no2", "pm25_smoke"]
SPEC = ["so4", "no3", "nh4", "om", "bc", "dust", "ss"]
SCALE = {"pm25": 10, "pm10": 10, "pm25_frm": 10, "pm25_smoke": 10, "o3": 10, "o3_mda8": 10, "no2": 10,
         "pm25_raw": 10, **{f"spec_{s}": 100 for s in SPEC}}
OBS_NET = {"AQS": "AQS", "Embassy": "Embassy", "SPARTAN": "SPARTAN", "SensorCommunity": "SensorCommunity",
           "OpenAQ": "OpenAQ", "OpenAQ-LC": "OpenAQ-LC"}


def safe_id(site_id: str) -> str:
    return site_id.replace(":", "_")


def _write_parquet(df: pd.DataFrame, path: Path, index_name: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    df = df[[c for c in df.columns if c.split("|")[1] in SCALE]].dropna(axis=1, how="all").dropna(how="all")
    if df.empty:
        return False
    cols = {index_name: pa.array(df.index.values.astype("int32"))}
    for c in df.columns:
        v = df[c].to_numpy(dtype="f8") * SCALE[c.split("|")[1]]
        ok = np.isfinite(v)
        cols[c] = pa.array(np.where(ok, np.round(v), 0).astype("int32"), mask=~ok)
    t = pa.table(cols)
    pq.write_table(t, path, compression="zstd", compression_level=9, use_dictionary=False,
                   column_encoding={c: "DELTA_BINARY_PACKED" for c in t.column_names})
    return True


def site_frames(site: pd.Series, products: list[str], root=None):
    """(daily, monthly, hourly) DataFrames with '<source>|<var>' columns."""
    off = A.site_offset(site)
    d_cols, m_cols, h_cols = {}, {}, {}
    if site.tier != 4:
        obs = M.site_obs(site, root)
        net = OBS_NET.get(site.network, site.network)
        if obs["daily"] is not None:
            for c in obs["daily"]:
                d_cols[f"{net}|{c}"] = obs["daily"][c]
            mo = A.monthly(obs["daily"])
            for c in mo:
                m_cols[f"{net}|{c}"] = mo[c]
        if obs["frm"] is not None:
            d_cols["AQS-FRM|pm25_frm"] = obs["frm"]["pm25_frm"]
        if obs["species"] is not None:
            for c in obs["species"]:
                d_cols[f"{site.network if site.network != 'AQS' else 'CSN'}|spec_{c}"] = obs["species"][c]
        if obs["hourly"] is not None:
            for c in HOURLY_VARS + ["pm25_raw"]:
                if c in obs["hourly"]:
                    h_cols[f"{net}|{c}"] = obs["hourly"][c]
    for name in products:
        df = A.product_series(name, site.site_id, root, "bilinear")
        if df is None or df.empty:
            continue
        scales, _ = M._product_scales(df, off)
        sd = dict(scales)
        spp = M.product_species(df, name)
        if "hourly" in sd:
            for c in HOURLY_VARS:
                if c in df:
                    h_cols[f"{name}|{c}"] = df[c]
        if "daily" in sd:
            dd = sd["daily"]
            if not spp.empty:
                sp_d = A.daily(spp, off, 1.0 if df.attrs["freq"] == "1h" else 3.0) if df.attrs["freq"] in ("1h", "3h") else spp
                for c in sp_d:
                    dd[f"spec_{c}"] = sp_d[c]
            for c in dd:
                if c in SCALE:
                    d_cols[f"{name}|{c}"] = dd[c]
            mo = A.monthly(dd)
        else:
            mo = sd["monthly"].copy()
            for c in spp:
                mo[f"spec_{c}"] = spp[c]
        for c in mo:
            if c in SCALE:
                m_cols[f"{name}|{c}"] = mo[c]
    return pd.DataFrame(d_cols).sort_index(), pd.DataFrame(m_cols).sort_index(), pd.DataFrame(h_cols).sort_index()


DEPENDENCE = {
    "merra2_cnn": "trained on OpenAQ reference monitors (incl. AQS/AirNow, embassies)",
    "ghap": "trained on ~9,500 monitors (OpenAQ, EPA, EEA, CNEMC)", "ghap_m": "trained on ~9,500 monitors (OpenAQ, EPA, EEA, CNEMC)",
    "acag": "calibrated to ground monitors (global); NA composition uses speciation networks",
    "naqfc_bc": "bias-corrected against AirNow", "haqes": "ensemble incl. AirNow-corrected NAQFC",
}


def export(sites: pd.DataFrame, metrics: pd.DataFrame, root=None, log=print):
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    pmeta = {}
    for name in registry.names():
        p = registry.get(name)
        try:
            sess = store.readonly("products", name, root)
            vmeta = store.group_attrs(sess, store.group_path("products", name, p.freq)).get("variables", {})
        except Exception:
            continue
        pmeta[name] = {"title": p.title, "freq": p.freq, "source": p.source, "notes": p.notes, "variables": vmeta,
                       "dependence": DEPENDENCE.get(name, "no surface PM/O3/NO2 observations used")}
    (OUT / "products.json").write_text(json.dumps(pmeta, indent=1, default=str))
    (OUT / "scales.json").write_text(json.dumps(SCALE))
    epoch = pd.Timestamp("1970-01-01")
    site_rows = []
    keep = ["product", "var", "scale", "window", "method", "n", "mean_obs", "mean_prod", "bias", "nmb", "rmse", "r",
            "kge", "csi_35", "csi_15", "csi_70", "aqi_agree", "reference_site"]
    for k, (_, s) in enumerate(sites.iterrows()):
        sid = safe_id(s.site_id)
        d, m, h = site_frames(s, list(pmeta), root)
        if d.empty and m.empty:
            continue
        d.index = (pd.DatetimeIndex(d.index) - epoch).days
        m.index = (pd.DatetimeIndex(m.index) - epoch).days
        has_d = _write_parquet(d, OUT / "site" / sid / "daily.parquet", "day")
        has_m = _write_parquet(m, OUT / "site" / sid / "monthly.parquet", "day")
        years = []
        if not h.empty:
            for y in HOURLY_YEARS:
                hy = h[h.index.year == y]
                if hy.dropna(how="all").empty:
                    continue
                hy.index = ((hy.index - epoch) // pd.Timedelta(hours=1)).astype("int64")
                if _write_parquet(hy, OUT / "site" / sid / "hourly" / f"{y}.parquet", "hour"):
                    years.append(y)
        mm = metrics[metrics.site == s.site_id] if len(metrics) else metrics
        cols = [c for c in keep if c in mm]
        (OUT / "site" / sid / "metrics.json").write_text(mm[cols].round(3).to_json(orient="records"))
        site_rows.append({"site_id": s.site_id, "id": sid, "network": s.network, "tier": int(s.tier), "name": s["name"],
                          "lat": round(float(s.lat), 4), "lon": round(float(s.lon), 4), "region": s.region,
                          "setting": s.setting if isinstance(s.setting, str) else "",
                          "params": s.params if isinstance(s.params, str) else "",
                          "note": s.note if isinstance(s.note, str) else "",
                          "daily": has_d, "monthly": has_m, "hourly_years": years})
        if k % 100 == 0:
            log(f"  [{k + 1}/{len(sites)}] {s.site_id}: daily {d.shape}, monthly {m.shape}, hourly {years}")
    (OUT / "sites.json").write_text(json.dumps(site_rows, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    if len(metrics):
        summ = summary(metrics)
        (OUT / "summary.json").write_text(summ.to_json(orient="records"))
    total = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    log(f"site data: {total / 1e6:.1f} MB, {sum(1 for _ in OUT.rglob('*'))} files in {OUT}")
    return total


def summary(metrics: pd.DataFrame) -> pd.DataFrame:
    """Medians across sites, grouped by tier / network / region."""
    vals = [c for c in ("bias", "nmb", "rmse", "r", "kge", "csi_35", "csi_15", "csi_70", "aqi_agree", "mean_obs",
                        "mean_prod") if c in metrics]
    m = metrics[metrics.method != "point"]
    parts = []
    for grp, col in (("tier", "tier"), ("network", "network"), ("region", "region")):
        keys = [col, "product", "var", "scale", "window", "method"]
        g = m.groupby(keys)
        s = g[vals].median().round(3)
        s["n_sites"] = g.size()
        s = s.reset_index().rename(columns={col: "group_value"})
        s["group_value"] = s["group_value"].astype(str)
        s.insert(0, "group", grp)
        parts.append(s)
    return pd.concat(parts, ignore_index=True)
