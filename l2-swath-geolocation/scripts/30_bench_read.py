"""Part C: read performance of different readers, locally and through simulated networks.

Setup (all local processes):
  * moto S3 server holding the benchmark granules (bucket "earthdata-sim"),
  * the throttling proxy (swathgeo.netsim) with one port per profile in config/net_profiles.toml,
  * icechunk repos of *virtual* references (VirtualiZarr) per (profile, file).

Tasks per sensor (one geolocation + one L2 granule):
  full         latitude + longitude + LST, whole granule
  window_site  33 x 33 pixel window around the site (what the analytic locator needs)
  window_poly  bounding window of Colusa County (~60 x 70 km)
plus, separately, the cost of *building* the virtual references over each network
(HDF5 file scan vs. DMR++ sidecar).

Every (reader, profile, task) runs in a fresh subprocess; proxy counters give request
counts and bytes. Outputs: results/read_bench.csv, results/virtual_build.csv,
results/read_windows.json.

Usage: python scripts/30_bench_read.py [--profiles a,b] [--sensors modis,viirs] [--reps N]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import os
import shutil
import socket
import subprocess
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from swathgeo import config
from swathgeo import readers as R

warnings.filterwarnings("ignore")

FILES = {
    "modis": {"geo": ("modis/MYD03.A2023154.2125.061.2023155150831.hdf", "hdf4", ["Latitude", "Longitude"]),
              "l2": ("modis/MYD11_L2.A2023154.2125.061.2023155175206.hdf", "hdf4", ["LST"])},
    "viirs": {"geo": ("viirs/VNP03MOD.A2023154.2012.002.2023155044803.nc", "hdf5",
                      ["geolocation_data/latitude", "geolocation_data/longitude"]),
              "l2": ("viirs/VNP21.A2023154.2012.002.2023156230312.nc", "hdf5", ["VIIRS_Swath_LSTE/Data Fields/LST"])},
    "ecostress": {"geo": ("ecostress/ECOv002_L1B_GEO_27837_005_20230603T202541_0711_02.h5", "hdf5",
                          ["Geolocation/latitude", "Geolocation/longitude"]),
                  "l2": ("ecostress/ECOv002_L2_LSTE_27837_005_20230603T202541_0711_03.h5", "hdf5", ["SDS/LST"])},
}
VIRTUAL_GROUPS = {  # group -> variables to drop (VNP21 has string _FillValue='n/a' on int vars)
    "viirs/VNP03MOD.A2023154.2012.002.2023155044803.nc": [("geolocation_data", [])],
    "viirs/VNP21.A2023154.2012.002.2023156230312.nc": [("VIIRS_Swath_LSTE/Data Fields", ["PWV", "QC", "oceanpix"])],
    "ecostress/ECOv002_L1B_GEO_27837_005_20230603T202541_0711_02.h5": [("Geolocation", [])],
    "ecostress/ECOv002_L2_LSTE_27837_005_20230603T202541_0711_03.h5": [("SDS", [])],
}
PROFILES = ["local", "zero_s3", "zero_http", "s3_in_region", "s3_cross_region", "https_earthdata", "nccs_portal"]
REPS = {"local": 3, "zero_s3": 2, "zero_http": 2, "s3_in_region": 3, "s3_cross_region": 3,
        "https_earthdata": 3, "nccs_portal": 5}
TIMEOUT_S = 400
ICE = config.DATA / "icechunk"
MOTO_PORT = 17999
BASE_PORT = 18000


def free(port):
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


# ---------------------------------------------------------------------------------------
def start_services(profiles):
    procs = []
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    if free(MOTO_PORT):
        procs.append(subprocess.Popen([shutil.which("moto_server") or "moto_server", "-H", "127.0.0.1", "-p",
                                       str(MOTO_PORT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env))
        for _ in range(100):
            if not free(MOTO_PORT):
                break
            time.sleep(0.1)
        upload()
    net = [p for p in profiles if p != "local"]
    allp = list(R.config.load_toml("net_profiles.toml")["profile"])
    proxy = subprocess.Popen([sys.executable, "-m", "swathgeo.netsim", "--config", str(config.CONFIG / "net_profiles.toml"),
                              "--profiles", ",".join(allp), "--files-root", str(config.RAW), "--base-port", str(BASE_PORT),
                              "--backend", f"http://127.0.0.1:{MOTO_PORT}"], stdout=subprocess.PIPE, text=True, env=env)
    line = proxy.stdout.readline()
    assert line.startswith("READY"), line
    ports = json.loads(line.split(" ", 1)[1])
    procs.append(proxy)
    return procs, ports


def upload():
    import s3fs

    fs = s3fs.S3FileSystem(endpoint_url=f"http://127.0.0.1:{MOTO_PORT}", key="testing", secret="testing",
                           client_kwargs={"region_name": "us-west-2"})
    if not fs.exists(R.BUCKET):
        fs.mkdir(R.BUCKET)
    for sensor, d in FILES.items():
        for _, (key, _, _) in d.items():
            for k in (key, key + ".dmrpp"):
                if (config.RAW / k).exists():
                    t = time.time()
                    fs.put(str(config.RAW / k), f"{R.BUCKET}/{k}")
                    print("uploaded", k, f"{time.time() - t:.1f}s", flush=True)


def access_for(profile, ports):
    if profile == "local":
        return R.Access("local")
    kind = R.config.load_toml("net_profiles.toml")["profile"][profile]["kind"]
    return R.Access(kind, ports[profile], profile)


def stats(port, reset=True):
    if port is None:
        return {}
    return requests.get(f"http://127.0.0.1:{port}/__stats" + ("?reset=1" if reset else ""), timeout=30).json()


# ---------------------------------------------------------------------------------------
def build_virtual_repos(profiles, ports):
    """Parse each HDF5 file once (locally), rewrite chunk URLs per profile, write icechunk."""
    from virtualizarr import open_virtual_dataset
    from virtualizarr.parsers import HDFParser
    import xarray as xr

    local = R.Access("local")
    reg = R.obstore_registry(local)
    for key, groups in VIRTUAL_GROUPS.items():
        vds_list = []
        for g, drop in groups:
            vds = open_virtual_dataset("file://" + str(config.RAW / key), registry=reg,
                                       parser=HDFParser(group=g, drop_variables=drop))
            vds_list.append((g, vds))
        for profile in profiles:
            acc = access_for(profile, ports)
            path = ICE / profile / key.replace("/", "__")
            if path.exists():
                continue
            prefix = R.container_prefix(acc)
            repo = R.open_repo(path, acc, create=True)
            s = repo.writable_session("main")
            for g, vds in vds_list:
                v2 = vds.vz.rename_paths(lambda old: prefix + key)
                v2.vz.to_icechunk(s.store, group=g)
            s.commit("virtual refs")
        print("virtual repos for", key, flush=True)


def _virtual_build_worker(profile, ports, key, parser_name, q):
    from virtualizarr import open_virtual_dataset
    from virtualizarr.parsers import DMRPPParser, HDFParser

    acc = access_for(profile, ports)
    port = ports.get(profile)
    try:
        stats(port)
        reg = R.obstore_registry(acc)
        g, drop = VIRTUAL_GROUPS[key][0]
        t = time.perf_counter()
        if parser_name == "hdf5_scan":
            url = acc.url(key) if acc.kind != "local" else "file://" + acc.url(key)
            vds = open_virtual_dataset(url, registry=reg, parser=HDFParser(group=g, drop_variables=drop))
        else:
            url = (acc.url(key) if acc.kind != "local" else "file://" + acc.url(key)) + ".dmrpp"
            vds = open_virtual_dataset(url, registry=reg, parser=DMRPPParser(group="/" + g.replace(" ", "_")))
        dt = time.perf_counter() - t
        q.put({"seconds": dt, "n_vars": len(vds.data_vars), **{f"net_{k}": v for k, v in stats(port).items()}})
    except Exception as e:  # noqa: BLE001
        q.put({"error": f"{type(e).__name__}: {e}"[:300]})


def bench_virtual_build(profiles, ports, reps=2):
    rows = []
    ctx = mp.get_context("spawn")
    for key in VIRTUAL_GROUPS:
        for parser_name in ("hdf5_scan", "dmrpp"):
            if parser_name == "dmrpp" and not (config.RAW / (key + ".dmrpp")).exists():
                continue
            for profile in profiles:
                for rep in range(reps):
                    q = ctx.Queue()
                    p = ctx.Process(target=_virtual_build_worker, args=(profile, ports, key, parser_name, q))
                    p.start()
                    p.join(TIMEOUT_S)
                    rec = q.get() if not p.is_alive() and not q.empty() else {"error": "timeout"}
                    if p.is_alive():
                        p.kill()
                    rows.append({"file": key, "parser": parser_name, "profile": profile, "rep": rep, **rec})
                    print(rows[-1], flush=True)
                    pd.DataFrame(rows).to_csv(config.RESULTS / "virtual_build.csv", index=False)


# ---------------------------------------------------------------------------------------
def make_reader(name):
    if name == "h5py":
        return R.H5pyReader()
    if name == "h5py_blockcache":
        return R.H5pyReader("blockcache", 8 * 2**20, name="h5py_blockcache")
    if name == "xarray_h5netcdf":
        return R.XarrayH5netcdfReader()
    if name == "gdal":
        return R.GdalReader(False)
    if name == "gdal_tuned":
        return R.GdalReader(True)
    if name == "pyhdf":
        return R.PyhdfReader()
    if name == "download_then_read":
        return R.DownloadThenRead()
    if name == "icechunk_virtual":
        return R.IcechunkVirtualReader(ICE)
    raise KeyError(name)


READERS = ["h5py", "h5py_blockcache", "xarray_h5netcdf", "gdal", "gdal_tuned", "pyhdf", "download_then_read",
           "icechunk_virtual"]


def digest(arrs):
    h = hashlib.sha1()
    for k in sorted(arrs):
        a = np.ascontiguousarray(arrs[k])
        h.update(str(a.shape).encode())
        h.update(a.tobytes())
    return h.hexdigest()[:12]


def _read_worker(reader_name, profile, ports, sensor, task, window, reps, q):
    acc = access_for(profile, ports)
    port = ports.get(profile)
    rdr = make_reader(reader_name)
    out = []
    for rep in range(reps):
        try:
            stats(port)
            t = time.perf_counter()
            arrs = {}
            for part in ("geo", "l2"):
                key, fmt, vars_ = FILES[sensor][part]
                arrs.update(rdr.read_many(acc, key, vars_, window))
            dt = time.perf_counter() - t
            nb = sum(a.nbytes for a in arrs.values())
            out.append({"rep": rep, "seconds": dt, "array_MB": nb / 1e6, "digest": digest(arrs),
                        **{f"net_{k}": v for k, v in stats(port).items()}})
        except Exception as e:  # noqa: BLE001
            out.append({"rep": rep, "error": f"{type(e).__name__}: {e}"[:300]})
        q.put(out[-1])
    q.put(None)


def bench_reads(profiles, sensors, ports, reps_override=None):
    ctx = mp.get_context("spawn")
    windows = json.loads((config.RESULTS / "read_windows.json").read_text())
    path = config.RESULTS / "read_bench.csv"
    rows = pd.read_csv(path).to_dict("records") if path.exists() else []
    done = {(r["sensor"], r["task"], r["profile"], r["reader"]) for r in rows}
    for sensor in sensors:
        fmt = FILES[sensor]["geo"][1]
        for task in ("window_site", "window_poly", "full"):
            window = None if task == "full" else windows[sensor][task]
            for profile in profiles:
                acc = access_for(profile, ports)
                for reader_name in READERS:
                    if (sensor, task, profile, reader_name) in done:
                        continue
                    rdr = make_reader(reader_name)
                    if not rdr.supports(fmt, acc.kind):
                        continue
                    if reader_name == "icechunk_virtual" and fmt == "hdf4":
                        continue  # no working virtual parser for MODIS HDF4 (see virtual_build)
                    reps = reps_override or REPS[profile]
                    q = ctx.Queue()
                    p = ctx.Process(target=_read_worker,
                                    args=(reader_name, profile, ports, sensor, task, window, reps, q))
                    p.start()
                    t0 = time.time()
                    got = []
                    while True:
                        try:
                            item = q.get(timeout=max(TIMEOUT_S - (time.time() - t0), 1))
                        except Exception:  # noqa: BLE001
                            got.append({"rep": len(got), "error": "timeout"})
                            break
                        if item is None:
                            break
                        got.append(item)
                    if p.is_alive():
                        p.kill()
                    p.join()
                    for g in got:
                        rows.append({"sensor": sensor, "task": task, "profile": profile, "reader": reader_name, **g})
                    ok = [g["seconds"] for g in got if "seconds" in g]
                    print(f"{sensor:9s} {task:11s} {profile:16s} {reader_name:18s} "
                          f"median {np.median(ok) if ok else float('nan'):8.3f}s  n_ok {len(ok)}/{len(got)} "
                          f"req {got[-1].get('net_requests', '-')} MB {got[-1].get('net_bytes', 0) / 1e6:.1f} "
                          f"{got[-1].get('error', '')[:80]}", flush=True)
                    pd.DataFrame(rows).to_csv(path, index=False)


def compute_windows():
    """Pixel windows for the site and the county polygon in each benchmark granule."""
    import geopandas as gpd

    from swathgeo import io, locate as L

    site = gpd.read_file(config.CONFIG / "targets/site.geojson").geometry.iloc[0]
    county = gpd.read_file(config.CONFIG / "targets/polygons.geojson").set_index("name").geometry["colusa_county"]
    out = {}
    for sensor, d in FILES.items():
        key = d["geo"][0]
        sw = io.read_geo(config.RAW / key, nav=False)
        loc = L.ScipyKDTree().build(sw.lat, sw.lon)
        r, c, _ = loc.query_points([site.y], [site.x])
        r, c = int(r[0]), int(c[0])
        nl, ns = sw.shape
        ws = [max(r - 16, 0), min(r + 17, nl), max(c - 16, 0), min(c + 17, ns)]
        pr, pc = loc.query_polygon(county, L.POLY_BUFFER_M[sensor])
        wp = [int(pr.min()), int(pr.max()) + 1, int(pc.min()), int(pc.max()) + 1]
        out[sensor] = {"window_site": ws, "window_poly": wp, "shape": [nl, ns]}
        print(sensor, out[sensor], flush=True)
    (config.RESULTS / "read_windows.json").write_text(json.dumps(out, indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profiles", default=",".join(PROFILES))
    ap.add_argument("--sensors", default="modis,viirs,ecostress")
    ap.add_argument("--reps", type=int, default=None)
    ap.add_argument("--steps", default="windows,virtual,build,read")
    a = ap.parse_args()
    profiles = a.profiles.split(",")
    steps = a.steps.split(",")
    if "windows" in steps and not (config.RESULTS / "read_windows.json").exists():
        compute_windows()
    procs, ports = start_services(profiles)
    try:
        if "virtual" in steps:
            build_virtual_repos(profiles, ports)
        if "build" in steps:
            bench_virtual_build([p for p in profiles if not p.startswith("zero")], ports)
        if "read" in steps:
            bench_reads(profiles, a.sensors.split(","), ports, a.reps)
    finally:
        for p in procs:
            p.terminate()


if __name__ == "__main__":
    main()
