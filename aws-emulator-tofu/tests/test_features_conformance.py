"""tipg-lite vs real tipg (1.x, FastAPI TestClient on a local PostGIS): API-surface conformance.

Most-common-use-case only: collections listing, collection metadata, items with limit/offset/bbox/
properties/property filters, single item, 404s. Compared: status codes, content types, JSON keys,
link relations, numberMatched/numberReturned and returned feature ids.
"""
import importlib.util
import os
import sqlite3
import sys

import pytest

from lambda_harness import ROOT, call, load

VEC = ROOT / "data" / "vectors"
pytestmark = pytest.mark.skipif(not (VEC / "countries.geojson").exists(), reason="run `mise run fetch` first")


def _loader():
    spec = importlib.util.spec_from_file_location("load_vectors", ROOT / "scripts" / "load_vectors.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def lite():
    lv = _loader()
    conn = sqlite3.connect(":memory:")
    w = lv.SQLiteWriter(conn)
    lv.load(w)
    mod = load("features_lite")
    mod.DB = w
    return mod


@pytest.fixture(scope="module")
def ref():
    import pg_reference
    try:
        dsn = pg_reference.start()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"local PostGIS unavailable: {e}")
    os.environ["DATABASE_URL"] = dsn
    os.environ["TIPG_DB_SCHEMAS"] = '["public"]'
    os.environ["TIPG_EXCLUDE_TABLE_PATTERN"] = r"spatial_ref_sys|geography_columns|geometry_columns|raster_.*"
    from fastapi.testclient import TestClient
    from tipg.main import app
    with TestClient(app) as c:
        yield c


def rels(links):
    return sorted(link["rel"] for link in links)


def get_both(lite, ref, path, params=None):
    rr = ref.get(path, params=params or {})
    st, hdr, body = call(lite, "/features" + path, params or {})
    return rr, (st, hdr, body)


def test_collections(lite, ref):
    rr, (st, hdr, b) = get_both(lite, ref, "/collections")
    r = rr.json()
    assert st == rr.status_code == 200
    assert set(b) == set(r)
    ours = {c["id"]: c for c in b["collections"]}
    theirs = {c["id"]: c for c in r["collections"]}
    assert set(ours) <= set(theirs)
    for cid, c in ours.items():
        t = theirs[cid]
        assert set(c) - {"description"} <= set(t) | {"title"}, cid
        assert rels(c["links"]) == sorted(set(rels(c["links"])) & set(rels(t["links"])))
        assert c["extent"]["spatial"]["bbox"][0] == pytest.approx(t["extent"]["spatial"]["bbox"][0], abs=1e-6)


@pytest.mark.parametrize("cid", ["public.countries", "public.populated_places", "public.rivers"])
def test_collection(lite, ref, cid):
    rr, (st, hdr, b) = get_both(lite, ref, f"/collections/{cid}")
    assert st == rr.status_code == 200
    assert {"id", "links", "extent", "itemType", "crs"} <= set(b) and {"id", "links", "extent", "itemType", "crs"} <= set(rr.json())
    assert {"self", "items", "queryables"} <= set(rels(b["links"])) and {"self", "items", "queryables"} <= set(rels(rr.json()["links"]))


ITEM_CASES = [
    ("countries-default", "public.countries", {}),
    ("countries-bbox", "public.countries", {"limit": 2, "bbox": "0,40,10,50"}),
    ("countries-bbox-page2", "public.countries", {"limit": 3, "offset": 3, "bbox": "0,40,10,50"}),
    ("countries-properties", "public.countries", {"limit": 1, "offset": 3, "properties": "name,iso_a3"}),
    ("countries-filter", "public.countries", {"limit": 1, "name": "Canada"}),
    ("countries-filter-int", "public.countries", {"continent": "Oceania", "limit": 50}),
    ("places-bbox", "public.populated_places", {"bbox": "-10,35,30,60", "limit": 100}),
    ("rivers-bbox", "public.rivers", {"bbox": "-100,30,-80,50"}),
]


@pytest.mark.parametrize("name,cid,params", ITEM_CASES, ids=[c[0] for c in ITEM_CASES])
def test_items(lite, ref, name, cid, params):
    rr, (st, hdr, b) = get_both(lite, ref, f"/collections/{cid}/items", params)
    r = rr.json()
    assert st == rr.status_code == 200
    assert hdr["Content-Type"] == rr.headers["content-type"] == "application/geo+json"
    assert set(b) == set(r)
    assert (b["numberMatched"], b["numberReturned"]) == (r["numberMatched"], r["numberReturned"])
    assert [f["id"] for f in b["features"]] == [f["id"] for f in r["features"]]
    assert rels(b["links"]) == rels(r["links"])
    for fa, fb in zip(b["features"], r["features"]):
        assert set(fa) == set(fb)
        assert set(fa["properties"]) == set(fb["properties"])
        assert fa["geometry"]["type"] == fb["geometry"]["type"]


def test_item(lite, ref):
    rr, (st, hdr, b) = get_both(lite, ref, "/collections/public.countries/items/5")
    r = rr.json()
    assert st == rr.status_code == 200
    assert set(b) == set(r) and b["id"] == r["id"] and b["properties"] == pytest.approx(r["properties"])
    assert rels(b["links"]) == rels(r["links"])


@pytest.mark.parametrize("path", ["/collections/public.nope/items", "/collections/public.countries/items/99999"])
def test_404(lite, ref, path):
    rr, (st, hdr, b) = get_both(lite, ref, path)
    assert st == rr.status_code == 404
    assert set(b) == set(rr.json()) == {"detail"}


def test_conformance_and_landing(lite, ref):
    for path in ["/", "/conformance"]:
        rr, (st, _, b) = get_both(lite, ref, path)
        assert st == rr.status_code == 200
        assert set(b) <= set(rr.json())
    rr, (st, _, b) = get_both(lite, ref, "/conformance")
    assert set(b["conformsTo"]) <= set(rr.json()["conformsTo"])
