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
            frames = {v: aqs.hourly(st, v, log=_log).rename(columns={}) for v in ("pm25", "pm10", "o3", "no2")}
            ingest.write("AQS", "1h", frames, store_url=a.store, log=_log)
            frm = aqs.daily_frm(st).rename(columns={"date": "time"})
            ingest.write("AQS", "1d", {"pm25_frm": frm}, attrs={"day": "local standard day"}, store_url=a.store, log=_log)
        elif net == "embassy":
            from .obs import embassy
            ingest.write("Embassy", "1h", {"pm25": embassy.hourly(sites.load("embassy"))}, store_url=a.store, log=_log)
        elif net == "spartan":
            from .obs import spartan
            ingest.write("SPARTAN", "1h", {"pm25": spartan.hourly(sites.load("spartan"))}, store_url=a.store, log=_log)
        else:
            raise SystemExit(f"unknown network {net}")


def cmd_extract(a):
    from . import extract, sites
    from .products import registry
    names = registry.names() if a.products == ["all"] else a.products
    st = sites.load(a.sites)
    for n in names:
        try:
            s = extract.run(n, st, store_url=a.store, dry_run=a.dry_run, log=_log,
                            t_end=a.end, t_start=a.start)
            _log(json.dumps(s, default=str))
        except Exception as e:  # keep going with the other products
            import traceback
            traceback.print_exc()
            _log(f"[{n}] FAILED: {e!r}")


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
    s = sub.add_parser("obs"); s.add_argument("--networks", default="aqs,embassy,spartan"); s.set_defaults(fn=cmd_obs)
    for name in ("extract", "update"):
        s = sub.add_parser(name)
        s.add_argument("products", nargs="*", default=["all"])
        s.add_argument("--sites", default="all")
        s.add_argument("--start", default=None)
        s.add_argument("--end", default=None)
        s.add_argument("--dry-run", action="store_true")
        s.set_defaults(fn=cmd_extract)
    s = sub.add_parser("status"); s.set_defaults(fn=cmd_status)
    a = p.parse_args(argv)
    if getattr(a, "products", None) == []:
        a.products = ["all"]
    a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
