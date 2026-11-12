"""Generic station ingest: network module -> Icechunk repo obs-<NETWORK> (group obs/<NETWORK>/1h)."""

from __future__ import annotations

import importlib
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from .. import config, store
from . import NETWORKS


def module(network: str):
    return importlib.import_module(f"cpc.obs.{NETWORKS[network]}")


def run(network: str, sites: pd.DataFrame, *, root=None, force=False, update=False, workers=4, batch=8, log=print):
    """Ingest a network. update=True re-fetches each known station from the year of its last
    update onward (incremental refresh) and still ingests stations not yet in the store."""
    mod = module(network)
    sites = sites[sites.network == network]
    if sites.empty:
        return
    need = getattr(mod, "token", None) or getattr(mod, "creds", None)
    if need is not None and not need():
        log(f"[{network}] credentials not set; skipping {len(sites)} sites (see README, Requirements)")
        return
    specs = {k: store.VarSpec(k, *v) for k, v in mod.VARS.items()}
    years = list(range(config.START.year, pd.Timestamp.now().year + 1))
    repo = store.open_repo(store.repo_name("obs", network), root)
    path = store.group_path("obs", network, "1h")
    s = repo.writable_session("main")
    origin = pd.Timestamp(f"{years[0]}-01-01 01:00")
    w = store.GroupWriter(s, path, "1h", has_px=False, attrs={"network": network}, t_origin=origin)
    site_end = dict(w.g.attrs.get("site_end", {}))
    done = set(site_end)
    todo = [r for r in sites.itertuples() if force or update or r.site_id not in done]
    if update and site_end:
        first = min(pd.Timestamp(v).year for k, v in site_end.items() if k in set(sites.site_id)) if done & set(sites.site_id) else years[0]
        years_upd = list(range(first, years[-1] + 1))
    else:
        years_upd = years
    tax = pd.date_range(f"{min(years)}-01-01 01:00", f"{max(years) + 1}-01-01 00:00", freq="h")
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        with ThreadPoolExecutor(workers) as ex:
            res = list(ex.map(lambda r: (r, _safe(mod.fetch_site, r, years_upd if r.site_id in done else years, log)), chunk))
        s = repo.writable_session("main")
        w = store.GroupWriter(s, path, "1h", has_px=False, t_origin=origin)
        se = dict(w.g.attrs.get("site_end", {}))
        for r, df in res:
            if df is None:  # failed (e.g. missing credentials): leave unmarked so a later run retries
                continue
            if df.empty:
                log(f"  {r.site_id}: no data")
                se[r.site_id] = pd.Timestamp.now().floor("h").isoformat()
                continue
            df = df[~df.index.duplicated()].sort_index()
            df = df.reindex(tax[(tax >= df.index[0]) & (tax <= df.index[-1])])
            data = {k: df[k].to_numpy(dtype="f8")[None, :] for k in mod.VARS if k in df}
            w.write([r.site_id], df.index, data, specs)
            se[r.site_id] = pd.Timestamp.now().floor("h").isoformat()
            n = {k: int(np.isfinite(v).sum()) for k, v in data.items()}
            log(f"  {r.site_id}: {df.index[0]:%Y-%m-%d}..{df.index[-1]:%Y-%m-%d} {n}")
        w.g.attrs["site_end"] = se
        st = dict(w.g.attrs.get("stations", {}))
        for r, _ in res:
            st[r.site_id] = {"name": r.name, "lat": float(r.lat), "lon": float(r.lon),
                             "elev_m": None if pd.isna(r.elev_m) else float(r.elev_m)}
        w.g.attrs["stations"] = st
        if s.has_uncommitted_changes:
            s.commit(f"obs {network}: {len(chunk)} sites")
        log(f"[{network}] committed {i + len(chunk)}/{len(todo)}")


def _safe(fn, r, years, log):
    try:
        return fn(r, years)
    except Exception as e:  # one bad station should not stop the network
        log(f"  {r.site_id}: FAILED {e!r}")
        return None
