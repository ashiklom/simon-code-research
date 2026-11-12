"""Local PostGIS (conda-forge, no Docker) loaded with the same vectors, for the real-tipg reference."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PGDATA = ROOT / "data" / "pg"
PORT = 54329
VECTORS = ROOT / "data" / "vectors"
DSN = f"postgresql://postgres@127.0.0.1:{PORT}/features"


def _run(*a, **kw):
    # PostgreSQL refuses to run as root; drop to `nobody` when needed (e.g. in containers).
    if os.geteuid() == 0:
        a = ("setpriv", "--reuid=nobody", "--regid=nogroup", "--clear-groups", *a)
    return subprocess.run(a, check=True, capture_output=True, text=True, **kw)


def start() -> str:
    if not (PGDATA / "PG_VERSION").exists():
        PGDATA.mkdir(parents=True, exist_ok=True)
        if os.geteuid() == 0:
            shutil.chown(PGDATA, "nobody", "nogroup")
        _run("initdb", "-D", str(PGDATA), "-U", "postgres", "--auth=trust")
    try:
        _run("pg_ctl", "-D", str(PGDATA), "status")
    except subprocess.CalledProcessError:
        _run("pg_ctl", "-D", str(PGDATA), "-l", str(PGDATA / "log.txt"), "-o",
             f"-p {PORT} -k {PGDATA} -c listen_addresses=127.0.0.1", "start")
        time.sleep(1.5)
    import psycopg
    with psycopg.connect(f"postgresql://postgres@127.0.0.1:{PORT}/postgres", autocommit=True) as c:
        if not c.execute("select 1 from pg_database where datname='features'").fetchone():
            c.execute("create database features")
    with psycopg.connect(DSN, autocommit=True) as c:
        c.execute("create extension if not exists postgis")
        for path in sorted(VECTORS.glob("*.geojson")):
            name = path.stem
            fc = json.loads(path.read_text())
            props = list(fc["features"][0]["properties"])
            types = {k: _pgtype([f["properties"][k] for f in fc["features"]]) for k in props}
            c.execute(f"drop table if exists public.{name}")
            cols = ", ".join(f'"{k}" {types[k]}' for k in props)
            c.execute(f"create table public.{name} (id integer primary key, {cols}, geom geometry(Geometry, 4326))")
            for f in fc["features"]:
                vals = [f["properties"][k] for k in props]
                ph = ", ".join(["%s"] * len(props))
                c.execute(f"insert into public.{name} values (%s, {ph}, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))",
                          [f["id"], *vals, json.dumps(f["geometry"])])
            c.execute(f"create index on public.{name} using gist (geom)")
    return DSN


def _pgtype(values) -> str:
    vals = [v for v in values if v is not None]
    if vals and all(isinstance(v, int) and not isinstance(v, bool) for v in vals):
        return "bigint"
    if vals and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
        return "double precision"
    return "text"


def stop() -> None:
    subprocess.run(["pg_ctl", "-D", str(PGDATA), "stop", "-m", "fast"], capture_output=True)


if __name__ == "__main__":
    print(start())
