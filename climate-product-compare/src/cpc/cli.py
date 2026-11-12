"""Command-line entry point (`uv run cpc ...`, wrapped by mise tasks)."""

from __future__ import annotations

import argparse
import json
import sys

import pandas as pd

from . import config, sites as sitesmod, store


def cmd_sites(a):
    df = sitesmod.build_uscrn()
    sitesmod.save(df, "uscrn")
    print(f"uscrn: {len(df)} stations ({df.pilot.sum()} pilot)")


def cmd_obs(a):
    from .obs import uscrn

    sites = sitesmod.load(a.sites)
    sites = sites[sites.network == "USCRN"]
    repo = store.open_repo(a.store)
    years = list(range(config.START.year, pd.Timestamp.now().year + 1))
    path = store.group_path("obs", "USCRN", "1h")
    s = repo.writable_session("main")
    w = store.GroupWriter(s, path, "1h", has_px=False, attrs={"network": "USCRN", "source": uscrn.BASE})
    todo = [r for r in sites.itertuples() if a.force or r.site_id not in w.g.attrs.get("site_end", {})]
    for i in range(0, len(todo), 10):
        batch = pd.DataFrame(todo[i:i + 10])
        s = repo.writable_session("main")
        w = store.GroupWriter(s, path, "1h", has_px=False)
        uscrn.ingest(w, batch, years, wind=not a.no_wind)
        se = dict(w.g.attrs.get("site_end", {}))
        for sid in batch.site_id:
            se[sid] = pd.Timestamp.now().floor("h").isoformat()
        w.g.attrs["site_end"] = se
        w.g.attrs["stations"] = {r.site_id: {"name": r.name, "lat": r.lat, "lon": r.lon, "elev_m": r.elev_m}
                                 for r in sites.itertuples()}
        s.commit(f"obs USCRN: {len(batch)} stations")
        print(f"committed {i + len(batch)}/{len(todo)}")


def cmd_extract(a):
    from . import extract

    sites = sitesmod.load(a.sites)
    if a.limit:
        sites = sites.head(a.limit)
    for name in a.products:
        extract.run(name, sites, t_end=a.t_end, store_url=a.store, dry_run=a.dry_run)


def cmd_update(a):
    from . import extract
    from .products import registry

    sites = sitesmod.load("all")
    names = a.products or registry.names()
    out = []
    for name in names:
        try:
            out.append(extract.run(name, sites, store_url=a.store, dry_run=a.dry_run, refresh_revisions=a.refresh_revisions))
        except Exception as e:  # keep going: one broken source should not block the others
            print(f"[{name}] FAILED: {e!r}", file=sys.stderr)
            out.append({"product": name, "error": repr(e)})
    print(json.dumps(out, indent=1, default=str))


def cmd_store_copy(a):
    store.copy_repo(a.src, a.dst)


def main(argv=None):
    p = argparse.ArgumentParser(prog="cpc")
    p.add_argument("--store", default=None, help="store URL (file://, s3://, https://); default $CPC_STORE or local")
    sub = p.add_subparsers(required=True)

    s = sub.add_parser("sites", help="build USCRN site table (results/sites/uscrn.csv)")
    s.set_defaults(fn=cmd_sites)

    s = sub.add_parser("obs", help="ingest station observations")
    s.add_argument("--sites", default="uscrn")
    s.add_argument("--no-wind", action="store_true")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_obs)

    s = sub.add_parser("extract", help="extract products at sites")
    s.add_argument("products", nargs="+")
    s.add_argument("--sites", default="pilot")
    s.add_argument("--limit", type=int, default=0)
    s.add_argument("--t-end", default=None)
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(fn=cmd_extract)

    s = sub.add_parser("update", help="bring every product up to its latest available time")
    s.add_argument("products", nargs="*")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--refresh-revisions", action="store_true", help="re-fetch provisional spans even if current")
    s.set_defaults(fn=cmd_update)

    s = sub.add_parser("store-copy", help="copy the store between backends")
    s.add_argument("src")
    s.add_argument("dst")
    s.set_defaults(fn=cmd_store_copy)

    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
