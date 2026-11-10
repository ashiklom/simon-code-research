"""Download all granules listed in config/granules.toml (+ DMR++ sidecars) and
config/geo_scenes.toml (geolocation-only consistency set) into data/raw/ (git-ignored).

Needs EARTHDATA_LOGIN_USER / EARTHDATA_LOGIN_PASSWORD.
Usage: python scripts/01_download.py [--main-only]
"""

import argparse
from concurrent.futures import ThreadPoolExecutor

from swathgeo import config, earthdata as ed

ap = argparse.ArgumentParser()
ap.add_argument("--main-only", action="store_true")
args = ap.parse_args()

jobs = []
for name, sc in config.scenes().items():
    for k in ("geo", "l2", "att"):
        for u in sc.get(k, []):
            jobs.append((u, config.local_path(u, sc["sensor"]).parent))
            if k in ("geo", "l2"):  # DMR++ sidecars (may not exist for every product)
                jobs.append((u + ".dmrpp", config.local_path(u, sc["sensor"]).parent / "dmrpp"))

if not args.main_only and (config.CONFIG / "geo_scenes.toml").exists():
    for s in config.load_toml("geo_scenes.toml")["scene"]:
        jobs.append((s["url"], config.RAW / "geo_only" / s["sensor"]))
        if s.get("att"):
            jobs.append((s["att"], config.RAW / "geo_only" / s["sensor"]))

session = ed.EarthdataSession()


def get(job):
    url, dest = job
    try:
        p = ed.download(url, dest, session, retries=2 if url.endswith(".dmrpp") else 4)
        return f"ok   {p.relative_to(config.ROOT)}"
    except Exception as e:  # noqa: BLE001
        if url.endswith(".dmrpp"):
            return f"--   no DMR++ sidecar: {url.rsplit('/', 1)[-1]}"
        return f"FAIL {url} ({e.__class__.__name__}: {e})"


with ThreadPoolExecutor(6) as ex:
    for msg in ex.map(get, jobs):
        print(msg, flush=True)
