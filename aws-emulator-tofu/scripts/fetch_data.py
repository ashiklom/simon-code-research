"""Fetch small public COGs + Natural Earth vectors into data/ (git-ignored).

COGs are re-written as EPSG:3857 GoogleMapsCompatible COGs (DEFLATE, 256-px tiles, no predictor)
so that every internal tile at every overview is exactly one WebMercatorQuad tile. That is what
lets the pure-Python tiler serve a tile with a single S3 range read.
"""
from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"

COGS = {
    # Sentinel-2 L2A true-colour (RGB uint8) over the Nile near Aswan, 2020-07-01 (Element 84 open data).
    # A 2048x2048 window (20 km) keeps the result to a few MB.
    "s2-aswan-tci": dict(
        src="/vsicurl/https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/36/Q/WD/2020/7/S2A_36QWD_20200701_0_L2A/TCI.tif",
        srcwin=(4000, 4000, 2048, 2048),
        nodata=0, resampling="bilinear",
    ),
    # Copernicus DEM GLO-90 (float32), 1x1 degree over the Valais Alps (Copernicus open data on AWS).
    "cop90-alps-dem": dict(
        src="/vsicurl/https://copernicus-dem-90m.s3.amazonaws.com/Copernicus_DSM_COG_30_N46_00_E007_00_DEM/Copernicus_DSM_COG_30_N46_00_E007_00_DEM.tif",
        srcwin=None, nodata=-9999, resampling="bilinear",
    ),
}

VECTORS = {
    "countries": ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_admin_0_countries.geojson",
                  ["NAME", "ISO_A3", "CONTINENT", "POP_EST", "GDP_MD"]),
    "populated_places": ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_populated_places_simple.geojson",
                         ["name", "adm0name", "pop_max", "featurecla"]),
    "rivers": ("https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_110m_rivers_lake_centerlines.geojson",
               ["name", "featurecla"]),
}


def run(*args: str) -> None:
    print("+", " ".join(args))
    subprocess.run(args, check=True)


def fetch_cog(name: str, spec: dict) -> None:
    out = DATA / "cogs" / f"{name}.tif"
    if out.exists():
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".src.tif")
    args = ["gdal_translate", "-q"]
    if spec["srcwin"]:
        args += ["-srcwin", *map(str, spec["srcwin"])]
    run(*args, "-a_nodata", str(spec["nodata"]), spec["src"], str(tmp))
    run("gdal_translate", "-q", "-of", "COG",
        "-co", "TILING_SCHEME=GoogleMapsCompatible", "-co", "BLOCKSIZE=256",
        "-co", "COMPRESS=DEFLATE", "-co", "PREDICTOR=NO", "-co", f"RESAMPLING={spec['resampling']}",
        "-co", "ADD_ALPHA=NO", "-co", "OVERVIEWS=IGNORE_EXISTING",
        # Align every level (not just full res) to the tile grid -> each tile is one block read.
        "-co", "ALIGNED_LEVELS=6",
        str(tmp), str(out))
    tmp.unlink()


def fetch_vector(name: str, url: str, keep: list[str]) -> None:
    out = DATA / "vectors" / f"{name}.geojson"
    if out.exists():
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    print("+ GET", url)
    fc = json.load(urllib.request.urlopen(url))
    feats = []
    for i, f in enumerate(fc["features"], start=1):
        props = {k.lower(): f["properties"].get(k) for k in keep}
        feats.append({"type": "Feature", "id": i, "geometry": f["geometry"], "properties": props})
    out.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))


def main() -> None:
    for name, spec in COGS.items():
        fetch_cog(name, spec)
    for name, (url, keep) in VECTORS.items():
        fetch_vector(name, url, keep)
    for p in sorted([*DATA.glob("cogs/*.tif"), *DATA.glob("vectors/*.geojson")]):
        print(f"{p.relative_to(DATA)}: {p.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
