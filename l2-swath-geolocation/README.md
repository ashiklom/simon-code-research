# l2-swath-geolocation

How should you pull points and polygons out of **L2 swath** products (no grid — just 2-D
lat/lon arrays), how big is a swath pixel really, and how should you read the files over a
network? Using same-day MODIS (MYD11_L2/MOD11_L2 + MOD03), VIIRS (VNP21/VJ121 + VNP03MOD) and
ECOSTRESS (ECO_L2_LSTE + ECO_L1B_GEO) land-surface-temperature granules over California's
Sacramento Valley (2023-06-02/03), plus 47 geolocation-only granules from six regions and two
epochs (2013, 2024), this experiment compared:

* **Part A — locating pixels** for one site, 100 points and three polygons: naive search,
  KD-trees, xarray `NDPointIndex` with [xoak](https://xoak.readthedocs.io/) adapters, S2, H3, and an
  **analytic inverse geolocation** from orbit + scan geometry.
* **Part B — pixel footprints and PSFs**: a spherical-Earth trigonometric footprint model, vector
  export of pixel polygons, Voronoi cells, literature PSFs, and how areal means change with the pixel
  model (real LST and a synthetic-truth test).
* **Part C — read performance** of h5py/fsspec, HDF5 ROS3, xarray, GDAL, download-then-read and
  VirtualiZarr → icechunk virtual references, locally and through a network simulator with S3
  in-region, S3 cross-region, Earthdata HTTPS (TEA redirects) and NCCS-portal-like profiles. These are
  checked against real measurements of the same granules, read from S3 in us-east-1 and through
  CloudFront.
* **Bonus — making MODIS HDF4 work as virtual Zarr**: root-causing and patching VirtualiZarr and
  kerchunk ([`patches/README.md`](patches/README.md)).

## Key results

* **Locating pixels.** Brute force costs 0.3–1.8 s *per point* (5–30 M pixels). A KD-tree on unit
  vectors builds in 1–9 s (0.4–1.7 GB) and answers in ~0.1 ms; S2/H3 sorted cell ids use the least memory.
  xarray's default `NDPointIndex` (Euclidean on degrees) returns the wrong pixel for 4–10 % of points —
  use a xoak BallTree/S2 adapter. An **analytic inverse geolocation** from each granule's orbit/attitude
  data needs no index: with constants calibrated once per platform it found the right pixel within a
  ±1 (MODIS), ±2 (VIIRS), ±3 (ECOSTRESS) pixel search window in all 53 test scenes (6 regions,
  2013 and 2024, before/after the Terra/Aqua orbit drift) when the target's height is known
  (±3/±9/±16 without terrain height). ECOSTRESS requires the ISS attitude quaternions (~7° pitch).
* **Pixel size and PSF.** Spherical-Earth trigonometry matches the files (MODIS 1 → 4.8 × 2.0 km, VIIRS
  0.78 → 1.6 km with its aggregation saw-tooth). In a synthetic-truth test (70 m ECOSTRESS LST seen
  through real MODIS/VIIRS geometry; 200 polygons × 5 scenes), schemes that share overlapping scans' ground —
  including plain Voronoi cells — cut swath-edge errors of polygon-mean LST by 30–40 %; centre-in-polygon is
  worst for small polygons; adding the PSF does not help on average. With real LST the schemes differ by up
  to 0.9 K for a 3 km square and < 0.1 K for 10 km+ polygons.
* **Reading.** For subsets, VirtualiZarr → icechunk virtual references are fastest on every simulated
  network (33 × 33 window: 0.4–0.6 s in-region, 1–4 s on HTTPS/NCCS-like links, < 1 MB moved). Library defaults
  are the main hazard (h5py on s3fs: ~0.5–0.9 GB moved for that window; xarray + h5netcdf: 1.3–2.1 GB; GDAL:
  ~900–2,200 requests); fsspec `blockcache` 8 MiB or tuned GDAL fix most of it. For whole granules,
  download-then-read wins. icechunk 2.3 does not retry transient 5xx/SlowDown on virtual chunks, and HDF5
  ROS3 cannot follow Earthdata's 303 redirects. DMR++ sidecars build references in < 2 s vs. 16–120 s
  (264 MB) for scanning the ECOSTRESS file.
* **Real S3 and CloudFront confirm the simulation.** The benchmark container is outside AWS, about
  70 ms from S3 in us-east-1.
  - The measured times rank the readers the way the simulator does: Spearman 0.97–0.98 for S3 and
    0.93–0.94 for CloudFront.
  - The times fall between the simulated in-region and cross-region profiles: a median 1.25× the
    in-region time and 0.6× the cross-region time over S3.
  - Icechunk virtual references read a VIIRS site window in 1.1 s (S3) or 0.8 s (CloudFront).
  - With no transient errors on the real links, full-granule icechunk reads also succeeded (ECOSTRESS
    in 36–47 s, against 22 s to download the file).
  - ROS3 works through CloudFront, which does not redirect.
* **MODIS HDF4 as virtual Zarr** failed with stock VirtualiZarr 2.8 / kerchunk 0.2.10 (8 distinct bugs,
  incl. byte-swapped HDF4 floats in kerchunk). Since kerchunk is in maintenance mode, the recommended fix is
  a **native HDF4 reader inside VirtualiZarr** (no kerchunk/fsspec): identical to the HDF4 C library on
  32 MODIS granules (1,324 datasets, 4,652 attributes), no regressions in VirtualiZarr's test suite, and
  6× less data transferred than the kerchunk path when building references over HTTPS. All options and
  the recommendation: [`patches/README.md`](patches/README.md).

Full write-up with methods pages and interactive explainers:
**https://ashiklom.github.io/simon-code-research/l2-swath-geolocation/**

## Reproduce

```bash
cd l2-swath-geolocation
mise install && mise run setup                       # pixi + quarto; conda-forge env (GDAL/HDF4/HDF5, ...)
export EARTHDATA_LOGIN_USER=... EARTHDATA_LOGIN_PASSWORD=...
mise run download                                    # ~7 GB into data/ (git-ignored)
mise run all                                         # all benchmarks + figures (~4 h on 4 vCPUs)
mise run site                                        # render the Quarto site from committed results
```

The MODIS virtual-Zarr results need the patched vendored libraries:
`git submodule update --init --depth 1 vendor/VirtualiZarr vendor/kerchunk`, then apply
`patches/blunt-*.diff` (the read benchmark used these) or `patches/optionD-virtualizarr-native-hdf4.diff`
(native HDF4 reader; recommended) — see [`patches/README.md`](patches/README.md).

### Requirements

An Earthdata Login account (downloads only); ~15 GB of free disk; local ports 18000–18010 for the
network simulator. Timings were measured in a 4-vCPU / 16 GB Linux container; the network
profiles are simulated (see the Part C methods page for sources and assumptions).

The real-endpoint run (`mise run readbench-real`) also needs:
- the granule copies in `s3://ycgs-use1-public/simon-code-research/l2-swath-geolocation/granules/`
  (1.18 GB, Intelligent-Tiering; served through CloudFront at `$YCGS_PUBLIC_BUCKET_URL`);
- AWS credentials for the `ycgs-all-buckets-reader` profile.

Its results describe one container, outside AWS, on 2026-11-19.

## Published granules and virtual stores

The 6 benchmark granules are copied, with their DMR++ sidecars, under
`s3://ycgs-use1-public/simon-code-research/l2-swath-geolocation/granules/` (1.18 GB). They are
served through CloudFront at `$YCGS_PUBLIC_BUCKET_URL/simon-code-research/l2-swath-geolocation/granules/`.

The **virtual Icechunk stores** that point at those CloudFront copies are under
`stores/virtual-cloudfront/<sensor>__<file>/` (434 KB in total). Anyone can open them read-only
over HTTPS, with no credentials, and read only the chunks they need:

```python
import icechunk, xarray as xr
base = "https://d3v5kb9d29awwb.cloudfront.net/simon-code-research/l2-swath-geolocation"
repo = icechunk.Repository.open(
    icechunk.http_storage(f"{base}/stores/virtual-cloudfront/viirs__VNP03MOD.A2023154.2012.002.2023155044803.nc"),
    authorize_virtual_chunk_access=icechunk.containers_credentials({f"{base}/granules/": None}))
ds = xr.open_zarr(repo.readonly_session("main").store, group="geolocation_data", consolidated=False)
ds.latitude[1500:1533, 1500:1533].values   # ~3 s from outside AWS
```

Checked with icechunk 2.3.1, the version pinned in `pixi.lock`. The `main` snapshots:

| Store | Snapshot |
|---|---|
| `ecostress__ECOv002_L1B_GEO_27837_005_20230603T202541_0711_02.h5` | `4P7F4W1QGDCRDYYPAEMG` |
| `ecostress__ECOv002_L2_LSTE_27837_005_20230603T202541_0711_03.h5` | `4B52H50D9TPH410YJFVG` |
| `modis__MYD03.A2023154.2125.061.2023155150831.hdf` | `CZHW4F8CK17X305SWWQG` |
| `modis__MYD11_L2.A2023154.2125.061.2023155175206.hdf` | `RZSZZVMP9HK1H1BX3WJ0` |
| `viirs__VNP03MOD.A2023154.2012.002.2023155044803.nc` | `KXG8YK0HNFCNP0B0HWGG` |
| `viirs__VNP21.A2023154.2012.002.2023156230312.nc` | `WCA6R1SBTRZ6075154Y0` |

The MODIS HDF4 stores were built with the patched parser (see `patches/`); reading them only
needs icechunk. The granules are NASA data (LP DAAC, LAADS), redistributed here unchanged for
the benchmark.

## Layout

`src/swathgeo/` (library: readers, analytic model, locators, footprints, PSF, network simulator),
`scripts/` (numbered pipeline steps), `config/` (scene lists, targets, PSF and network profiles),
`results/` (tables, small vector exports), `figures/`, `report/` (Quarto site), `notes/` (literature
notes), `patches/` + `vendor/` (VirtualiZarr/kerchunk fixes), `tests/`.
