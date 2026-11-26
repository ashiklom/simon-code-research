"""Command line: aqc sites | obs | extract | update | status | metrics | figures | sitedata."""

from __future__ import annotations

import argparse
import json
import sys
import time


def _log(msg: str):
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def cmd_sites(a):
    from . import sites
    df = sites.build(a.networks.split(","), log=_log)
    _log(f"total sites: {len(df)}")


def cmd_obs(a):
    from . import sites
    from .obs import ingest
    for net in a.networks.split(","):
        if net == "aqs":
            from .obs import aqs
            st = sites.load("aqs")
            for v in (a.vars.split(",") if a.vars else ("pm25", "pm10", "o3", "no2")):  # one variable and 3 years at a time keeps memory bounded
                for y0 in range(aqs.YEARS[0], aqs.YEARS[-1] + 1, 3):
                    ys = [y for y in aqs.YEARS if y0 <= y < y0 + 3]
                    ingest.write("AQS", "1h", {v: aqs.hourly(st, v, years=ys, log=_log)}, store_url=a.store, log=_log)
            frm = aqs.daily_frm(st).rename(columns={"date": "time"})
            ingest.write("AQS", "1d", {"pm25_frm": frm}, attrs={"day": "local standard day"}, store_url=a.store, log=_log)
        elif net == "embassy":
            from .obs import embassy
            ingest.write("Embassy", "1h", {"pm25": embassy.hourly(sites.load("embassy"))}, store_url=a.store, log=_log)
        elif net == "spartan":
            from .obs import spartan
            ingest.write("SPARTAN", "1h", {"pm25": spartan.hourly(sites.load("spartan"))}, store_url=a.store, log=_log)
        elif net == "airnow":
            import pandas as pd

            from .obs import airnow
            frames = airnow.hourly(sites.load("aqs"), pd.Timestamp("2025-07-01"),
                                   pd.Timestamp.now().floor("h") - pd.Timedelta(hours=2), log=_log)
            ingest.write("AirNow", "1h", frames, attrs={"status": "preliminary (unvalidated)"}, store_url=a.store, log=_log)
        elif net == "lowcost":
            from .obs import lowcost
            ingest.write("SensorCommunity", "1h", lowcost.hourly(sites.load("sensorcommunity"), log=_log),
                         attrs={"correction": "RH<=75%, kappa-Koehler kappa=0.4"}, store_url=a.store, log=_log)
        elif net == "openaq":
            from .obs import openaq
            for oaq_net in ("OpenAQ", "OpenAQ-LC"):
                st = sites.load(oaq_net)
                for i in range(0, len(st), 40):  # batches of sites keep memory bounded (~1 GB)
                    ingest.write(oaq_net, "1h", openaq.hourly(st.iloc[i:i + 40], log=_log),
                                 attrs={"source": "OpenAQ archive (openaq-data-archive), provider values as published"},
                                 store_url=a.store, log=_log)
        elif net == "speciation":
            from .obs import speciation
            data, _ = speciation.load()
            ids = set(sites.load(["improve", "csn", "aqs"]).site_id)
            data = data[data.site_id.isin(ids)]
            frames = {v: data[["site_id", "date", v]].rename(columns={"date": "time", v: "value"})
                      for v in data.columns if v.startswith("pm25_")}
            ingest.write("SPEC", "1d", frames, attrs={"day": "local standard day"}, store_url=a.store, log=_log)
        else:
            raise SystemExit(f"unknown network {net}")


def cmd_cams_store(a):
    from . import cams_store
    blocks = None
    if a.blocks:
        lo, _, hi = a.blocks.partition("-")
        blocks = list(range(int(lo), int(hi or lo) + 1))
    cams_store.build(blocks=blocks, root=a.store, workers=a.workers, group=a.group, log=_log)


def cmd_extract(a):
    from . import extract, sites
    from .products import registry
    names = registry.names() if a.products == ["all"] else a.products
    st = sites.load(a.sites)
    failed = []
    for n in names:
        try:
            s = extract.run(n, st, store_url=a.store, dry_run=a.dry_run, log=_log,
                            t_end=a.end, t_start=a.start)
            _log(json.dumps(s, default=str))
        except Exception as e:  # keep going with the other products
            import traceback
            traceback.print_exc()
            _log(f"[{n}] FAILED: {e!r}")
            failed.append(n)
    if failed:  # non-zero exit so wrappers (retry loops, queues) do not treat it as done
        sys.exit(f"extract failed: {', '.join(failed)}")


def _metrics_one(args):
    site, products, root = args
    from . import metrics
    try:
        if site["tier"] == 4:
            return metrics.remote_metrics(__import__("pandas").Series(site), products, root)
        return metrics.site_metrics(__import__("pandas").Series(site), products, root)
    except Exception as e:  # one bad site must not stop the run
        return [{"site": site["site_id"], "error": repr(e)}]


def cmd_metrics(a):
    from concurrent.futures import ProcessPoolExecutor

    import pandas as pd

    from . import analysis, config, sites
    st = sites.load(a.sites)
    products = a.products or analysis.available_products(a.store)
    _log(f"metrics: {len(st)} sites x {len(products)} products: {products}")
    rows, errs = [], []
    jobs = [(r._asdict() if hasattr(r, "_asdict") else dict(r), products, a.store) for _, r in st.iterrows()]
    import multiprocessing as mp

    # spawn: icechunk's runtime threads do not survive fork
    with ProcessPoolExecutor(a.workers, mp_context=mp.get_context("spawn")) as ex:
        for k, res in enumerate(ex.map(_metrics_one, jobs, chunksize=4)):
            for r in res:
                (errs if "error" in r else rows).append(r)
            if k % 200 == 0:
                _log(f"metrics: {k}/{len(jobs)} sites, {len(rows)} rows")
    df = pd.DataFrame(rows)
    out = config.DATA / "results"
    out.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out / f"metrics_{a.tag}.parquet", index=False)
    if errs:
        pd.DataFrame(errs).to_csv(out / f"metrics_{a.tag}_errors.csv", index=False)
    _log(f"metrics: {len(df)} rows, {len(errs)} site errors -> {out / f'metrics_{a.tag}.parquet'}")


def cmd_figures(a):
    from . import figures
    figures.run(log=_log)


def cmd_sitedata(a):
    import pandas as pd

    from . import config, export_site, sites
    m = pd.read_parquet(config.DATA / "results" / "metrics_all.parquet")
    export_site.export(sites.load(a.sites), m, root=a.store, log=_log)


def cmd_status(a):
    from . import store
    from .products import registry
    for n in registry.names():
        try:
            s = store.readonly("products", n, a.store)
            g = store.group_attrs(s, store.group_path("products", n, registry.get(n).freq))
            se = g.get("site_end", {})
            ends = sorted(set(se.values()))
            print(f"{n:16s} sites={len(g.get('sites', [])):5d} end={ends[0] if ends else '-'} .. {ends[-1] if ends else '-'}")
        except Exception as e:
            print(f"{n:16s} -- {type(e).__name__}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="aqc")
    p.add_argument("--store", default=None, help="store root URL (default AQC_STORE or data/store)")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sites"); s.add_argument("--networks", default="aqs,embassy,spartan"); s.set_defaults(fn=cmd_sites)
    s = sub.add_parser("obs"); s.add_argument("--networks", default="aqs,embassy,spartan")
    s.add_argument("--vars", default="", help="AQS hourly variables to (re)ingest, e.g. pm25 (default: all)")
    s.set_defaults(fn=cmd_obs)
    for name in ("extract", "update"):
        s = sub.add_parser(name)
        s.add_argument("products", nargs="*", default=["all"])
        s.add_argument("--sites", default="all")
        s.add_argument("--start", default=None)
        s.add_argument("--end", default=None)
        s.add_argument("--dry-run", action="store_true")
        s.set_defaults(fn=cmd_extract)
    s = sub.add_parser("status"); s.set_defaults(fn=cmd_status)
    s = sub.add_parser("cams-store", help="build the global CAMS EAC4 store (global-cams_eac4) from the ADS")
    s.add_argument("--blocks", default=None, help="31-day block range, e.g. 0-11 (default: all 271)")
    s.add_argument("--workers", type=int, default=2, help="parallel ADS downloads")
    s.add_argument("--group", type=int, default=3, help="consecutive 31-day blocks per ADS request")
    s.set_defaults(fn=cmd_cams_store)
    s = sub.add_parser("figures"); s.set_defaults(fn=cmd_figures)
    s = sub.add_parser("sitedata"); s.add_argument("--sites", default="all"); s.set_defaults(fn=cmd_sitedata)
    s = sub.add_parser("metrics")
    s.add_argument("products", nargs="*", default=[])
    s.add_argument("--sites", default="all")
    s.add_argument("--workers", type=int, default=2)
    s.add_argument("--tag", default="all")
    s.set_defaults(fn=cmd_metrics)
    a = p.parse_args(argv)
    if getattr(a, "products", None) == [] and a.cmd in ("extract", "update"):
        a.products = ["all"]
    a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
