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
    from .obs import ingest

    sites = sitesmod.load(a.sites)
    for net in (a.network or sorted(sites.network.unique())):
        ingest.run(net, sites, root=a.store, force=a.force)


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
    if not a.products and not a.dry_run:
        from .obs import ingest

        for net in sorted(sites.network.unique()):
            if net != "REMOTE":
                ingest.run(net, sites, root=a.store, update=True)
    for name in names:
        try:
            out.append(extract.run(name, sites, store_url=a.store, dry_run=a.dry_run, refresh_revisions=a.refresh_revisions))
        except Exception as e:  # keep going: one broken source should not block the others
            print(f"[{name}] FAILED: {e!r}", file=sys.stderr)
            out.append({"product": name, "error": repr(e)})
    print(json.dumps(out, indent=1, default=str))


def _site_rows(args):
    fn, site, products = args
    from . import diagnostics, metrics

    return {"metrics": metrics.site_metrics, "lags": diagnostics.lag_table}[fn](site, products)


def _run_sites(fn: str, a, out_name: str):
    from .parallel import process_map
    from .products import registry

    sites = sitesmod.load(a.sites)
    products = a.products or registry.names()
    rows = []
    for k, r in enumerate(process_map(_site_rows, [(fn, s, products) for _, s in sites.iterrows()], a.workers)):
        rows.extend(r)
        print(f"  {k + 1}/{len(sites)} sites", flush=True)
    df = pd.DataFrame(rows)
    out = config.DATA / "results" / f"{out_name}_{a.sites}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"wrote {out} ({len(df)} rows)")
    return df


def cmd_metrics(a):
    _run_sites("metrics", a, "metrics")


def cmd_lags(a):
    df = _run_sites("lags", a, "lags")
    keys = ["product", "var", "scale"]
    best = (df.dropna(subset=["r"]).groupby(keys + [c for c in ("lag_h", "day_end_offset_h") if c in df], dropna=False)["r"].median()
            .reset_index())
    out = config.RESULTS / "pilot" / f"lagcheck_{a.sites}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    best.to_csv(out, index=False, float_format="%.4f")
    from .diagnostics import overrides_from

    ov = overrides_from(df)
    ov.to_csv(config.RESULTS / f"day_window_overrides_{a.sites}.csv", index=False, float_format="%.4f")
    print(ov.to_string(index=False))
    print(f"wrote {out}")


def cmd_sitedata(a):
    from . import export_site

    sites = sitesmod.load(a.sites)
    mfile = config.DATA / "results" / f"metrics_{a.metrics}.parquet"
    metrics = pd.read_parquet(mfile) if mfile.exists() else pd.DataFrame()
    export_site.export(sites, metrics, hourly_years=a.hourly_years)


def cmd_status(a):
    """Per repo: sites with data, min/max per-site end time, on-disk size (local roots)."""
    from .products import registry

    rows = []
    for name in store.list_repos(a.store):
        kind, _, n = name.partition("-")
        try:
            sess = store.open_repo(name, a.store, create=False).readonly_session("main")
            freq = registry.get(n).freq if kind == "products" else "1h"
            at = store.group_attrs(sess, store.group_path(kind, n, freq))
        except Exception as e:
            rows.append({"repo": name, "error": repr(e)[:60]})
            continue
        se = pd.to_datetime(pd.Series(at.get("site_end", {})), errors="coerce")
        rows.append({"repo": name, "sites": len(at.get("sites", [])), "done": len(se),
                     "end_min": se.min(), "end_max": se.max()})
    print(pd.DataFrame(rows).to_string(index=False))


def cmd_figures(a):
    from . import figures

    for f in figures.run(a.metrics):
        print(f)


def cmd_report(a):
    from . import report

    print(report.write_pilot_report())


def cmd_compression(a):
    from . import compression

    compression.run()


def cmd_store_copy(a):
    store.copy_store(a.src, a.dst)


def main(argv=None):
    p = argparse.ArgumentParser(prog="cpc")
    p.add_argument("--store", default=None, help="store URL (file://, s3://, https://); default $CPC_STORE or local")
    sub = p.add_subparsers(required=True)

    s = sub.add_parser("sites", help="build USCRN site table (results/sites/uscrn.csv)")
    s.set_defaults(fn=cmd_sites)

    s = sub.add_parser("obs", help="ingest station observations")
    s.add_argument("--sites", default="uscrn")
    s.add_argument("--network", action="append", help="limit to these networks")
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

    for name, fn in (("metrics", cmd_metrics), ("lags", cmd_lags)):
        s = sub.add_parser(name)
        s.add_argument("products", nargs="*")
        s.add_argument("--sites", default="pilot")
        s.add_argument("--workers", type=int, default=4)
        s.set_defaults(fn=fn)

    s = sub.add_parser("sitedata", help="export website data to site/public/data")
    s.add_argument("--sites", default="all")
    s.add_argument("--metrics", default="all")
    s.add_argument("--hourly-years", type=int, default=2)
    s.set_defaults(fn=cmd_sitedata)

    s = sub.add_parser("status", help="extraction progress per repo")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("figures", help="README figures (results/figures)")
    s.add_argument("--metrics", default="all")
    s.set_defaults(fn=cmd_figures)

    s = sub.add_parser("report", help="write results/pilot/pilot_report.md")
    s.set_defaults(fn=cmd_report)

    s = sub.add_parser("compression", help="compression study on pilot sites")
    s.set_defaults(fn=cmd_compression)

    s = sub.add_parser("store-copy", help="copy the store between backends")
    s.add_argument("src")
    s.add_argument("dst")
    s.set_defaults(fn=cmd_store_copy)

    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
