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

<!-- KEY-RESULTS -->

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
