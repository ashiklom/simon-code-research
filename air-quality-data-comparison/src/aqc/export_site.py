"""Export per-site data for the static website (site/public/data/...).

Adapted from climate-product-compare/src/cpc/export_site.py.

    sites.json                      site list + metadata
    products.json                   product metadata (title, source, notes, freq, independence)
    summary.json                    medians of metrics across sites (by tier / network / region)
    scales.json                     integer scale per variable
    site/<id>.parquet               ONE file per site (few, larger S3 objects), rows by `scale`:
        0 daily LST series (t = days since 1970): obs + every sub-daily/daily product (bilinear)
        2 monthly means (t = days since 1970 of the month start), incl. monthly-only ACAG/GHAP-m
        1 hourly pm25/pm10/o3/no2 (+ smoke) for HOURLY_YEARS (t = hours since 1970)
        footer metadata "metrics_gz": this site's metrics (all windows, both methods), JSON,
        gzipped + base64

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


SCALE_CODE = {"daily": 0, "hourly": 1, "monthly": 2}


def _table(df: pd.DataFrame, code: int) -> pa.Table | None:
    """int32-scaled '<source>|<var>' columns plus t (int64) and scale (int8); None if empty."""
    df = df[[c for c in df.columns if c.split("|")[1] in SCALE]].dropna(axis=1, how="all").dropna(how="all")
    if df.empty:
        return None
    cols = {"t": pa.array(np.asarray(df.index.values).astype("int64")),
            "scale": pa.array(np.full(len(df), code, dtype="int8"))}
    for c in df.columns:
        v = df[c].to_numpy(dtype="f8") * SCALE[c.split("|")[1]]
        ok = np.isfinite(v)
        cols[c] = pa.array(np.where(ok, np.round(v), 0).astype("int32"), mask=~ok)
    return pa.table(cols)


def _gz_b64(obj) -> str:
    """Compact JSON, gzipped and base64-encoded (Parquet footer metadata is not compressed)."""
    import base64
    import gzip

    return base64.b64encode(gzip.compress(json.dumps(obj, separators=(",", ":"), default=str).encode(), 9)).decode()


def _write_site(path: Path, tables: list, meta: dict) -> bool:
    tables = [t for t in tables if t is not None]
    if not tables:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    t = pa.concat_tables(tables, promote_options="default")
    t = t.replace_schema_metadata({k: (_gz_b64(v) if k.endswith("_gz") else str(v)) for k, v in meta.items()})
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


def _export_one(args) -> dict | None:
    """Write one site's parquet; return its sites.json row (None when it has no data)."""
    site, products, root, mrec = args
    s = pd.Series(site)
    epoch = pd.Timestamp("1970-01-01")
    sid = safe_id(s.site_id)
    d, m, h = site_frames(s, products, root)
    if d.empty and m.empty:
        return None
    d.index = (pd.DatetimeIndex(d.index) - epoch).days
    m.index = (pd.DatetimeIndex(m.index) - epoch).days
    td, tm = _table(d, SCALE_CODE["daily"]), _table(m, SCALE_CODE["monthly"])
    tables, years = [td, tm], []
    if not h.empty:
        for y in HOURLY_YEARS:
            hy = h[h.index.year == y]
            if hy.dropna(how="all").empty:
                continue
            hy.index = ((hy.index - epoch) // pd.Timedelta(hours=1)).astype("int64")
            th = _table(hy, SCALE_CODE["hourly"])
            if th is not None:
                tables.append(th)
                years.append(y)
    _write_site(OUT / "site" / f"{sid}.parquet", tables, {"metrics_gz": mrec, "site_id": s.site_id})
    return {"site_id": s.site_id, "id": sid, "network": s.network, "tier": int(s.tier), "name": s["name"],
            "lat": round(float(s.lat), 4), "lon": round(float(s.lon), 4), "region": s.region,
            "setting": s.setting if isinstance(s.setting, str) else "",
            "params": s.params if isinstance(s.params, str) else "",
            "note": s.note if isinstance(s.note, str) else "",
            "daily": td is not None, "monthly": tm is not None, "hourly_years": years}


def export(sites: pd.DataFrame, metrics: pd.DataFrame, root=None, log=print, workers: int = 1):
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
    keep = ["product", "var", "scale", "window", "method", "n", "mean_obs", "mean_prod", "bias", "nmb", "rmse", "r",
            "kge", "csi_35", "csi_15", "csi_70", "aqi_agree", "reference_site"]
    cols = [c for c in keep if c in metrics]
    by_site = {k: json.loads(g[cols].round(3).to_json(orient="records"))
               for k, g in metrics.groupby("site")} if len(metrics) else {}
    jobs = [(dict(s), list(pmeta), root, by_site.get(s.site_id, [])) for _, s in sites.iterrows()]
    site_rows = []
    import multiprocessing as mp
    from concurrent.futures import ProcessPoolExecutor

    # sites are independent and each one is latency-bound S3 reads: a process pool (spawn: icechunk's
    # runtime threads do not survive fork) keeps several in flight
    with ProcessPoolExecutor(workers, mp_context=mp.get_context("spawn")) as ex:
        for k, row in enumerate(ex.map(_export_one, jobs, chunksize=2)):
            if row is not None:
                site_rows.append(row)
            if k % 100 == 0:
                log(f"  [{k + 1}/{len(sites)}] {jobs[k][0]['site_id']}: "
                    f"{'hourly ' + str(row['hourly_years']) if row else 'no data'}")
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
