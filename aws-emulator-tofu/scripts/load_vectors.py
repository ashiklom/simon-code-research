"""Load data/vectors/*.geojson into the features database (schema used by tipg-lite).

Each collection becomes a table `<name>` (id, <properties>, geom GeoJSON text, minx/miny/maxx/maxy)
plus a row in `_collections`. Works against any object with
  .query(sql, params_dict) and .batch(sql, [params_dict, ...]);
`DataAPIWriter` drives the RDS Data API (aws-emulator or AWS), tests use sqlite.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

VECTORS = Path(__file__).resolve().parent.parent / "data" / "vectors"


def pgtype(values) -> str:
    vals = [v for v in values if v is not None]
    if vals and all(isinstance(v, int) and not isinstance(v, bool) for v in vals):
        return "bigint"
    if vals and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
        return "double precision"
    return "text"


def bounds(g):
    def walk(c):
        if isinstance(c[0], (int, float)):
            yield c
        else:
            for x in c:
                yield from walk(x)
    pts = list(walk(g["coordinates"]))
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def load(db, vectors: Path = VECTORS) -> dict:
    db.query("DROP TABLE IF EXISTS _collections")
    db.query("CREATE TABLE _collections (id text primary key, title text, description text, "
             "columns text, bbox text, geometry_type text)")
    summary = {}
    for path in sorted(vectors.glob("*.geojson")):
        name = path.stem
        fc = json.loads(path.read_text())
        props = list(fc["features"][0]["properties"])
        types = {k: pgtype([f["properties"][k] for f in fc["features"]]) for k in props}
        db.query(f"DROP TABLE IF EXISTS {name}")
        cols = ", ".join(f'"{k}" {types[k]}' for k in props)
        db.query(f"CREATE TABLE {name} (id integer primary key, {cols}, geom text, "
                 "minx double precision, miny double precision, maxx double precision, maxy double precision)")
        names = ["id", *props, "geom", "minx", "miny", "maxx", "maxy"]
        ph = ", ".join(f":c{i}" for i in range(len(names)))
        sql = f"INSERT INTO {name} ({', '.join(chr(34) + n + chr(34) for n in names)}) VALUES ({ph})"
        rows, allb = [], []
        for f in fc["features"]:
            b = bounds(f["geometry"])
            allb.append(b)
            vals = [f["id"], *[f["properties"][k] for k in props], json.dumps(f["geometry"]), *b]
            rows.append({f"c{i}": v for i, v in enumerate(vals)})
        db.batch(sql, rows)
        bbox = [min(b[0] for b in allb), min(b[1] for b in allb), max(b[2] for b in allb), max(b[3] for b in allb)]
        gtypes = sorted({f["geometry"]["type"] for f in fc["features"]})
        # tipg exposes the table's own id column as a property too.
        columns = sorted([["id", "integer"], *[[k, types[k]] for k in props]])
        db.query("INSERT INTO _collections (id, title, description, columns, bbox, geometry_type) "
                 "VALUES (:id, :t, :d, :c, :b, :g)",
                 {"id": f"public.{name}", "t": f"public.{name}", "d": f"public.{name}",
                  "c": json.dumps(columns), "b": json.dumps(bbox), "g": ",".join(gtypes)})
        summary[name] = len(rows)
    return summary


class DataAPIWriter:
    def __init__(self, cluster_arn, secret_arn, database="features"):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lambdas" / "features_lite"))
        from db import DataAPI, _param  # vendored helper used by the Lambda itself
        self._param = _param
        self.api = DataAPI(cluster_arn, secret_arn, database)

    def query(self, sql, params=None):
        return self.api.query(sql, params)

    def batch(self, sql, rows, chunk=200):
        for i in range(0, len(rows), chunk):
            self.api.client.batch_execute_statement(
                resourceArn=self.api.cluster_arn, secretArn=self.api.secret_arn, database=self.api.database,
                sql=sql, parameterSets=[[self._param(k, v) for k, v in r.items()] for r in rows[i:i + chunk]])


class SQLiteWriter:
    def __init__(self, conn):
        self.conn = conn

    def query(self, sql, params=None):
        cur = self.conn.execute(sql, params or {})
        cols = [d[0] for d in cur.description] if cur.description else []
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def batch(self, sql, rows):
        self.conn.executemany(sql, rows)


if __name__ == "__main__":
    w = DataAPIWriter(os.environ["DB_CLUSTER_ARN"], os.environ["DB_SECRET_ARN"], os.environ.get("DB_NAME", "features"))
    print(json.dumps(load(w)))
