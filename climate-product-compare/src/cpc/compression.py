"""Compression study: zstd vs lossless pcodec vs quantized pcodec, and the effect of
quantization on metrics (PLAN.md, "Compression study").

Re-extracts a few products at a few pilot sites into a lossless store root, measures encoded
bytes per value for each codec on identical arrays, then recomputes metrics from both stores.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
from numcodecs import Zstd

from . import config, store
from .products import registry

PRODUCTS = ["era5", "era5land", "merra2", "hrrr", "gridmet", "chirps3", "imerg_late", "nldas2_forcing", "nldas2_noah"]
SITES = ["TX_Monahans_6_ENE", "WA_Darrington_21_NNE", "ME_Limestone_4_NNW"]
LOSSLESS_ROOT = f"file://{config.DATA / 'store_lossless'}"


def extract_lossless(sites: pd.DataFrame, log=print):
    from . import extract

    os.environ["CPC_LOSSLESS"] = "1"
    try:
        for p in PRODUCTS:
            extract.run(p, sites, store_url=LOSSLESS_ROOT, log=log)
    finally:
        os.environ.pop("CPC_LOSSLESS", None)


def _bytes(arr: np.ndarray, how: str, kind: str) -> int:
    a = np.ascontiguousarray(arr, dtype="f4")
    if how == "zstd":
        return len(Zstd(level=5).encode(a))
    if how == "pcodec":
        return _pco(a)
    if how == "pcodec_q":
        os.environ.pop("CPC_LOSSLESS", None)
        return _pco(store.quantize(a, kind))
    raise ValueError(how)


def _pco(a):
    from zarr.codecs.numcodecs import PCodec  # same codec as the store uses

    import numcodecs

    c = numcodecs.get_codec({"id": "pcodec", "level": 8})
    _ = PCodec
    return len(c.encode(np.ascontiguousarray(a, dtype="f4")))


def sizes(site_ids: list[str]) -> pd.DataFrame:
    rows = []
    for p in PRODUCTS:
        prod = registry.get(p)
        sess = store.readonly("products", p, LOSSLESS_ROOT)
        ds = store.read_group(sess, store.group_path("products", p, prod.freq), sites=site_ids)
        for v, meta in ds.attrs.get("variables", {}).items():
            if v not in ds:
                continue
            kind = meta.get("kind")
            for k in range(ds.sizes["site"]):
                a = ds[v].values[k]  # (4, time) = one store chunk's worth
                n = a.size
                rows.append({"product": p, "var": v, "kind": kind, "site": ds.site.values[k], "n": n,
                             **{h: _bytes(a, h, kind) for h in ("zstd", "pcodec", "pcodec_q")}})
    return pd.DataFrame(rows)


def run(log=print):
    from . import metrics, sites as sitesmod

    us = sitesmod.load("uscrn")
    sel = us[us.file_stub.isin(SITES)].reset_index(drop=True)
    extract_lossless(sel, log)
    sz = sizes(list(sel.site_id))
    out = config.RESULTS / "pilot"
    out.mkdir(parents=True, exist_ok=True)
    by = sz.groupby("product")[["n", "zstd", "pcodec", "pcodec_q"]].sum()
    for h in ("zstd", "pcodec", "pcodec_q"):
        by[f"{h}_B_per_value"] = by[h] / by.n
    by["ratio_q_vs_lossless"] = by.pcodec_q / by.pcodec
    by.round(4).to_csv(out / "compression_sizes.csv")
    bk = sz.groupby("kind")[["n", "zstd", "pcodec", "pcodec_q"]].sum()
    for h in ("zstd", "pcodec", "pcodec_q"):
        bk[f"{h}_B_per_value"] = bk[h] / bk.n
    bk.round(4).to_csv(out / "compression_sizes_by_kind.csv")
    # metric differences: quantized (default root) vs lossless root
    rows_q, rows_l = [], []
    for _, s in sel.iterrows():
        rows_q += metrics.site_metrics(s, PRODUCTS)
        rows_l += metrics.site_metrics(s, PRODUCTS, root=LOSSLESS_ROOT)
    keys = ["site", "product", "var", "obs_var", "scale", "window", "method"]
    # compare on the common window only: the two stores may end at slightly different times
    q, l = pd.DataFrame(rows_q), pd.DataFrame(rows_l)
    q, l = q[q.window == "common"].set_index(keys), l[l.window == "common"].set_index(keys)
    common = q.index.intersection(l.index)
    cols = [c for c in ("bias", "rmse", "r", "kge", "anom_r", "ratio", "csi_1.0") if c in q]
    d = (q.loc[common, cols] - l.loc[common, cols]).abs()
    summ = d.groupby(level=["product", "scale"]).max()
    summ.round(6).to_csv(out / "compression_metric_maxabsdiff.csv")
    log(by.round(3).to_string())
    log(summ.round(5).to_string())
    return by, summ
