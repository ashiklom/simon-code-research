"""titiler-lite: a titiler-compatible subset (the common `/cog` endpoints) in pure Python.

Routes (the API is rooted at /tiler so authorizer policies can grant `*/tiler/*`):
  GET /tiler/cog/info?url=s3://bucket/key
  GET /tiler/cog/WebMercatorQuad/tilejson.json?url=...[&tilesize=&rescale=&colormap_name=&bidx=]
  GET /tiler/cog/tiles/WebMercatorQuad/{z}/{x}/{y}[.png]?url=...[&tilesize=&rescale=&colormap_name=&bidx=]
  GET /tiler/cog/point/{lon},{lat}?url=...
Request parameters and JSON response shapes follow titiler 2.x (`titiler.core.TilerFactory`).
"""
import os
import re

from apigw import HTTPError, dispatch, response
from cog import COG, COGError, lonlat_to_merc, merc_to_lonlat
from render import render

PREFIX = "/tiler"
ALLOWED_BUCKETS = [b for b in os.environ.get("ALLOWED_BUCKETS", "").split(",") if b]
_COGS = {}


def _s3_fetcher(url):
    import boto3  # resolved by the Lambda runtime (real boto3 on AWS, a stand-in on aws-emulator)

    m = re.fullmatch(r"s3://([^/]+)/(.+)", url)
    if not m:
        raise HTTPError(400, "url must be an s3://bucket/key URL")
    bucket, key = m.groups()
    if ALLOWED_BUCKETS and bucket not in ALLOWED_BUCKETS:
        raise HTTPError(403, f"Bucket '{bucket}' is not allowed")
    s3 = boto3.client("s3")

    def fetch(start, length):
        try:
            r = s3.get_object(Bucket=bucket, Key=key, Range=f"bytes={start}-{start + length - 1}")
        except Exception as e:  # noqa: BLE001 - surface S3 errors like titiler (500 + detail)
            msg = str(e)
            if "NoSuchKey" in msg or "Not Found" in msg or "404" in msg:
                raise HTTPError(404, f"{url} not found")
            if "InvalidRange" in msg:
                return b""
            raise HTTPError(500, msg)
        return r["Body"].read()

    return fetch


FETCHER = _s3_fetcher  # tests swap this for a local-file fetcher


def open_cog(url):
    if not url:
        raise HTTPError(422, "Missing required query parameter: url")
    if url not in _COGS:
        try:
            _COGS[url] = COG(FETCHER(url))
        except COGError as e:
            raise HTTPError(e.status, e.detail)
    return _COGS[url]


def _params(req):
    bidx = [int(b) for b in req.args("bidx")] or None
    rescale = []
    for r in req.args("rescale"):
        try:
            lo, hi = (float(v) for v in r.split(","))
        except ValueError:
            raise HTTPError(422, f"Invalid rescale value: {r}")
        rescale.append((lo, hi))
    return bidx, rescale or None, req.arg("colormap_name")


def _tms(tms):
    if tms != "WebMercatorQuad":
        raise HTTPError(422, f"Unsupported TileMatrixSet '{tms}' (titiler-lite only serves WebMercatorQuad)")


def info(req):
    cog = open_cog(req.arg("url"))
    names = [f"b{i}" for i in range(1, cog.spp + 1)]
    interp = {2: ["red", "green", "blue", "alpha"][: cog.spp]}.get(cog.photometric, ["gray"] * cog.spp)
    return response(200, {
        "bounds": list(cog.bounds),
        "crs": "http://www.opengis.net/def/crs/EPSG/0/3857",
        "band_metadata": [[n, {}] for n in names],
        "band_descriptions": [[n, n] for n in names],
        "dtype": cog.dtype,
        "nodata_type": "Nodata" if cog.nodata is not None else "None",
        "colorinterp": interp,
        "scales": [1.0] * cog.spp,
        "offsets": [0.0] * cog.spp,
        "driver": "GTiff",
        "count": cog.spp,
        "width": cog.levels[0].width,
        "height": cog.levels[0].height,
        "overviews": [2 ** i for i in range(1, len(cog.levels))],
        "nodata_value": cog.nodata,
    })


def tilejson(req, tms):
    _tms(tms)
    cog = open_cog(req.arg("url"))
    minzoom = int(req.arg("minzoom", cog.minzoom))
    maxzoom = int(req.arg("maxzoom", cog.maxzoom))
    passthrough = [(k, v) for k, vs in req.query_multi.items() for v in vs
                   if k not in ("minzoom", "maxzoom", "tilesize")]
    passthrough.append(("tilesize", req.arg("tilesize", "512")))
    w, s = merc_to_lonlat(cog.bounds[0], cog.bounds[1])
    e, n = merc_to_lonlat(cog.bounds[2], cog.bounds[3])
    tiles = req.url(f"{PREFIX}/cog/tiles/{tms}/{{z}}/{{x}}/{{y}}", passthrough).replace("%7B", "{").replace("%7D", "}")
    names = [f"b{i}" for i in range(1, cog.spp + 1)]
    return response(200, {
        "tilejson": "3.0.0",
        "version": "1.0.0",
        "scheme": "xyz",
        "tiles": [tiles],
        "minzoom": minzoom,
        "maxzoom": maxzoom,
        "bounds": [w, s, e, n],
        "center": [(w + e) / 2, (s + n) / 2, minzoom],
        "raster_layers": {},
        "band_descriptions": [[n_, n_] for n_ in names],
        "data_type": cog.dtype,
    })


def tile(req, tms, z, x, y, fmt=None):
    _tms(tms)
    if fmt not in (None, "png"):
        raise HTTPError(422, f"titiler-lite only encodes PNG, not '{fmt}'")
    cog = open_cog(req.arg("url"))
    z, x, y = int(z), int(x), int(y)
    tilesize = int(req.arg("tilesize", "256"))
    bidx, rescale, cmap = _params(req)
    try:
        data, w, h = cog.read_tile(z, x, y, tilesize)
        body = render(cog, data, w, h, bidx=bidx, rescale=rescale, colormap_name=cmap)
    except COGError as e:
        raise HTTPError(e.status, e.detail)
    except KeyError as e:
        raise HTTPError(422, f"Invalid colormap name: {e.args[0]}")
    except ValueError as e:
        raise HTTPError(422, str(e))
    return response(200, body, content_type="image/png", binary=True)


def point(req, lon, lat):
    cog = open_cog(req.arg("url"))
    lon, lat = float(lon), float(lat)
    mx, my = lonlat_to_merc(lon, lat)
    b = cog.bounds
    if not (b[0] <= mx <= b[2] and b[1] <= my <= b[3]):
        raise HTTPError(404, "Point is outside dataset bounds")
    vals = cog.read_point(mx, my)
    if vals is None:
        raise HTTPError(404, "Point is outside dataset bounds")
    bidx, _, _ = _params(req)
    idx = bidx or list(range(1, cog.spp + 1))
    names = [f"b{i}" for i in idx]
    return response(200, {
        "coordinates": [lon, lat],
        "values": [vals[i - 1] for i in idx],
        "band_names": names,
        "band_descriptions": names,
    })


def landing(req):
    return response(200, {"title": "titiler-lite", "description": "titiler-compatible COG tiler subset",
                          "links": [{"href": req.url(f"{PREFIX}/cog/info"), "rel": "data"}]})


ROUTES = [
    ("GET", re.compile(PREFIX + r"/?"), landing),
    ("GET", re.compile(PREFIX + r"/cog/info"), info),
    ("GET", re.compile(PREFIX + r"/cog/(?P<tms>[^/]+)/tilejson\.json"), tilejson),
    ("GET", re.compile(PREFIX + r"/cog/tiles/(?P<tms>[^/]+)/(?P<z>\d+)/(?P<x>\d+)/(?P<y>\d+)(?:\.(?P<fmt>\w+))?"), tile),
    ("GET", re.compile(PREFIX + r"/cog/point/(?P<lon>[-\d.]+),(?P<lat>[-\d.]+)"), point),
]


def handler(event, context):
    return dispatch(ROUTES, event)
