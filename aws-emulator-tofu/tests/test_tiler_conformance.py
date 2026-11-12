"""titiler-lite vs real titiler (titiler.core 2.x via FastAPI TestClient): API-surface conformance.

Most-common-use-case only: same request parameters, same response shape (JSON keys/types, PNG
size/mode, status codes). Pixel values are not compared (nearest-neighbour vs GDAL resampling).
"""
import io
import math
from pathlib import Path

import pytest
from PIL import Image

from lambda_harness import ROOT, call, load

COGS = ROOT / "data" / "cogs"
S2 = COGS / "s2-aswan-tci.tif"
DEM = COGS / "cop90-alps-dem.tif"
pytestmark = pytest.mark.skipif(not S2.exists(), reason="run `mise run fetch` first")


def xyz(lon, lat, z):
    n = 2 ** z
    lr = math.radians(lat)
    return int((lon + 180) / 360 * n), int((1 - math.log(math.tan(lr) + 1 / math.cos(lr)) / math.pi) / 2 * n)


@pytest.fixture(scope="module")
def lite():
    mod = load("tiler_lite")

    def local(url):
        path = Path(url.replace("s3://local/", str(COGS) + "/"))

        def fetch(start, length):
            with open(path, "rb") as f:
                f.seek(start)
                return f.read(length)
        return fetch

    mod.FETCHER = local
    return mod


@pytest.fixture(scope="module")
def ref():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from titiler.core.errors import DEFAULT_STATUS_CODES, add_exception_handlers
    from titiler.core.factory import TilerFactory

    app = FastAPI()
    app.include_router(TilerFactory().router, prefix="/cog")
    add_exception_handlers(app, DEFAULT_STATUS_CODES)
    return TestClient(app)


def lite_get(lite, path, **params):
    url = params.pop("url")
    return call(lite, "/tiler" + path, {"url": "s3://local/" + Path(url).name, **params})


def shape(o):
    if isinstance(o, dict):
        return {k: shape(v) for k, v in o.items()}
    if isinstance(o, list):
        return [shape(o[0])] if o else []
    return type(o).__name__ if not isinstance(o, (int, float)) or isinstance(o, bool) else "number"


@pytest.mark.parametrize("cog", [S2, DEM], ids=["rgb-uint8", "dem-float32"])
def test_info(lite, ref, cog):
    r = ref.get("/cog/info", params={"url": str(cog)}).json()
    st, _, b = lite_get(lite, "/cog/info", url=cog)
    assert st == 200
    assert shape(b) == shape(r)
    for k in ("crs", "dtype", "count", "width", "height", "overviews", "nodata_value", "colorinterp", "nodata_type"):
        assert b[k] == r[k], k
    assert b["bounds"] == pytest.approx(r["bounds"], abs=1e-3)


@pytest.mark.parametrize("cog,params", [(S2, {}), (DEM, {"rescale": "500,4000", "colormap_name": "terrain"})],
                         ids=["rgb", "dem-colormap"])
def test_tilejson(lite, ref, cog, params):
    r = ref.get("/cog/WebMercatorQuad/tilejson.json", params={"url": str(cog), **params}).json()
    st, _, b = lite_get(lite, "/cog/WebMercatorQuad/tilejson.json", url=cog, **params)
    assert st == 200
    assert set(b) == set(r)
    for k in ("tilejson", "scheme", "minzoom", "maxzoom", "data_type", "band_descriptions"):
        assert b[k] == r[k], k
    assert b["bounds"] == pytest.approx(r["bounds"], abs=1e-6)
    assert b["tiles"][0].endswith(r["tiles"][0].split("/tiles/WebMercatorQuad", 1)[1].replace(str(cog).replace("/", "%2F"), "x")) or "{z}/{x}/{y}" in b["tiles"][0]
    assert "tilesize=512" in b["tiles"][0] and "tilesize=512" in r["tiles"][0]


CASES = [
    ("rgb-native", S2, (33.46, 16.73, 12), {}),
    ("rgb-overzoom", S2, (33.46, 16.73, 16), {}),
    ("rgb-512", S2, (33.46, 16.73, 11), {"tilesize": "512"}),
    ("rgb-bidx1", S2, (33.46, 16.73, 12), {"bidx": "1"}),
    ("rgb-rescale", S2, (33.46, 16.73, 13), {"rescale": "0,128"}),
    ("dem-gray", DEM, (7.5, 46.5, 10), {"rescale": "500,4000"}),
    ("dem-colormap", DEM, (7.5, 46.5, 9), {"rescale": "500,4000", "colormap_name": "terrain"}),
    ("dem-viridis-overzoom", DEM, (7.5, 46.5, 12), {"rescale": "500,4000", "colormap_name": "viridis"}),
]


@pytest.mark.parametrize("name,cog,where,params", CASES, ids=[c[0] for c in CASES])
def test_tile(lite, ref, name, cog, where, params):
    z = where[2]
    x, y = xyz(where[0], where[1], z)
    rr = ref.get(f"/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png", params={"url": str(cog), **params})
    st, hdr, body = lite_get(lite, f"/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png", url=cog, **params)
    assert (st, hdr["Content-Type"]) == (rr.status_code, rr.headers["content-type"])
    a, b = Image.open(io.BytesIO(body)), Image.open(io.BytesIO(rr.content))
    assert (a.size, a.mode) == (b.size, b.mode)
    # Same picture, roughly: mean absolute difference on a 0-255 scale stays small.
    import numpy as np
    da, db = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    assert np.abs(da - db).mean() < 20, np.abs(da - db).mean()


def test_tile_without_extension_is_an_image(lite, ref):
    x, y = xyz(33.46, 16.73, 12)
    st, hdr, body = lite_get(lite, f"/cog/tiles/WebMercatorQuad/12/{x}/{y}", url=S2)
    assert st == 200 and hdr["Content-Type"].startswith("image/")


def test_outside_bounds_404(lite, ref):
    rr = ref.get("/cog/tiles/WebMercatorQuad/3/0/0.png", params={"url": str(S2)})
    st, _, body = lite_get(lite, "/cog/tiles/WebMercatorQuad/3/0/0.png", url=S2)
    assert st == rr.status_code == 404
    assert body == rr.json()


def test_point(lite, ref):
    rr = ref.get("/cog/point/7.5,46.5", params={"url": str(DEM)}).json()
    st, _, b = lite_get(lite, "/cog/point/7.5,46.5", url=DEM)
    assert st == 200
    assert set(b) == set(rr), (b, rr)
    assert b["coordinates"] == rr["coordinates"]
    assert b["values"][0] == pytest.approx(rr["values"][0], abs=50)


def test_missing_url_422(lite):
    st, _, b = call(lite, "/tiler/cog/info", {})
    assert st == 422 and "detail" in b
