"""Export per-site data for the static website (site/public/data/...).

    data/sites.json                  site list + metadata + headline metrics (for the map)
    data/products.json               product metadata (title, source, notes, variables)
    data/summary.json                cross-site medians of metrics (heatmaps, rankings)
    data/site/<id>.parquet           ONE file per site (few, larger S3 objects):
        rows with scale=0: daily series, t = days since 1970-01-01 (obs UTC day + every product)
        rows with scale=1: hourly series for selected variables (recent years), t = hours since 1970
        key-value metadata "metrics_gz": this site's metrics (bilinear and nearest), JSON records,
        gzipped + base64

Parquet columns are "<source>|<var>" (source = network name for obs, product name otherwise),
stored as nullable int32 = round(value * SCALE[var]) with DELTA_BINARY_PACKED + ZSTD (about 3x
smaller than float32). data/scales.json lists the scale per variable for the browser.
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
from . import config, store
from .products import registry

OUT = config.ROOT / "site" / "public" / "data"
HOURLY_VARS = ["tair", "tdew", "rh", "pr", "sw", "tsurf", "wind", "swe", "snowd"]
# variables shipped to the site, with the integer scale used to store them
SCALE = {"tair": 100, "tmax": 100, "tmin": 100, "tdew": 100, "tsurf": 100, "tsoil1": 100, "ts05": 100, "ts10": 100,
         "pr": 100, "sw": 10, "rh": 10, "vpd": 1000, "wind": 100, "soilm1": 10000, "soilm_top": 10000, "sm05": 10000,
         "sm10": 10000, "swe": 10, "snowd": 1000, "ps": 0.1}


def safe_id(site_id: str) -> str:
    return site_id.replace(":", "_")


SCALE_CODE = {"daily": 0, "hourly": 1}


def _table(df: pd.DataFrame, code: int) -> pa.Table:
    """int32-scaled '<source>|<var>' columns plus t (int64) and scale (int8)."""
    df = df[[c for c in df.columns if c.split("|")[1] in SCALE]].dropna(axis=1, how="all")
    cols = {"t": pa.array(np.asarray(df.index.values).astype("int64")),
            "scale": pa.array(np.full(len(df), code, dtype="int8"))}
    for c in df.columns:
        v = df[c].to_numpy(dtype="f8") * SCALE[c.split("|")[1]]
        ok = np.isfinite(v)
        cols[c] = pa.array(np.where(ok, np.round(v), 0).astype("int32"), mask=~ok)
    return pa.table(cols)


def _gz_b64(obj) -> str:
    """Compact JSON, gzipped and base64-encoded: Parquet footer metadata is stored uncompressed
    (metrics are ~1 MB of JSON per site); the browser inflates it with DecompressionStream."""
    import base64
    import gzip

    raw = json.dumps(obj, separators=(",", ":"), default=str).encode()
    return base64.b64encode(gzip.compress(raw, 9)).decode()


def _write_site(path: Path, tables: list[pa.Table], meta: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    t = pa.concat_tables(tables, promote_options="default")
    t = t.replace_schema_metadata({k: (_gz_b64(v) if k.endswith("_gz") else str(v)) for k, v in meta.items()})
    pq.write_table(t, path, compression="zstd", compression_level=9, use_dictionary=False,
                   column_encoding={c: "DELTA_BINARY_PACKED" for c in t.column_names})


def _round(df: pd.DataFrame, meta: dict) -> pd.DataFrame:
    out = df.copy()
    for c in out:
        q = store.QUANTA.get((meta.get(c) or {}).get("kind", ""), None)
        if q:
            out[c] = np.round(out[c] / q) * q
    return out


def site_frames(site: pd.Series, products: list[str], root=None):
    """(daily DataFrame, hourly DataFrame) with '<source>|<var>' columns."""
    daily_cols, hourly_cols = {}, {}
    net = site.network
    if net != "REMOTE":
        obs = A.obs_series(net, site.site_id, root)
        if obs is not None and not obs.empty:
            obs = A.add_station_humidity(obs, float(site.elev_m) if pd.notna(site.elev_m) else 0.0)
            od = A.station_daily(obs, 24)
            od = _round(od, obs.attrs.get("variables", {}))
            for c in od:
                daily_cols[f"{net}|{c}"] = od[c]
            for c in HOURLY_VARS:
                if c in obs:
                    hourly_cols[f"{net}|{c}"] = obs[c]
    for name in products:
        df = A.product_series(name, site.site_id, root, "bilinear")
        if df is None or df.empty:
            continue
        meta = df.attrs["variables"]
        if df.attrs["freq"] in ("1h", "30min"):
            if df.attrs["freq"] == "30min":
                df = A.to_hourly(df)
            for c in HOURLY_VARS:
                if c in df:
                    hourly_cols[f"{name}|{c}"] = _round(df[[c]], meta)[c]
            d = df.copy()
            if "tair" in d and "tmax" not in d:
                d["tmax"], d["tmin"] = d["tair"], d["tair"]
            pdaily = _round(A.daily(d, 24, 24), {**meta, "tmax": meta.get("tair"), "tmin": meta.get("tair")})
        else:
            pdaily = _round(df, meta)
        for c in pdaily:
            if c in SCALE:
                daily_cols[f"{name}|{c}"] = pdaily[c]
    daily = pd.DataFrame(daily_cols).sort_index()
    hourly = pd.DataFrame(hourly_cols).sort_index()
    return daily, hourly


def _export_site(args):
    """Write site/<id>.parquet for one site; returns (site, sites.json row or None, log message)."""
    s, products, root, hourly_years, m, out = args
    sid = safe_id(s.site_id)
    d, h = site_frames(s, products, root)
    if d.empty:
        return s, None, "no data"
    d.index = (d.index - pd.Timestamp("1970-01-01")).days
    tables = [_table(d, SCALE_CODE["daily"])]
    years = []
    if not h.empty:
        last = h.index.max().year
        for y in range(last - hourly_years + 1, last + 1):
            hy = h[h.index.year == y]
            if hy.dropna(how="all").empty:
                continue
            hy.index = ((hy.index - pd.Timestamp("1970-01-01")) // pd.Timedelta(hours=1)).astype("int64")
            tables.append(_table(hy, SCALE_CODE["hourly"]))
            years.append(y)
    mrec = json.loads(m.drop(columns="site").round(4).to_json(orient="records")) if m is not None and len(m) else []
    _write_site(out / "site" / f"{sid}.parquet", tables, {"metrics_gz": mrec, "site_id": s.site_id})
    srcs = sorted({c.split("|")[0] for c in d.columns})
    row = {**{c: (None if pd.isna(s.get(c)) else s.get(c)) for c in ("site_id", "network", "tier", "name", "state", "lat", "lon", "elev_m")},
           "id": sid, "sources": srcs, "hourly_years": years,
           "d_station_km": None if pd.isna(s.get("d_station_km")) else s.get("d_station_km"),
           "stratum": s.get("stratum") if isinstance(s.get("stratum"), str) else None,
           "independence": s.get("independence") if isinstance(s.get("independence"), str) else None}
    return s, row, f"daily {d.shape}, hourly years {years}"


def export(sites: pd.DataFrame, metrics: pd.DataFrame, hourly_years: int = 2, root=None, log=print, workers: int = 4):
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    products = [p for p in registry.names()]
    # products.json
    pmeta = {}
    for name in products:
        p = registry.get(name)
        try:
            sess = store.readonly("products", name, root)
            vmeta = store.group_attrs(sess, store.group_path("products", name, p.freq)).get("variables", {})
        except Exception:
            continue
        pmeta[name] = {"title": p.title, "freq": p.freq, "source": p.source, "notes": p.notes, "variables": vmeta}
    (OUT / "products.json").write_text(json.dumps(pmeta, indent=1, default=str))
    (OUT / "scales.json").write_text(json.dumps(SCALE))
    # per site (network-bound reads, so several processes)
    from .parallel import process_map

    mcols = [c for c in ("site", "product", "var", "obs_var", "kind", "scale", "window", "method", "n", "bias", "mae", "rmse",
                         "ubrmse", "r", "kge", "anom_r", "ratio", "csi_1.0", "pod_1.0", "far_1.0", "mean_obs", "mean_prod")
             if c in metrics]
    by_site = dict(tuple(metrics[mcols].groupby("site"))) if len(metrics) else {}
    items = [(s, list(pmeta), root, hourly_years, by_site.get(s.site_id), OUT) for _, s in sites.iterrows()]
    site_rows = []
    for k, (s, row, msg) in enumerate(process_map(_export_site, items, workers)):
        if row is not None:
            site_rows.append(row)
        log(f"  [{k + 1}/{len(sites)}] {s.site_id}: {msg}")
    (OUT / "sites.json").write_text(json.dumps(site_rows, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
    # summary.json: medians across sites
    if len(metrics):
        keys = ["network", "product", "var", "obs_var", "scale", "window", "method"]
        vals = [c for c in ("bias", "mae", "rmse", "ubrmse", "r", "kge", "anom_r", "ratio", "csi_1.0") if c in metrics]
        summ = metrics.groupby(keys)[vals].median().round(4)
        summ["n_sites"] = metrics.groupby(keys).size()
        (OUT / "summary.json").write_text(summ.reset_index().to_json(orient="records"))
    total = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    log(f"site data: {total / 1e6:.1f} MB in {OUT}")
    return total
