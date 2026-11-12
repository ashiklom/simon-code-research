"""tipg-lite: a tipg-compatible OGC API - Features subset in pure Python over the RDS Data API.

Routes (rooted at /features so authorizer policies can grant `*/features/*`):
  GET /features/                                   landing page
  GET /features/conformance
  GET /features/collections
  GET /features/collections/{collectionId}
  GET /features/collections/{collectionId}/queryables
  GET /features/collections/{collectionId}/items   ?limit&offset&bbox&properties&<column>=<value>&sortby
  GET /features/collections/{collectionId}/items/{itemId}
Collection ids, parameters and JSON shapes follow tipg 1.x. Geometries are stored as GeoJSON text
with bbox columns (no PostGIS on aws-emulator); bbox filtering is an SQL bbox prefilter followed by
an exact intersection test in Python (geom.intersects), so results match ST_Intersects.
"""
import json
import re

from apigw import HTTPError, dispatch, response
from geom import intersects

PREFIX = "/features"
DB = None  # set lazily (tests inject a sqlite-backed object with the same .query interface)
MAX_LIMIT = 10000
CRS84 = "http://www.opengis.net/def/crs/OGC/1.3/CRS84"
CONFORMANCE = [
    "http://www.opengis.net/spec/ogcapi-common-1/1.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-common-1/1.0/conf/landingPage",
    "http://www.opengis.net/spec/ogcapi-common-2/1.0/conf/collections",
    "http://www.opengis.net/spec/ogcapi-common-2/1.0/conf/simple-query",
    "http://www.opengis.net/spec/ogcapi-common-1/1.0/conf/json",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson",
]
JSON = "application/json"
GEOJSON = "application/geo+json"


def db():
    global DB
    if DB is None:
        from db import DataAPI
        DB = DataAPI()
    return DB


def _collections():
    rows = db().query("SELECT id, title, description, columns, bbox, geometry_type FROM _collections ORDER BY id")
    out = {}
    for r in rows:
        r["columns"] = json.loads(r["columns"])
        r["bbox"] = json.loads(r["bbox"])
        out[r["id"]] = r
    return out


def _collection(cid):
    cols = _collections()
    if cid not in cols:
        raise HTTPError(404, f"Table/Function '{cid}' not found.")
    return cols[cid]


def _table(c):
    name = c["id"].split(".", 1)[-1]
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise HTTPError(500, "bad table name")
    return name


def _collection_json(req, c, self_rel=False):
    base = f"{PREFIX}/collections/{c['id']}"
    if self_rel:
        links = [
            {"href": req.url(base), "rel": "self", "type": JSON, "title": "Collection"},
            {"href": req.url(base + "/items"), "rel": "items", "type": GEOJSON, "title": "Items"},
            {"href": req.url(base + "/queryables"), "rel": "queryables", "type": "application/schema+json",
             "title": "Queryables"},
        ]
    else:
        links = [
            {"href": req.url(base), "rel": "collection", "type": JSON},
            {"href": req.url(base + "/items"), "rel": "items", "type": GEOJSON},
            {"href": req.url(base + "/queryables"), "rel": "queryables", "type": "application/schema+json"},
        ]
    return {
        "id": c["id"],
        "title": c["title"] or c["id"],
        "description": c["description"] or c["id"],
        "links": links,
        "extent": {"spatial": {"bbox": [c["bbox"]], "crs": CRS84}},
        "itemType": "feature",
        "crs": [CRS84],
    }


def landing(req):
    return response(200, {
        "title": "tipg-lite: OGC Features API",
        "links": [
            {"href": req.url(PREFIX + "/"), "rel": "self", "type": JSON, "title": "Landing Page"},
            {"href": req.url(PREFIX + "/conformance"), "rel": "conformance", "type": JSON, "title": "Conformance"},
            {"href": req.url(PREFIX + "/collections"), "rel": "data", "type": JSON,
             "title": "List of Collections"},
        ],
    })


def conformance(req):
    return response(200, {"conformsTo": CONFORMANCE})


def collections(req):
    cols = [_collection_json(req, c) for c in _collections().values()]
    return response(200, {
        "links": [{"href": req.url(PREFIX + "/collections"), "rel": "self", "type": JSON}],
        "numberMatched": len(cols), "numberReturned": len(cols), "collections": cols,
    })


def collection(req, cid):
    return response(200, _collection_json(req, _collection(cid), self_rel=True))


def queryables(req, cid):
    c = _collection(cid)
    props = {"geom": {"$ref": "https://geojson.org/schema/Geometry.json"}}
    for name, typ in c["columns"]:
        props[name] = {"name": name, "type": "number" if typ in ("bigint", "integer", "double precision") else "string"}
    return response(200, {
        "title": cid, "properties": props, "type": "object",
        "$schema": "https://json-schema.org/draft/2019-09/schema",
        "$id": req.url(f"{PREFIX}/collections/{cid}/queryables"),
    }, content_type="application/schema+json")


def _feature(req, c, row, props_filter=None, self_link=False):
    props = {name: row.get(name) for name, _ in c["columns"]
             if props_filter is None or name in props_filter}
    base = f"{PREFIX}/collections/{c['id']}"
    item = f"{base}/items/{row['id']}"
    if self_link:
        links = [{"href": req.url(base), "rel": "collection", "type": JSON},
                 {"href": req.url(item), "rel": "self", "type": GEOJSON}]
    else:
        links = [{"title": "Collection", "href": req.url(base), "rel": "collection", "type": JSON},
                 {"title": "Item", "href": req.url(item), "rel": "item", "type": GEOJSON}]
    return {"type": "Feature", "geometry": json.loads(row["geom"]), "id": row["id"],
            "properties": props, "links": links}


def items(req, cid):
    c = _collection(cid)
    table = _table(c)
    colnames = [n for n, _ in c["columns"]]
    coltypes = dict(c["columns"])
    try:
        limit = min(int(req.arg("limit", "10")), MAX_LIMIT)
        offset = int(req.arg("offset", "0"))
    except ValueError:
        raise HTTPError(422, "limit/offset must be integers")
    where, params = [], {}
    # Property equality filters (tipg: any queryable column name as a query parameter).
    for k, vs in req.query_multi.items():
        if k in colnames:
            p = f"p{len(params)}"
            typ = coltypes[k]
            try:
                val = int(vs[0]) if typ in ("bigint", "integer") else float(vs[0]) if typ == "double precision" else vs[0]
            except ValueError:
                raise HTTPError(422, f"Invalid value for {k}")
            where.append(f'"{k}" = :{p}')
            params[p] = val
    bbox = None
    if req.arg("bbox"):
        try:
            bbox = [float(v) for v in req.arg("bbox").split(",")]
            assert len(bbox) == 4
        except (ValueError, AssertionError):
            raise HTTPError(422, "bbox must be minx,miny,maxx,maxy")
        where.append("maxx >= :bx0 AND minx <= :bx1 AND maxy >= :by0 AND miny <= :by1")
        params.update(bx0=bbox[0], bx1=bbox[2], by0=bbox[1], by1=bbox[3])
    order = "id"
    sortby = req.arg("sortby")
    if sortby:
        key = sortby.lstrip("+-")
        if key not in colnames:
            raise HTTPError(422, f"Invalid sortby column {key}")
        order = f'"{key}" {"DESC" if sortby.startswith("-") else "ASC"}, id'
    props_filter = None
    if req.arg("properties") is not None:
        props_filter = [p for p in req.arg("properties").split(",") if p]
    sel = ", ".join(["id", *[f'"{n}"' for n in colnames if n != "id"], "geom"])
    wsql = (" WHERE " + " AND ".join(where)) if where else ""
    if bbox:
        rows = db().query(f"SELECT {sel} FROM {table}{wsql} ORDER BY {order}", params)
        rows = [r for r in rows if intersects(json.loads(r["geom"]), bbox)]
        matched = len(rows)
        rows = rows[offset:offset + limit]
    else:
        matched = db().query(f"SELECT count(*) AS n FROM {table}{wsql}", params)[0]["n"]
        rows = db().query(f"SELECT {sel} FROM {table}{wsql} ORDER BY {order} LIMIT :lim OFFSET :off",
                          {**params, "lim": limit, "off": offset})
    feats = [_feature(req, c, r, props_filter) for r in rows]
    qs = [(k, v) for k, vs in req.query_multi.items() for v in vs]
    base = f"{PREFIX}/collections/{cid}"
    links = [{"title": "Collection", "href": req.url(base), "rel": "collection", "type": JSON},
             {"title": "Items", "href": req.url(base + "/items", qs), "rel": "self", "type": GEOJSON}]
    nq = [(k, v) for k, v in qs if k != "offset"]
    if offset + len(feats) < matched:
        links.append({"href": req.url(base + "/items", nq + [("offset", str(offset + limit))]),
                      "rel": "next", "type": GEOJSON, "title": "Next page"})
    if offset > 0:
        prev = max(offset - limit, 0)
        links.append({"href": req.url(base + "/items", nq + ([("offset", str(prev))] if prev else [])),
                      "rel": "prev", "type": GEOJSON, "title": "Previous page"})
    return response(200, {
        "type": "FeatureCollection", "id": cid, "title": c["title"] or cid, "description": c["description"] or cid,
        "numberMatched": matched, "numberReturned": len(feats), "links": links, "features": feats,
    }, content_type=GEOJSON)


def item(req, cid, iid):
    c = _collection(cid)
    table = _table(c)
    colnames = [n for n, _ in c["columns"]]
    sel = ", ".join(["id", *[f'"{n}"' for n in colnames if n != "id"], "geom"])
    try:
        key = int(iid)
    except ValueError:
        raise HTTPError(404, f"Item {iid} in Collection {cid} does not exist.")
    rows = db().query(f"SELECT {sel} FROM {table} WHERE id = :id", {"id": key})
    if not rows:
        raise HTTPError(404, f"Item {iid} in Collection {cid} does not exist.")
    return response(200, _feature(req, c, rows[0], self_link=True), content_type=GEOJSON)


CID = r"(?P<cid>[A-Za-z0-9_.]+)"
ROUTES = [
    ("GET", re.compile(PREFIX + r"/?"), landing),
    ("GET", re.compile(PREFIX + r"/conformance"), conformance),
    ("GET", re.compile(PREFIX + r"/collections/?"), collections),
    ("GET", re.compile(PREFIX + rf"/collections/{CID}/?"), collection),
    ("GET", re.compile(PREFIX + rf"/collections/{CID}/queryables"), queryables),
    ("GET", re.compile(PREFIX + rf"/collections/{CID}/items/?"), items),
    ("GET", re.compile(PREFIX + rf"/collections/{CID}/items/(?P<iid>[^/]+)"), item),
]


def handler(event, context):
    return dispatch(ROUTES, event)
