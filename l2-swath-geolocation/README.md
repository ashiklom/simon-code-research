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
  in-region, S3 cross-region, Earthdata HTTPS (TEA redirects) and NCCS-portal-like profiles.
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
* **MODIS HDF4 as virtual Zarr** failed with stock VirtualiZarr 2.8 / kerchunk 0.2.10 (8 distinct bugs,
  incl. byte-swapped HDF4 floats in kerchunk). Patched, all files read bit-identically; minimal patch
  options and a recommendation are in [`patches/README.md`](patches/README.md).

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
`patches/blunt-*.diff` (see [`patches/README.md`](patches/README.md)).

### Requirements

An Earthdata Login account (downloads only); ~15 GB of free disk; local ports 18000–18010 for the
network simulator. Timings were measured in a 4-vCPU / 16 GB Linux container; the network
profiles are simulated (see the Part C methods page for sources and assumptions).

## Layout

`src/swathgeo/` (library: readers, analytic model, locators, footprints, PSF, network simulator),
`scripts/` (numbered pipeline steps), `config/` (scene lists, targets, PSF and network profiles),
`results/` (tables, small vector exports), `figures/`, `report/` (Quarto site), `notes/` (literature
notes), `patches/` + `vendor/` (VirtualiZarr/kerchunk fixes), `tests/`.
