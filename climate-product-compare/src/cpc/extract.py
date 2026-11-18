"""Extraction / update runner: product x sites -> Icechunk group products/<name>/<freq>.

The same code path does the initial extraction and incremental updates: each site's last
extracted time is kept in the group attribute ``site_end``. A run fetches, per site,
``[max(site_end - revision_window, START), available_end]`` and skips sites already at
``available_end``. Commits happen every `commit_every` sites, so interrupted runs resume.
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd

from . import config, store
from .products import registry
from .products.base import Block, px_distance_km

# Writes are batched to match the store's shard layout (store.SITE_SHARD sites x
# store.TIME_CHUNK steps): consecutive blocks for the same sites are merged in time up to a
# time-chunk boundary, and single-site blocks with identical times are stacked up to SITE_SHARD
# sites. Whole-shard writes need no read-back; on S3 a partial write re-reads and re-encodes the
# shard, and many small writes were the bottleneck (PRISM: ~5 min per month of data).


def _batched(blocks, freq: str, origin: pd.Timestamp, axis0: pd.Timestamp | None = None,
             tchunk: int | None = None):
    """axis0: first stamp of the store's existing time axis (None: derived from the first block,
    the way GroupWriter lays out a new axis). tchunk: the arrays' shard time length."""
    dt = pd.Timedelta(seconds=store.FREQ_SECONDS[freq])
    tchunk = tchunk or store.TIME_CHUNK[freq]
    base = [axis0]

    def chunk_of(t):
        if base[0] is None:
            base[0] = origin + (t - origin) % dt
        return int((t - base[0]) // dt) // tchunk

    pending: list = []
    mode = None  # "time" | "site"

    def merge():
        if len(pending) == 1:
            return pending[0]
        keys = sorted(set().union(*[b.data.keys() for b in pending]))
        data = {}
        axis = -1 if mode == "time" else 0
        for k in keys:
            parts = []
            for b in pending:
                if k in b.data:
                    parts.append(b.data[k])
                else:
                    ref = next(iter(b.data.values()))
                    parts.append(np.full(ref.shape, np.nan, dtype="f4"))
            data[k] = np.concatenate(parts, axis=axis)
        if mode == "time":
            out = Block(pending[0].site_ids, pending[0].times.append([b.times for b in pending[1:]]), data)
            out.final = getattr(pending[-1], "final", True)
        else:
            out = Block([s for b in pending for s in b.site_ids], pending[0].times, data)
            out.final = all(getattr(b, "final", True) for b in pending)
        return out

    for blk in blocks:
        if pending:
            last = pending[-1]
            same_sites = blk.site_ids == last.site_ids
            same_times = len(blk.times) == len(last.times) and blk.times.equals(last.times)
            nsite = sum(len(b.site_ids) for b in pending)
            if (mode in (None, "time") and same_sites and len(blk.times)
                    and chunk_of(blk.times[-1]) == chunk_of(pending[0].times[0])
                    and getattr(last, "final", True) == getattr(blk, "final", True)):
                mode = "time"
            elif (mode in (None, "site") and same_times and not same_sites
                  and nsite + len(blk.site_ids) <= store.SITE_SHARD):
                mode = "site"
            else:
                yield merge()
                pending, mode = [], None
        pending.append(blk)
    if pending:
        yield merge()

def _fmt_bytes(n: float) -> str:
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {u}"
        n /= 1024
    return f"{n:.1f} PB"


def plan(product, sites: pd.DataFrame, writer_attrs: dict, t_end: pd.Timestamp, refresh_revisions: bool = False):
    """Return {t0: [site_ids]} of work to do."""
    site_end = writer_attrs.get("site_end", {})
    t_start = max(config.START, product.start)
    groups: dict[pd.Timestamp, list[str]] = {}
    for sid in sites.site_id:
        if sid in site_end:
            se = pd.Timestamp(site_end[sid])
            if se >= t_end and not refresh_revisions:
                continue
            t0 = max(t_start, se - product.revision_window) if product.revision_window > pd.Timedelta(0) else se
            if product.revision_window == pd.Timedelta(0):
                t0 = se + pd.Timedelta(seconds=store.FREQ_SECONDS[product.freq])
        else:
            t0 = t_start
        if t0 > t_end:
            continue
        groups.setdefault(t0, []).append(sid)
    return groups


def run(name: str, sites: pd.DataFrame, *, t_end: pd.Timestamp | None = None, store_url: str | None = None,
        dry_run: bool = False, commit_every: int = 10, refresh_revisions: bool = False, log=print) -> dict:
    product = registry.get(name)
    grid = product.grid()
    st_all = grid.stencil(sites.lat.values, sites.lon.values)
    inside = st_all.inside
    if not inside.all():
        log(f"[{name}] {(~inside).sum()} site(s) outside domain: {list(sites.site_id[~inside])[:8]}...")
    sites = sites[inside].reset_index(drop=True)
    st = grid.stencil(sites.lat.values, sites.lon.values)

    avail = product.available_end()
    t_end = min(pd.Timestamp(t_end), avail) if t_end is not None else avail
    repo = store.open_repo(store.repo_name("products", name), store_url)
    path = store.group_path("products", name, product.freq)
    session = repo.writable_session("main")
    origin = max(config.START, product.start)
    w = store.GroupWriter(session, path, product.freq, has_px=True, attrs=product.meta(), t_origin=origin)
    work = plan(product, sites, dict(w.g.attrs), t_end, refresh_revisions)
    n_sites = sum(len(v) for v in work.values())
    summary = {"product": name, "available_end": str(avail), "t_end": str(t_end), "sites_to_fetch": n_sites,
               "spans": {str(k): len(v) for k, v in work.items()}}
    if dry_run or n_sites == 0:
        log(f"[{name}] available_end={avail} -> {n_sites} site(s) to fetch" + ("" if n_sites else " (up to date)"))
        return summary

    # stencil metadata for all sites (cheap; idempotent)
    plat, plon = grid.px_latlon(st)
    elev = product.elevation(st)
    w.write_stencil(list(sites.site_id), plat, plon, st.w, px_elev=elev,
                    px_dist_km=px_distance_km(sites.lat.values, sites.lon.values, plat, plon))
    session.commit(f"{name}: stencil for {len(sites)} sites")

    specs = product.specs()
    t_wall = time.time()
    done_since_commit = 0
    n_commits = 0
    nbytes = 0
    for t0, sids in sorted(work.items()):
        sub_idx = np.array([list(sites.site_id).index(s) for s in sids])
        sub = sites.iloc[sub_idx].reset_index(drop=True)
        sub_st = grid.stencil(sub.lat.values, sub.lon.values)
        log(f"[{name}] fetching {len(sub)} site(s) {t0} .. {t_end}")
        session = repo.writable_session("main")
        w = store.GroupWriter(session, path, product.freq, has_px=True, t_origin=origin)
        finished: dict[str, str] = {}
        axis0 = pd.Timestamp(int(w.g["time"][0]), unit="s") if "time" in w.g else None
        tarr = [a for n, a in w.g.arrays() if (a.metadata.dimension_names or ())[-1:] == ("time",) and n != "time"]
        tchunk = (tarr[0].shards or tarr[0].chunks)[-1] if tarr else store.time_chunk_for(len(sites), (4,), product.freq)
        for blk in _batched(product.fetch(sub, sub_st, t0, t_end), product.freq, origin, axis0, tchunk):
            w.write(blk.site_ids, blk.times, blk.data, specs)
            nbytes += sum(a.nbytes for a in blk.data.values())
            if getattr(blk, "final", True):
                for s in blk.site_ids:
                    finished[s] = str(blk.times[-1]) if len(blk.times) else str(t_end)
                done_since_commit += len(blk.site_ids)
            if done_since_commit >= commit_every:
                _record(w, finished)
                session.commit(f"{name}: {len(finished)} site(s)")
                n_commits += 1
                if n_commits % 25 == 0:
                    try:
                        store.compact(store.repo_name("products", name), store_url)
                    except Exception:
                        pass
                session = repo.writable_session("main")
                w = store.GroupWriter(session, path, product.freq, has_px=True, t_origin=origin)
                finished, done_since_commit = {}, 0
        # sites with no data in range still count as done up to t_end
        for s in sids:
            finished.setdefault(s, str(t_end))
        _record(w, finished)
        w.set_extracted_end(t_end)
        if session.has_uncommitted_changes:
            session.commit(f"{name}: {len(finished)} site(s) to {t_end}")
    try:
        log(f"[{name}] compact: {store.compact(store.repo_name('products', name), store_url, keep_minutes=0.5)}")
    except Exception as e:  # e.g. read-only backend
        log(f"[{name}] compact skipped: {e!r}")
    dt = time.time() - t_wall
    log(f"[{name}] done: {n_sites} site(s), {_fmt_bytes(nbytes)} decoded, {dt:.0f} s")
    summary.update({"seconds": dt, "decoded_bytes": nbytes})
    return summary


def _record(w: store.GroupWriter, finished: dict[str, str]):
    se = dict(w.g.attrs.get("site_end", {}))
    for s, t in finished.items():
        se[s] = max(t, se.get(s, t))
    w.g.attrs["site_end"] = se
