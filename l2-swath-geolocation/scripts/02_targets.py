"""Build the subsetting targets (written to config/targets/, committed).

- site.geojson: one point (Sacramento National Wildlife Refuge, CA: wetland/rice/orchard mosaic)
- points100.geojson: 100 random points (seed 42) inside the common footprint of all scenes
- polygons.geojson: Colusa County (US Census cartographic boundary 1:500k) plus two
  synthetic polygons around the site (3 km square, 10 km-radius circle)
"""

import io as _io
import zipfile

import geopandas as gpd
import numpy as np
import requests
import shapely
from shapely.geometry import Point, Polygon

from swathgeo import config, geom, io

OUT = config.CONFIG / "targets"
OUT.mkdir(parents=True, exist_ok=True)
SITE = (39.4275, -122.164)  # lat, lon

# --- point -------------------------------------------------------------------------
gpd.GeoDataFrame({"name": ["sacramento_nwr"]}, geometry=[Point(SITE[1], SITE[0])], crs=4326).to_file(
    OUT / "site.geojson", driver="GeoJSON")


# --- footprints -> common area -------------------------------------------------------
def footprint(sw, step=20):
    lat, lon = sw.lat, sw.lon
    ring = np.concatenate([
        np.stack([lat[0, ::step], lon[0, ::step]], -1),
        np.stack([lat[::step, -1], lon[::step, -1]], -1),
        np.stack([lat[-1, ::-step], lon[-1, ::-step]], -1),
        np.stack([lat[::-step, 0], lon[::-step, 0]], -1),
    ])
    ring = ring[np.isfinite(ring).all(1)]
    return Polygon(ring[:, ::-1]).buffer(0)


common = None
for name in config.scenes():
    sw = io.read_scene(name, nav=False, lst=False)
    fp = footprint(sw)
    print(name, sw.shape, f"{fp.area:.1f} deg2")
    common = fp if common is None else common.intersection(fp)
common = common.buffer(-0.05)  # stay ~5 km inside the edges
print("common area deg2", common.area)

# --- polygons --------------------------------------------------------------------
url = "https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_500k.zip"
z = zipfile.ZipFile(_io.BytesIO(requests.get(url, timeout=300).content))
tmp = config.DATA / "census"
tmp.mkdir(parents=True, exist_ok=True)
z.extractall(tmp)
counties = gpd.read_file(tmp / "cb_2023_us_county_500k.shp").to_crs(4326)
colusa = counties[(counties.STATEFP == "06") & (counties.NAME == "Colusa")].geometry.iloc[0]
assert common.contains(colusa), "Colusa County must lie inside every scene"

tr = geom.local_aeqd(*SITE)
sq = shapely.box(-1500, -1500, 1500, 1500)
circ = Point(0, 0).buffer(10_000, quad_segs=32)
inv = lambda g: shapely.transform(g, lambda xy: np.column_stack(tr.transform(xy[:, 0], xy[:, 1], direction="INVERSE")))  # noqa: E731
polys = gpd.GeoDataFrame(
    {"name": ["box_3km", "circle_10km", "colusa_county"],
     "description": ["3 km x 3 km square centred on the site",
                     "10 km radius circle centred on the site",
                     "Colusa County, CA (US Census cb_2023_us_county_500k)"]},
    geometry=[inv(sq), inv(circ), colusa], crs=4326)
polys.to_file(OUT / "polygons.geojson", driver="GeoJSON")

# --- 100 random points in the common footprint -------------------------------------
rng = np.random.default_rng(42)
minx, miny, maxx, maxy = common.bounds
pts = []
while len(pts) < 100:
    x, y = rng.uniform(minx, maxx), rng.uniform(miny, maxy)
    if common.contains(Point(x, y)):
        pts.append(Point(x, y))
gpd.GeoDataFrame({"id": np.arange(100)}, geometry=pts, crs=4326).to_file(OUT / "points100.geojson", driver="GeoJSON")
gpd.GeoDataFrame({"name": ["common_footprint"]}, geometry=[common], crs=4326).to_file(
    OUT / "common_footprint.geojson", driver="GeoJSON")
print("wrote targets to", OUT)
