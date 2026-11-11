# Transcript

Model(s): claude-opus-5-5
Tool output, thinking, and system context are omitted; tool calls are summarized.

<!-- session cb779936-c969-5010-9e11-3af4c0652b45 -->
*Session started 2026-11-10 17:50 UTC*

## User

Experiment: l2-swath-geolocation.

Download a few representative L2 swath files from MODIS, VIIRS, and ECOSTRESS locally. Create a few subsetting targets: A single site (point); 100 site points; and a spatial polygon (all pixels that at least partially intersect the area, and the fraction of each pixel's area inside the polygon).

For each dataset and subsetting target, try the following subset methods: extract the point naively (e.g., xarray sel (method="nearest"); numpy.which; or similar); build a KD-Tree index and use to extract; build an S2 index and use to extract; same for Uber H3 index; try to estimate the pixel (or the pixel region) analytically based on information you can find about the orbit and observing geometry. Compare the performance of these methods (for index methods, measure building the index and using the index separately).

Come up with a way to capture the variability in pixel size with view geometry (i.e., pixels at swath edge are much bigger) based on trigonometry. Create a way to export pixels as vectors that approximately capture the true pixel size. Also, try to find some data on real point spread functions of these sensors (ATBD; literature; etc.). For a few representative areal averages, show the impact of naive pixel size assumptions (all pixels same size) vs. accounting for true pixel size vs. accounting for pixel size *and* incorporating point spread function. Note that MODIS, VIIRS, and ECOSTRESS have very different characteristics for these.

Also, compare several different methods for read performance --- direct read, something GDAL-powered, virtual Zarr (virtualizarr) via icechunk, and others. For these, compare performance locally; also, create mock readers that simulate performance degradations due to reading over network, with "profiles" for (1) direct S3 reads in region (higher latency; very good bandwidth); (2) direct S3 reads out-of-region (more latency); (3) HTTPS reads (e.g., similar performance characteristics to NASA Earthdata HTTPS URLs); (4) NASA GSFC NCCS Data portal (highly noisy/variable/unpredictable latency and bandwidth because of scaling issues).

## Claude

- **Bash**: `ls -la && git log --oneline | head -20 && ls _helpers && cat README.md && git branch -a`
- **Bash**: `for d in */; do echo "== $d"; ls $d; done; cat */publish.toml 2>/dev/null | head -60; which mise uv pixi gh; env | grep -i -E 'earthdata|netrc|token' | sed 's/…`
- **Bash**: `sed -n 1,80p _helpers/build_site.py; cat .gitignore; cat .github/workflows/*.yml | head -60; curl -sS "$HTTPS_PROXY/__agentproxy/status" | head -40`

Let me check network reachability to the relevant data hosts (read-only HEAD requests).

- **Bash**: `for u in https://cmr.earthdata.nasa.gov/search/collections.json?short_name=MOD021KM https://urs.earthdata.nasa.gov https://ladsweb.modaps.eosdis.nasa.gov https…`
- **Bash**: `for sn in MOD11_L2 MOD03 MOD021KM VNP21 VNP03MOD VJ121 ECO_L2_LSTE ECO_L1B_GEO ECO_L2T_LSTE; do printf "%s: " $sn; curl -sS -m 30 "https://cmr.earthdata.nasa.g…`
- **Bash**: `curl -sS -m 20 -L -o /dev/null -w "%{http_code} %{url_effective}\n" https://github.com/astral-sh/uv/releases/download/0.5.0/uv-x86_64-unknown-linux-gnu.tar.gz;…`
- **Bash**: `url=$(curl -sS -m 30 "https://cmr.earthdata.nasa.gov/search/granules.json?short_name=ECO_L2_LSTE&version=002&page_size=1&temporal=2023-07-01T00:00:00Z,2023-07-…`
- **Bash**: `for u in https://conda.anaconda.org/conda-forge/noarch/repodata.json https://prefix.dev/conda-forge/noarch/repodata.json https://ladsweb.modaps.eosdis.nasa.gov…`

*Asked:*

> **Products:** Which L2 product family should anchor the comparison? (All three sensors need a separate geolocation file for full-res lat/lon; MODIS C6.1 is HDF4, which complicates the virtual-Zarr path — that becomes a finding.)
> - *LST everywhere (Recommended)*: MOD11_L2 + MOD03 (1 km), VNP21 + VNP03MOD (750 m), ECO_L2_LSTE + ECO_L1B_GEO (70 m). Same geophysical variable across sensors, so areal averages are comparable.
> - *Geolocation + L1B radiance*: MOD021KM/MOD03, VNP02MOD/VNP03MOD, ECO_L1B_RAD/ECO_L1B_GEO. Closer to what PSFs are characterized for, but not 'L2'.
> - *Mixed L2 products*: Whatever L2 is most representative per sensor (e.g., MOD04 aerosol, VIIRS cloud props, ECOSTRESS LST). Less comparable.
>
> **Targets:** How should I choose the subsetting targets (1 point, 100 points, 1 polygon)? ECOSTRESS swaths are only ~400 km wide, so all targets must fall inside a scene where all three sensors overlap on the same day.
> - *I pick a CONUS region (Recommended)*: I choose a same-day MODIS/VIIRS/ECOSTRESS overlap over a heterogeneous US landscape: a flux-tower site as the point, 100 random points in the common footprint, and a ~30–50 km watershed/county polygon. Plus granules where the site sits near nadir and near swath edge.
> - *Real site network*: 100 real sites (e.g., AmeriFlux/NEON). They span far more than one ECOSTRESS scene, so ECOSTRESS would need many granules.
> - *I'll give you sites*: You provide the point, the 100 sites, and the polygon.
>
> **Site:** How should the experiment's Pages site be built?
> - *Quarto report (Recommended)*: Quarto installed via mise, multi-section report rendered from committed results/figures (frozen, no analysis re-run in CI).
> - *README only*: No build step; README.md with embedded figures and tables becomes the page. Simplest, but a long README.
> - *Static HTML from a Python script*: A small script turns committed results into HTML pages.
>
> **Branch:** CLAUDE.md says to work on `exp/l2-swath-geolocation` and finally fast-forward `main`, but this session was told to push only to `claude/wonderful-feynman-f097an`. Which should I do?
> - *Session branch only (Recommended)*: Commit and push to claude/wonderful-feynman-f097an; you merge to main yourself.
> - *Follow CLAUDE.md*: Use exp/l2-swath-geolocation, then rebase onto origin/main, fast-forward main and push main, and delete the branch.

## User

*Answered:*

- CLAUDE.md says to work on `exp/l2-swath-geolocation` and finally fast-forward `main`, but this session was told to push only to `claude/wonderful-feynman-f097an`. Which should I do?
  → **Follow CLAUDE.md**
- How should I choose the subsetting targets (1 point, 100 points, 1 polygon)? ECOSTRESS swaths are only ~400 km wide, so all targets must fall inside a scene where all three sensors overlap on the same day.
  → **I pick a CONUS region (Recommended)**
- How should the experiment's Pages site be built?
  → **Quarto report (Recommended)**
- Which L2 product family should anchor the comparison? (All three sensors need a separate geolocation file for full-res lat/lon; MODIS C6.1 is HDF4, which complicates the virtual-Zarr path — that becomes a finding.)
  → **LST everywhere (Recommended)**

## Claude

- **Write**: `~/.claude/plans/experiment-l2-swath-geolocation-download-iterative-wilkinson.md`
- **ToolSearch**: `select:ExitPlanMode`

<details><summary><b>Proposed plan</b></summary>

# Plan: `l2-swath-geolocation`

## Context

Extracting values from L2 *swath* products (curvilinear lat/lon, no grid) for points and
polygons is a recurring pain point. This experiment benchmarks how to (a) find the right
pixels (naive search, KD-tree, S2, H3, analytic inverse geolocation from orbit/scan geometry),
(b) represent what a pixel actually "sees" (view-angle-dependent footprint + point spread
function), and how much that matters for areal averages, and (c) read the data efficiently
(direct, GDAL, virtual Zarr/icechunk, DMR++, …) locally and under simulated network profiles.
MODIS, VIIRS and ECOSTRESS are deliberately different: whiskbroom with bow-tie overlap and
~2×5 km edge pixels (MODIS), on-board aggregation zones and bow-tie deletion (VIIRS), and a
70 m, ±25.5° ISS-mounted scanner (ECOSTRESS).

Decisions from Q&A: LST products for all sensors; I choose a CONUS same-day overlap region;
Quarto report site; follow CLAUDE.md git workflow (`exp/l2-swath-geolocation` → main).

Verified in the sandbox: Earthdata credentials (`EARTHDATA_LOGIN_USER/PASSWORD`) work for
LP DAAC and LAADS HTTPS downloads; CMR reachable; DMR++ sidecars exist (e.g. VNP21 `.nc.dmrpp`);
conda-forge and GitHub release-asset downloads work; mise is not installed yet (install via
mise.run). No real S3 in-region access → network behaviour is simulated (as requested).

## Data

| Sensor | L2 product | Geolocation | Format |
|---|---|---|---|
| MODIS Terra (+Aqua if useful) | MOD11_L2 v061 (LST, 1 km) | MOD03 v6.1 (1 km, incl. orbit pos/vel, attitude per scan) | HDF4 |
| VIIRS SNPP | VNP21 v002 (LST, 750 m M-band) | VNP03MOD v2 (incl. navigation data) | NetCDF4/HDF5 |
| ECOSTRESS | ECO_L2_LSTE v002 (70 m) | ECO_L1B_GEO v002 | HDF5 |

- `scripts/00_find_granules.py`: CMR search for a clear-sky summer day where all three overlap
  a chosen CONUS site; pick ~2 granules per sensor: site near nadir and site near swath edge
  (ECOSTRESS: whatever overlaps). Write chosen granule IDs/URLs to `config/granules.toml`
  (committed, so download is reproducible).
- `scripts/01_download.py`: earthaccess/requests with env-var credentials → `data/raw/`
  (git-ignored). Also fetch `.dmrpp` sidecars where present.
- Targets (`config/targets/`, committed, tiny): 1 flux-tower point (e.g., an AmeriFlux site in
  a heterogeneous landscape inside the overlap); 100 random points (fixed seed) inside the
  3-sensor common footprint; one ~30–50 km watershed (HUC) or county polygon (GeoJSON).

## Layout

```
l2-swath-geolocation/
  README.md PROMPT.md PLAN.md TRANSCRIPT.md publish.toml
  mise.toml            # pins pixi, quarto; tasks: download, locate, footprint, psf, readbench, site, all
  pixi.toml pixi.lock  # python + gdal(hdf4/hdf5 plugins) + pyhdf + h5py/h5netcdf + xarray + scipy
                       # + pykdtree + pys2index/s2sphere + h3 + shapely/geopandas/pyogrio + virtualizarr
                       # + icechunk + kerchunk + fsspec/aiohttp + moto[server] + earthaccess + matplotlib
  config/              # granules.toml, targets/*.geojson, net_profiles.toml, psf.toml
  src/swathgeo/        # library code (readers, locators, footprint, psf, netsim, bench utils)
  scripts/             # numbered pipeline steps calling src/
  results/             # committed small CSV/Parquet tables of timings & accuracy
  figures/             # PNGs (in git if small; else release assets)
  report/              # Quarto project (index.qmd + sections), renders results/figures only
  data/                # git-ignored raw granules + derived indexes
```

## Part A — Pixel location / subsetting benchmarks (`src/swathgeo/locate/`)

Common interface `Locator.build(lat, lon)` / `.query_points(pts)` / `.query_polygon(poly)`,
returning (row, col) indices + distance. Timed separately: load geolocation, build index,
query (1 point, 100 points, polygon). Repeated runs (timeit-style, median + IQR), memory peak.

1. **Naive**: vectorized haversine/ECEF distance argmin over full arrays (numpy); plus
   `xarray` 2-D approach (note `sel(method="nearest")` doesn't work on curvilinear coords —
   document); polygon via bbox prefilter + shapely `contains_xy` on centers.
2. **KD-tree**: scipy `cKDTree` and `pykdtree` on ECEF unit vectors (avoids dateline/pole issues).
3. **S2**: `pys2index` S2PointIndex (C++); polygon via S2 cell covering (s2sphere/`spherely`)
   then exact test.
4. **H3**: `h3` v4 — index pixel centers at resolution matched to pixel size, cell→pixel lookup
   (sorted array + searchsorted), point query with k-ring fallback; polygon via
   `polygon_to_cells` with a buffer for partial pixels.
5. **Analytic inverse geolocation**: use orbit position/velocity per scan (MOD03 `orb_pos/orb_vel`,
   VNP03 navigation data; ECOSTRESS: from L1B_GEO metadata if present, else derive a ground track
   from the nadir-most column) to (i) find the scan/line whose scan plane contains the target,
   (ii) compute scan angle satellite→target, (iii) map to sample index (MODIS linear in angle;
   VIIRS piecewise through 3:1/2:1/1:1 aggregation zones; ECOSTRESS linear), (iv) optional one-step
   local refinement using the real lat/lon of a 3×3 neighbourhood. Report accuracy vs KD-tree
   truth (exact-hit rate, pixel offset histogram, distance error) and speed (needs no index).

All methods must also report "is the point inside the swath at all" and handle MODIS bow-tie
(multiple scans covering a point → return all candidates, choose nearest center).

## Part B — Pixel footprints & PSF (`src/swathgeo/footprint.py`, `psf.py`)

- **Trigonometric footprint model** (spherical Earth, altitude h, IFOV): scan angle θ →
  Earth-central angle β = asin((R+h)/R·sinθ) − θ; along-scan size = R·IFOV·dβ/dθ, along-track
  size = slant range · IFOV_track. Sensor params in `config/psf.toml` (MODIS 705 km, ±55°,
  1 km@nadir; VIIRS 829 km with aggregation zones; ECOSTRESS ~400 km ISS altitude from metadata,
  ±25.5°). Validate against empirical spacing between neighbouring pixel centers and against
  view zenith in the geolocation files; plot size vs scan angle per sensor.
- **Vector export**: per-pixel quadrilaterals oriented along scan/track directions (from
  local Jacobian of the lat/lon grid, scaled by the model size) → GeoParquet + FlatGeobuf for
  the target subsets (small subsets committed/released; full-granule export via a task, not
  committed). Also a "naive" export (nominal square at center) for comparison.
- **PSF research** (web: ATBDs, literature): MODIS — triangular along-scan × rectangular
  along-track (Nishihama/Wolfe MOD03 ATBD; Tan et al. 2006; Campagnolo & Montaño 2014 Gaussian
  approx); VIIRS — pre-launch LSF/MTF & aggregation effects (VIIRS SDR/geolocation ATBD,
  Wolfe et al. 2013); ECOSTRESS — L1 ATBD/MTF spec. Encode as parametric 2-D PSFs in pixel
  coordinates, with citations in `config/psf.toml` and the report. Where only MTF is given,
  derive a Gaussian-equivalent and state the assumption.
- **Areal averages**: for the polygon (plus 2–3 extra representative polygons: small vs large,
  near nadir vs swath edge), compute LST means with weights from (1) naive equal-size pixels
  (center-in-polygon / nominal-square area fraction), (2) true footprint area fraction,
  (3) footprint ⊗ PSF energy fraction (numerical integration on a fine sub-pixel grid).
  Plus a **synthetic-truth test**: high-res synthetic LST field (e.g., land-cover-like
  patches), simulate each sensor's observation via PSF at real geometry, recover polygon mean
  with each weighting → error vs known truth. Figures: weight maps, bias by method/sensor/
  scan position.

## Part C — Read performance (`src/swathgeo/readers/`, `netsim/`)

Read tasks: (1) full LST + lat/lon arrays, (2) point extraction (geolocation + single pixel),
(3) polygon window. Readers:
- direct: `pyhdf` (HDF4) / `h5py` (HDF5/NetCDF4); `xarray` + `h5netcdf`/`netCDF4`
- GDAL: `osgeo.gdal` HDF4/HDF5 drivers, `/vsicurl/` and `/vsis3/` for remote (with tuned
  `GDAL_*` cache/merge options as a variant)
- fsspec + h5py (HTTP/S3) with block-cache variants (none/readahead/blockcache, block sizes)
- VirtualiZarr → icechunk (virtual refs to original files), read via xarray/zarr; HDF4 via
  kerchunk HDF4 or DMR++ parser if possible — failure documented as a result if not
- DMR++ sidecar → VirtualiZarr (no file-scan needed), kerchunk JSON refs as baseline
- (optional) earthaccess `open()` style for parity with common user code

**Network simulator** (`netsim`): local `moto` S3 server holding the granules + a Python
asyncio reverse proxy that injects per-request latency (TTFB), connection setup cost,
per-connection and aggregate bandwidth caps, jitter, stalls, and 5xx errors, serving both S3
API and plain HTTP Range requests — so GDAL, fsspec, h5py and icechunk all do *real* network
I/O. Profiles in `config/net_profiles.toml` (values justified from published AWS/Earthdata
measurements where findable; otherwise stated assumptions):
1. `s3-in-region`: ~20–40 ms TTFB, ~80–100 MB/s per connection
2. `s3-cross-region`: ~80–150 ms TTFB, ~20–50 MB/s
3. `earthdata-https`: extra redirect round-trips on first request (URS → CloudFront → signed
   S3), ~100–300 ms TTFB, ~10–30 MB/s
4. `nccs-portal`: heavy-tailed latency (lognormal, p99 multi-second), random bandwidth
   1–50 MB/s, occasional stalls and ~1–2% 5xx needing retries
Metrics per run: wall time, # requests, bytes transferred (from proxy logs); repeated runs,
distributions shown (especially for nccs). Also report the raw local baseline.

## Report & publishing

- Quarto project in `report/` (pinned via mise), rendering only committed `results/` tables
  and `figures/` (no code execution in CI; `execute: enabled: false` or pre-rendered
  matplotlib PNGs). `publish.toml`: `build = "mise run site"`, `output = "report/_site"`.
- README: question, headline results, `mise run all`, Pages link. Root README line added.
- Release `l2-swath-geolocation`: only if figures/vector exports are too large for git —
  **I'll ask before creating/uploading, listing files and sizes.**
- PROMPT.md (verbatim prompt + my Q&A), PLAN.md (this plan), TRANSCRIPT.md via
  `uv run _helpers/transcript.py -o l2-swath-geolocation/TRANSCRIPT.md` at the end.

## Git

Branch `exp/l2-swath-geolocation`; commits per logical step prefixed
`l2-swath-geolocation: `; PROMPT.md/PLAN.md in their own commits; push regularly. At the end:
fetch, rebase onto `origin/main`, fast-forward and push `main`, delete branch locally and on
origin.

## Verification

- Unit-ish checks (`pytest` in `tests/`): footprint model reproduces MODIS ~2×4.8 km and VIIRS
  ~1.6 km edge sizes; all locators agree with brute force on the 100 points (excluding
  documented analytic misses); weights sum to ~1 and footprint/PSF integrals are normalized;
  netsim proxy delivers configured latency/bandwidth within tolerance (self-test).
- `mise run all` end-to-end from downloaded data produces `results/` + `figures/`.
- `uv run _helpers/build_site.py --only l2-swath-geolocation --skip-assets` builds; inspect
  `_site/l2-swath-geolocation/index.html` (Playwright screenshot for a quick visual check).

</details>

- **Edit**: `~/.claude/plans/experiment-l2-swath-geolocation-download-iterative-wilkinson.md`
- **Edit**: `~/.claude/plans/experiment-l2-swath-geolocation-download-iterative-wilkinson.md`
- **Edit**: `~/.claude/plans/experiment-l2-swath-geolocation-download-iterative-wilkinson.md`
- **Edit**: `~/.claude/plans/experiment-l2-swath-geolocation-download-iterative-wilkinson.md`
- **Edit**: `~/.claude/plans/experiment-l2-swath-geolocation-download-iterative-wilkinson.md`
- **Edit**: `~/.claude/plans/experiment-l2-swath-geolocation-download-iterative-wilkinson.md`
- **Edit**: `~/.claude/plans/experiment-l2-swath-geolocation-download-iterative-wilkinson.md`
- **Edit**: `~/.claude/plans/experiment-l2-swath-geolocation-download-iterative-wilkinson.md`
- **Edit**: `~/.claude/plans/experiment-l2-swath-geolocation-download-iterative-wilkinson.md`

<details><summary><b>Proposed plan</b></summary>

# Plan: `l2-swath-geolocation`

## Context

Extracting values from L2 *swath* products (curvilinear lat/lon, no grid) for points and
polygons is a recurring pain point. This experiment benchmarks how to (a) find the right
pixels (naive search, KD-tree, S2, H3, analytic inverse geolocation from orbit/scan geometry),
(b) represent what a pixel actually "sees" (view-angle-dependent footprint + point spread
function), and how much that matters for areal averages, and (c) read the data efficiently
(direct, GDAL, virtual Zarr/icechunk, DMR++, …) locally and under simulated network profiles.
MODIS, VIIRS and ECOSTRESS are deliberately different: whiskbroom with bow-tie overlap and
~2×5 km edge pixels (MODIS), on-board aggregation zones and bow-tie deletion (VIIRS), and a
70 m, ±25.5° ISS-mounted scanner (ECOSTRESS).

Decisions from Q&A: LST products for all sensors; I choose a CONUS same-day overlap region;
Quarto report site; follow CLAUDE.md git workflow (`exp/l2-swath-geolocation` → main).

Verified in the sandbox: Earthdata credentials (`EARTHDATA_LOGIN_USER/PASSWORD`) work for
LP DAAC and LAADS HTTPS downloads; CMR reachable; DMR++ sidecars exist (e.g. VNP21 `.nc.dmrpp`);
conda-forge and GitHub release-asset downloads work; mise is not installed yet (install via
mise.run). No real S3 in-region access → network behaviour is simulated (as requested).

## Data

| Sensor | L2 product | Geolocation | Format |
|---|---|---|---|
| MODIS Terra (+Aqua if useful) | MOD11_L2 v061 (LST, 1 km) | MOD03 v6.1 (1 km, incl. orbit pos/vel, attitude per scan) | HDF4 |
| VIIRS SNPP | VNP21 v002 (LST, 750 m M-band) | VNP03MOD v2 (incl. navigation data) | NetCDF4/HDF5 |
| ECOSTRESS | ECO_L2_LSTE v002 (70 m) | ECO_L1B_GEO v002 | HDF5 |

- `scripts/00_find_granules.py`: CMR search for a clear-sky summer day where all three overlap
  a chosen CONUS site; pick ~2 granules per sensor: site near nadir and site near swath edge
  (ECOSTRESS: whatever overlaps). Write chosen granule IDs/URLs to `config/granules.toml`
  (committed, so download is reproducible).
- `scripts/01_download.py`: earthaccess/requests with env-var credentials → `data/raw/`
  (git-ignored). Also fetch `.dmrpp` sidecars where present.
- Targets (`config/targets/`, committed, tiny): 1 flux-tower point (e.g., an AmeriFlux site in
  a heterogeneous landscape inside the overlap); 100 random points (fixed seed) inside the
  3-sensor common footprint; one ~30–50 km watershed (HUC) or county polygon (GeoJSON).

## Layout

```
l2-swath-geolocation/
  README.md PROMPT.md PLAN.md TRANSCRIPT.md publish.toml
  mise.toml            # pins pixi, quarto; tasks: download, locate, footprint, psf, readbench, site, all
  pixi.toml pixi.lock  # python + gdal(hdf4/hdf5 plugins) + pyhdf + h5py/h5netcdf + xarray + scipy
                       # + pykdtree + xoak + scikit-learn + pys2index/s2sphere + h3 + shapely/geopandas/pyogrio + virtualizarr
                       # + icechunk + kerchunk + fsspec/aiohttp + moto[server] + earthaccess + matplotlib
  config/              # granules.toml, targets/*.geojson, net_profiles.toml, psf.toml
  src/swathgeo/        # library code (readers, locators, footprint, psf, netsim, bench utils)
  scripts/             # numbered pipeline steps calling src/
  results/             # committed small CSV/Parquet tables of timings & accuracy
  figures/             # PNGs (in git if small; else release assets)
  report/              # Quarto project (index.qmd + sections), renders results/figures only
  data/                # git-ignored raw granules + derived indexes
```

## Part A — Pixel location / subsetting benchmarks (`src/swathgeo/locate/`)

Common interface `Locator.build(lat, lon)` / `.query_points(pts)` / `.query_polygon(poly)`,
returning (row, col) indices + distance. Timed separately: load geolocation, build index,
query (1 point, 100 points, polygon). Repeated runs (timeit-style, median + IQR), memory peak.

1. **Naive**: vectorized haversine/ECEF distance argmin over full arrays (numpy); plus
   `xarray` 2-D approach (note `sel(method="nearest")` doesn't work on curvilinear coords with
   default indexes — document); polygon via bbox prefilter + shapely `contains_xy` on centers.
2. **KD-tree**: scipy `cKDTree` and `pykdtree` on ECEF unit vectors (avoids dateline/pole issues).
2b. **xarray-native indexes**: [xoak](https://xoak.readthedocs.io/) (`ds.xoak.set_index` /
   `ds.xoak.sel`) with each of its backends (scipy KD-tree, sklearn BallTree/haversine,
   pys2index S2), plus xarray's built-in `NDPointIndex` (custom-index API that enables
   `sel(method="nearest")` on 2-D coords) if available in the pinned xarray. Evaluate both
   **performance** (build/query, same harness) and **usability**: lines of code, API
   ergonomics, dask/lazy support, polygon support (or lack thereof), handling of out-of-swath
   points, maintenance status/compatibility with current xarray. Summarised as a table.
3. **S2**: `pys2index` S2PointIndex (C++); polygon via S2 cell covering (s2sphere/`spherely`)
   then exact test.
4. **H3**: `h3` v4 — index pixel centers at resolution matched to pixel size, cell→pixel lookup
   (sorted array + searchsorted), point query with k-ring fallback; polygon via
   `polygon_to_cells` with a buffer for partial pixels.
5. **Analytic inverse geolocation**: use orbit position/velocity per scan (MOD03 `orb_pos/orb_vel`,
   VNP03 navigation data; ECOSTRESS: from L1B_GEO metadata if present, else derive a ground track
   from the nadir-most column) to (i) find the scan/line whose scan plane contains the target,
   (ii) compute scan angle satellite→target, (iii) map to sample index (MODIS linear in angle;
   VIIRS piecewise through 3:1/2:1/1:1 aggregation zones; ECOSTRESS linear), (iv) local
   refinement using the real lat/lon in a k×k window around the analytic guess. Report accuracy
   vs KD-tree truth (exact-hit rate, row/col offset distribution, distance error) and speed
   (needs no index; reads only a small window of geolocation).
   - **Neighbourhood size**: not fixed at 3×3. From the analytic-vs-truth offset distribution,
     choose the smallest window that contains the true pixel with ~100% (report p99/p99.9/max
     offsets) — i.e. the largest error we can *reliably* bound — separately for rows/cols and
     per sensor; report the read-cost/accuracy trade-off vs window size.
   - **Consistency across scenes**: a separate geolocation-only scene set (just MOD03 /
     VNP03MOD / ECO_L1B_GEO, no L2) spanning very different locations (tropics, mid-lat N & S,
     high latitude, near-dateline), ascending/descending orbits, and epochs: MODIS Terra & Aqua
     ~2012–2015 vs 2023–2025 (post-constellation-exit orbit drift: lower altitude, shifted
     equator-crossing time), VIIRS SNPP vs NOAA-20, ECOSTRESS across ISS altitude changes
     (reboosts). Show whether a single parameter set (altitude, IFOV, scan rate) works or
     per-granule parameters from the orbit vectors are required, and how window size must grow.

All methods must also report "is the point inside the swath at all" and handle MODIS bow-tie
(multiple scans covering a point → return all candidates, choose nearest center).

## Part B — Pixel footprints & PSF (`src/swathgeo/footprint.py`, `psf.py`)

- **Trigonometric footprint model** (spherical Earth, altitude h, IFOV): scan angle θ →
  Earth-central angle β = asin((R+h)/R·sinθ) − θ; along-scan size = R·IFOV·dβ/dθ, along-track
  size = slant range · IFOV_track. Sensor params in `config/psf.toml` (MODIS 705 km, ±55°,
  1 km@nadir; VIIRS 829 km with aggregation zones; ECOSTRESS ~400 km ISS altitude from metadata,
  ±25.5°). Validate against empirical spacing between neighbouring pixel centers and against
  view zenith in the geolocation files; plot size vs scan angle per sensor.
- **Voronoi tessellation** (relevant: it is exactly the partition implied by nearest-neighbour
  extraction): spherical Voronoi (`scipy.spatial.SphericalVoronoi`, or planar Voronoi in a
  local equal-area projection for speed) of pixel centers for the target subsets. Compare
  Voronoi cell area/shape vs the trig footprint model: they agree away from edges, but Voronoi
  cells are non-overlapping, so in MODIS bow-tie overlap regions they shrink/fragment while the
  true footprints overlap, and they ignore the PSF. Voronoi is also used as an extra weighting
  scheme in the areal-average comparison and as a vector export option.
- **Vector export**: per-pixel quadrilaterals oriented along scan/track directions (from
  local Jacobian of the lat/lon grid, scaled by the model size) → GeoParquet + FlatGeobuf for
  the target subsets (small subsets committed/released; full-granule export via a task, not
  committed). Also a "naive" export (nominal square at center) for comparison.
- **PSF research** (web: ATBDs, literature): MODIS — triangular along-scan × rectangular
  along-track (Nishihama/Wolfe MOD03 ATBD; Tan et al. 2006; Campagnolo & Montaño 2014 Gaussian
  approx); VIIRS — pre-launch LSF/MTF & aggregation effects (VIIRS SDR/geolocation ATBD,
  Wolfe et al. 2013); ECOSTRESS — L1 ATBD/MTF spec. Encode as parametric 2-D PSFs in pixel
  coordinates, with citations in `config/psf.toml` and the report. Where only MTF is given,
  derive a Gaussian-equivalent and state the assumption.
- **Areal averages**: for the polygon (plus 2–3 extra representative polygons: small vs large,
  near nadir vs swath edge), compute LST means with weights from (1) naive equal-size pixels
  (center-in-polygon / nominal-square area fraction), (1b) Voronoi-cell area fraction, (2) true footprint area fraction,
  (3) footprint ⊗ PSF energy fraction (numerical integration on a fine sub-pixel grid).
  Plus a **synthetic-truth test**: high-res synthetic LST field (e.g., land-cover-like
  patches), simulate each sensor's observation via PSF at real geometry, recover polygon mean
  with each weighting → error vs known truth. Figures: weight maps, bias by method/sensor/
  scan position.

## Part C — Read performance (`src/swathgeo/readers/`, `netsim/`)

Read tasks: (1) full LST + lat/lon arrays, (2) point extraction (geolocation + single pixel),
(3) polygon window. Readers:
- direct: `pyhdf` (HDF4) / `h5py` (HDF5/NetCDF4); `xarray` + `h5netcdf`/`netCDF4`
- GDAL: `osgeo.gdal` HDF4/HDF5 drivers, `/vsicurl/` and `/vsis3/` for remote (with tuned
  `GDAL_*` cache/merge options as a variant)
- fsspec + h5py (HTTP/S3) with block-cache variants (none/readahead/blockcache, block sizes)
- VirtualiZarr → icechunk (virtual refs to original files), read via xarray/zarr; HDF4 via
  kerchunk HDF4 or DMR++ parser if possible — failure documented as a result if not
- DMR++ sidecar → VirtualiZarr (no file-scan needed), kerchunk JSON refs as baseline
- (optional) earthaccess `open()` style for parity with common user code

**Network simulator** (`netsim`): local `moto` S3 server holding the granules + a Python
asyncio reverse proxy that injects per-request latency (TTFB), connection setup cost,
per-connection and aggregate bandwidth caps, jitter, stalls, and 5xx errors, serving both S3
API and plain HTTP Range requests — so GDAL, fsspec, h5py and icechunk all do *real* network
I/O. Profiles in `config/net_profiles.toml` (values justified from published AWS/Earthdata
measurements where findable; otherwise stated assumptions):
1. `s3-in-region`: ~20–40 ms TTFB, ~80–100 MB/s per connection
2. `s3-cross-region`: ~80–150 ms TTFB, ~20–50 MB/s
3. `earthdata-https`: extra redirect round-trips on first request (URS → CloudFront → signed
   S3), ~100–300 ms TTFB, ~10–30 MB/s
4. `nccs-portal`: heavy-tailed latency (lognormal, p99 multi-second), random bandwidth
   1–50 MB/s, occasional stalls and ~1–2% 5xx needing retries
Metrics per run: wall time, # requests, bytes transferred (from proxy logs); repeated runs,
distributions shown (especially for nccs). Also report the raw local baseline.

## Report & publishing

- Quarto website in `report/` (pinned via mise), rendering only committed `results/` tables
  and `figures/` (no Python execution in CI; pre-rendered matplotlib PNGs).
  `publish.toml`: `build = "mise run site"`, `output = "report/_site"`.
- Pages: overview/results (`index.qmd`) + for **each part a results page and a dedicated
  methods page** describing the method in detail (equations, sensor parameters, citations).
  Methods pages carry client-side interactive explainers using Quarto's built-in Observable JS
  (runs in the browser; nothing to execute in CI; small JSON/CSV inputs only), e.g.:
  - Locate: toy swath where you click a target and step through naive / KD-tree / S2 / H3 /
    analytic search (cells visited, candidates); H3/S2 resolution slider vs pixel size.
  - Footprint: sliders for altitude, IFOV, scan angle → footprint size/shape (spherical trig),
    MODIS bow-tie overlap and VIIRS aggregation-zone visualisation; Voronoi vs true footprint
    toggle on a real subset (Leaflet/Observable Plot map of exported pixel polygons).
  - PSF: PSF shape explorer per sensor (triangular×rect, Gaussian, MTF-derived) and a
    polygon-weight demo showing naive vs footprint vs PSF weights and the resulting mean.
  - Read/network: profile simulator — sliders for latency, bandwidth, jitter, concurrency →
    predicted read time per reader, driven by the measured request counts/bytes logs, shown
    next to the actual measured distributions.
- README: question, headline results, `mise run all`, Pages link. Root README line added.
- Release `l2-swath-geolocation`: only if figures/vector exports are too large for git —
  **I'll ask before creating/uploading, listing files and sizes.**
- PROMPT.md (verbatim prompt + my Q&A), PLAN.md (this plan), TRANSCRIPT.md via
  `uv run _helpers/transcript.py -o l2-swath-geolocation/TRANSCRIPT.md` at the end.

## Git

Branch `exp/l2-swath-geolocation`; commits per logical step prefixed
`l2-swath-geolocation: `; PROMPT.md/PLAN.md in their own commits; push regularly. At the end:
fetch, rebase onto `origin/main`, fast-forward and push `main`, delete branch locally and on
origin.

## Verification

- Unit-ish checks (`pytest` in `tests/`): footprint model reproduces MODIS ~2×4.8 km and VIIRS
  ~1.6 km edge sizes; Voronoi cell areas match model areas away from bow-tie/edges; all
  locators (incl. xoak backends) agree with brute force on the 100 points (excluding
  documented analytic misses); weights sum to ~1 and footprint/PSF integrals are normalized;
  netsim proxy delivers configured latency/bandwidth within tolerance (self-test).
- `mise run all` end-to-end from downloaded data produces `results/` + `figures/`.
- `uv run _helpers/build_site.py --only l2-swath-geolocation --skip-assets` builds; inspect
  `_site/l2-swath-geolocation/index.html` (Playwright screenshots of each methods page and a
  scripted slider interaction to confirm the OJS widgets run without console errors).

</details>

- **ToolSearch**: `select:TaskCreate,TaskUpdate,TaskList`
- **TaskCreate**: `{"subject": "Setup: branch, PROMPT.md, PLAN.md, env (mise/pixi)", "description": "Create exp branch, record prompt/plan, install mise+pixi, pixi env with all d…`
- **TaskCreate**: `{"subject": "Data: find granules, targets, download", "description": "CMR search for overlap day, targets, download L2+geo, geo-only scene set."}`
- **TaskCreate**: `{"subject": "Part A: locators benchmark (naive, kdtree, xoak, S2, H3, analytic)", "description": "Implement and benchmark, analytic neighbourhood + cross-scene…`
- **TaskCreate**: `{"subject": "Part B: footprints, Voronoi, PSF, areal averages", "description": "Trig model, vector export, PSF research, weights, synthetic truth."}`
- **TaskCreate**: `{"subject": "Part C: read benchmarks + netsim", "description": "Readers, virtualizarr/icechunk, DMR++, network simulator with 4 profiles."}`
- **TaskCreate**: `{"subject": "Report: Quarto site with methods pages + OJS widgets; README; publish", "description": "Quarto site, README, root README, transcript, merge to mai…`
- **TaskUpdate**: `{"taskId": "1", "status": "in_progress"}`
- **Bash**: `git checkout -b exp/l2-swath-geolocation && mkdir -p l2-swath-geolocation && cp ~/.claude/plans/experiment-l2-swath-geolocation-download-iterative-wilkinso…`
- **Write**: `l2-swath-geolocation/PROMPT.md`
- **Bash**: `git add l2-swath-geolocation/PROMPT.md && git commit -q -m "l2-swath-geolocation: add PROMPT.md Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com> Claude-…`

Pushed the branch with PROMPT.md and PLAN.md. Now installing mise/pixi and building the environment.

- **Bash**: `cd /tmp && curl -sS https://mise.run | sh 2>&1 | tail -3; ls ~/.local/bin; ~/.local/bin/mise --version`
- **Bash**: `cd /home/user/simon-code-research/l2-swath-geolocation && cat > mise.toml <<'EOF' [tools] pixi = "0.59.0" quarto = "1.8.25" EOF ~/.local/bin/mise trust -q . ; …`
- **Bash**: `~/.local/bin/mise ls-remote pixi 2>&1 | tail -3; ~/.local/bin/mise ls-remote aqua:quarto-dev/quarto-cli 2>&1 | tail -5`
- **Bash**: `~/.local/bin/mise ls-remote aqua:quarto-dev/quarto-cli 2>&1 | grep -v -E '(pre|rc)' | tail -12 | tr '\n' ' '; cat > mise.toml <<'EOF' [tools] pixi = "0.84.1" "…`
- **Bash**: `cat > pixi.toml <<'EOF' [workspace] name = "l2-swath-geolocation" channels = ["conda-forge"] platforms = ["linux-64"] [dependencies] python = "3.12.*" # I/O gd…`
- **Bash**: `~/.local/bin/mise exec -- pixi run python -c " import importlib for m in ['osgeo.gdal','pyhdf','h5py','xarray','zarr','virtualizarr','icechunk','kerchunk','obs…`

Environment works (GDAL with HDF4/HDF5, virtualizarr, icechunk, xoak, S2, H3 all import). Committing the env, then searching for granules.

- **Bash**: `cat > .gitignore <<'EOF' .pixi/ data/ report/_site/ report/.quarto/ _site/ __pycache__/ *.egg-info/ .pytest_cache/ EOF cat >> mise.toml <<'EOF' [tasks.setup] d…`
- **TaskUpdate**: `{"taskId": "1", "status": "completed"}`
- **TaskUpdate**: `{"taskId": "2", "status": "in_progress"}`
- **Bash**: `mkdir -p /tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad && cd /tmp/claude-0/-home-user-simon-code-research/cb7799…`
- **Bash**: `for d in 2023-06-03 2023-06-19 2023-07-31 2023-08-03; do for sn in MYD11_L2 MOD11_L2 VNP21 VJ121; do printf "$d $sn: "; curl -sS -m 60 "https://cmr.earthdata.n…`
- **Bash**: `for sn in ECO_L1B_GEO ECO_L2_LSTE MYD03 MYD11_L2 VNP03MOD VNP21 MOD03; do printf "$sn: "; curl -sS -m 60 "https://cmr.earthdata.nasa.gov/search/granules.json?s…`
- **Bash**: `mkdir -p /home/user/simon-code-research/l2-swath-geolocation/{config/targets,scripts,results,figures,report,tests} && cat > /home/user/simon-code-research/l2-s…`

Wrote the Earthdata download helper; now downloading candidate granules for 2023‑06‑03 (Tonzi Ranch, CA) to inspect their structure.

- **Bash**: `cd /home/user/simon-code-research/l2-swath-geolocation && cat > /tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad/dl…`
- **Bash**: `rm data/raw/ecostress/ECOv002_L1B_GEO_27837_005_20230603T202541_0710_01.h5 && ~/.local/bin/mise exec -- pixi run python - <<'EOF' import h5py from pyhdf.SD imp…`
- **Bash**: `for sn in ECO_L1B_ATT ECO_L1A_ATT ECO1BATT ECO_L1A_RAW_ATT ECO_L1B_RAD; do printf "$sn: "; curl -sS -m 30 "https://cmr.earthdata.nasa.gov/search/collections.js…`
- **Bash**: `~/.local/bin/mise exec -- pixi run python - <<'EOF' from pathlib import Path from swathgeo import earthdata as ed es=ed.search("ECO_L1B_ATT","002",temporal=("2…`
- **Bash**: `rm -f data/raw/ecostress/ECOv002_L1B_ATT_27836* data/raw/ecostress/ECOv002_L1B_ATT_27837_20230603T201243_0710_01.h5 && cat >> pixi.toml.tmp <<'EOF' EOF rm pixi…`
- **Bash**: `~/.local/bin/mise exec -- pixi run python - <<'EOF' import h5py, glob from pyhdf.SD import SD sd=SD(glob.glob("data/raw/modis/MYD11_L2*2120*")[0]); print(sd.se…`

Inspected file layouts (orbit vectors available for all three; ECOSTRESS via its ATT product). Now writing the core readers module.

- **Write**: `l2-swath-geolocation/src/swathgeo/io.py`
- **Bash**: `cat > /tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad/site.py <<'EOF' import numpy as np, glob, time from swathgeo…`
- **Bash**: `~/.local/bin/mise exec -- pixi run python - <<'EOF' import numpy as np, glob from swathgeo import io sw=io.read_swath(glob.glob("data/raw/ecostress/*GEO*")[0],…`
- **Bash**: `~/.local/bin/mise exec -- pixi run python - <<'EOF' import numpy as np, shapely from shapely.geometry import Point, Polygon from swathgeo import earthdata as e…`
- **Bash**: `~/.local/bin/mise exec -- pixi run python - <<'EOF' from swathgeo import earthdata as ed es=ed.search("ECO_L2_LSTE","002",point=(-121.6531,38.1087),temporal=("…`
- **Bash**: `curl -sS -m 30 -o /dev/null -w "%{http_code} %{size_download}\n" -r 0-100 https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_county_20m.zip; curl -sS -m…`
- **Bash**: `~/.local/bin/mise exec -- pixi run python - <<'EOF' from pathlib import Path from swathgeo import earthdata as ed pt=(-122.164,39.4275); t=("2023-06-03T15:00:0…`
- **Bash**: `curl -sS -m 30 "https://cmr.earthdata.nasa.gov/search/collections.json?short_name=VJ103MOD" | python3 -c "import sys,json;print([(x['version_id'],x['data_cente…`
- **Bash**: `~/.local/bin/mise exec -- pixi run python - <<'EOF' from pathlib import Path import numpy as np from swathgeo import earthdata as ed, io pt=(-122.164,39.4275) …`
- **Bash**: `rm -rf data/raw/modis_cand && ~/.local/bin/mise exec -- pixi run python - <<'EOF' from swathgeo import earthdata as ed pt=(-122.164,39.4275) for sn,v,t in [("M…`

Now writing the scene config and the download script.

- **Bash**: `cat > config/granules.toml <<'EOF' # Main scene set: 2023-06-03 (DOY 154), Sacramento Valley, California. # Chosen because a near-cloud-free daytime ECOSTRESS …`
- **Bash**: `sed -i 's/ return f"FAIL {url} ({e.__class__.__name__}: {e})"/ if url.endswith(".dmrpp"):\n return f"-- no DMR++ sidecar: {url.rsplit(\x27\/\x27, 1)[-1]}"\n re…`
- **Bash**: `cat >> src/swathgeo/io.py <<'EOF' def stack(swaths: list[Swath]) -> Swath: """Concatenate consecutive granules along-track (MODIS/VIIRS).""" if len(swaths) == …`
- **Bash**: `python3 - <<'EOF' p='scripts/02_targets.py'; s=open(p).read() s=s.replace('inv = lambda g: shapely.ops.transform(lambda x, y: tr.transform(x, y, direction="INV…`
- **Bash**: `cat > scripts/00_select_geo_scenes.py <<'EOF' """Select the geolocation-only scene set for the analytic-locator consistency test. Diverse locations (equatorial…`
- **Bash**: `python3 - <<'EOF' p='scripts/00_select_geo_scenes.py'; s=open(p).read() s=s.replace(''' es = ed.search(sn, ver, point=(lon, lat), temporal=(f"{epoch}-01T00:00:…`
- **Bash**: `~/.local/bin/mise exec -- pixi run python scripts/01_download.py > data/download.log 2>&1`
- **Bash**: `git add -A . && git commit -q -m "l2-swath-geolocation: data selection, download, readers and targets Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com> C…`
- **TaskUpdate**: `{"taskId": "2", "status": "completed"}`
- **TaskUpdate**: `{"taskId": "3", "status": "in_progress"}`
- **Bash**: `~/.local/bin/mise exec -- pixi search h3ronpy 2>&1 | head -5; ~/.local/bin/mise exec -- pixi search s2geometry 2>&1 | head -5; ~/.local/bin/mise exec -- pixi r…`
- **Bash**: `sed -i 's/^h3-py = ">=4"/h3-py = ">=4"\nh3ronpy = "*"\ns2geometry = "*"/' pixi.toml && timeout 600 ~/.local/bin/mise exec -- pixi install 2>&1 | tail -3; ~/.lo…`
- **Bash**: `sed -i '/^s2geometry = /d' pixi.toml && timeout 600 ~/.local/bin/mise exec -- pixi install 2>&1 | tail -1; ~/.local/bin/mise exec -- pixi run python -c " impor…`

Now the analytic inverse-geolocation model — first probing the frame conventions (instrument axes, scan direction, timing) in the real files.

- **Bash**: `~/.local/bin/mise exec -- pixi run python - <<'EOF' import numpy as np, glob from swathgeo import io, geom sw=io.read_geo(glob.glob("data/raw/modis/MYD03*2125*…`
- **Bash**: `grep -c "^ok" data/download.log; grep FAIL data/download.log | head; du -sh data/raw/geo_only/*`

All 75 geolocation-only files downloaded (5.2 GB). Writing the analytic locator module.

- **Write**: `l2-swath-geolocation/src/swathgeo/analytic.py`
- **Bash**: `sed -i 's/ S = nav.interp(ks, model.kappa \* theta \* (-model.s))/ S = nav.interp(ks, model.s * model.kappa * theta)/' src/swathgeo/analytic.py && cat > /tmp/c…`
- **Bash**: `python3 - <<'EOF' p='src/swathgeo/io.py'; s=open(p).read() s=s.replace(""" lst: np.ndarray | None = None l2_path""",""" lst: np.ndarray | None = None height: n…`
- **Bash**: `~/.local/bin/mise exec -- pixi run python - <<'EOF' import numpy as np from swathgeo import io, analytic as an, geom sw=io.read_scene('ecostress', lst=False) m…`
- **Bash**: `~/.local/bin/mise exec -- pixi run python - <<'EOF' import numpy as np, h5py, glob from astropy import units as u from astropy.coordinates import GCRS, ITRS, C…`
- **Bash**: `python3 - <<'EOF' p='src/swathgeo/io.py'; s=open(p).read() s=s.replace(""" t_inst2ecr: np.ndarray | None = None # (n, 3, 3) MODIS only """,""" t_inst2ecr: np.n…`
- **Bash**: `cat > /tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad/an2.py <<'EOF' import numpy as np, sys from swathgeo import …`
- **Read**: `l2-swath-geolocation/src/swathgeo/analytic.py`

Rewriting the predict/refine/calibrate section to be scan-aware.

- **Bash**: `python3 - <<'EOF' p='src/swathgeo/analytic.py'; s=open(p).read() i=s.index('def predict(sw, lat, lon') s=s[:i]+'''def scan_angles(T, ks, model: SensorModel, na…`
- **Bash**: `~/.local/bin/mise exec -- pixi run python - <<'EOF' import numpy as np from swathgeo import io, analytic as an, geom sw=io.read_scene('ecostress', lst=False) m…`

The fit now matches ECOSTRESS to ~0.1 line / 0.5 sample, but via a degenerate parameter (roll trades off with the scan‑centre sample). Fixing roll and re‑checking robustness.

- **Bash**: `python3 - <<'EOF' p='src/swathgeo/analytic.py'; s=open(p).read() s=s.replace(''' def make(p): return replace(base, j_c=p[0], alpha=abs(p[1]) * 1e-3, phi0=p[2] …`

The "degenerate" roll was actually absorbing a constant time offset: ECOSTRESS's scan reference time isn't the Earth‑view centre. Adding an explicit scan‑time offset parameter.

- **Bash**: `python3 - <<'EOF' p='src/swathgeo/analytic.py'; s=open(p).read() s=s.replace(''' kappa: float # s per rad of scan angle (time offset of a sample relative to sc…`
- **Bash**: `git add -A . && git commit -q -m "l2-swath-geolocation: analytic inverse geolocation model (orbit + scan geometry) Co-Authored-By: Claude Opus 5.5 <noreply@ant…`

Now the index-based locators (naive, KD-tree, xarray/xoak, S2, H3) in one module with a common interface.

- **Write**: `l2-swath-geolocation/src/swathgeo/locate.py`
- **Bash**: `cat > /tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad/loc1.py <<'EOF' import numpy as np, time, sys, geopandas as …`
- **Bash**: `python3 - <<'EOF' p='src/swathgeo/locate.py'; s=open(p).read() s=s.replace(''' def uv2st(t): return np.where(t >= 0, 0.5 * np.sqrt(1 + 3 * t), 1 - 0.5 * np.sqr…`

Now the cross-scene consistency experiment for the analytic model (calibrate per platform on one reference scene, test on all others across years/locations).

- **Write**: `l2-swath-geolocation/scripts/11_analytic_consistency.py`
- **Bash**: `~/.local/bin/mise exec -- pixi run python scripts/11_analytic_consistency.py > data/consistency.log 2>&1`

While the consistency run goes, writing the locator benchmark harness (each locator in a fresh subprocess for clean timing/memory).

- **Write**: `l2-swath-geolocation/scripts/10_bench_locate.py`
- **Bash**: `cat data/consistency.log | cut -c1-400`
- **Agent**: Research sensor PSFs and IFOVs (general-purpose)
- **Agent**: Research network latency profiles (general-purpose)

Writing the footprint module (trigonometric pixel size, oriented quadrilaterals, Voronoi cells) and the PSF/weighting machinery.

- **Write**: `l2-swath-geolocation/src/swathgeo/footprint.py`
- **Bash**: `tail -28 data/consistency.log | cut -c1-200; ~/.local/bin/mise exec -- pixi run python -c " import pandas as pd d=pd.read_csv('results/analytic_consistency.csv…`
- **Bash**: `~/.local/bin/mise exec -- pixi run python -c " import pandas as pd, json d=pd.read_csv('results/analytic_consistency.csv') w=d[(d.model=='reference')&(d.height…`

While the benchmark runs (I'll avoid heavy concurrent jobs so timings stay clean), writing the PSF + areal-weighting module.

- **Write**: `l2-swath-geolocation/src/swathgeo/psf.py`
- **Bash**: `python3 - <<'EOF' p='src/swathgeo/psf.py'; s=open(p).read() s=s.replace(''' poly_local = shapely.prepared.prep(poly_local) if hasattr(shapely, "prepared") else…`
- **Bash**: `sleep 60; cat data/bench_locate.log | cut -c1-400; ps aux | grep bench_locate | head -3`
- **Bash**: `cat data/bench_locate.log | cut -c1-300; ps aux | grep -c "bench_locate"`
- **Write**: `l2-swath-geolocation/scripts/20_footprints.py`
- **Bash**: `cut -c1-500 data/bench_locate.log`
- **Write**: `l2-swath-geolocation/src/swathgeo/netsim.py`
- **Bash**: `cut -c1-250 data/bench_locate.log | tail -8`

Locator benchmark still running (MODIS done; xarray's default `.sel` fails on 2‑D coords as expected). Checking the VirtualiZarr/icechunk APIs for the read benchmark.

- **Bash**: `~/.local/bin/mise exec -- pixi run python -c " import virtualizarr, inspect from virtualizarr import open_virtual_dataset print(inspect.signature(open_virtual_…`
- **Bash**: `cat > config/net_profiles.toml <<'EOF' # Network profiles for the throttling proxy (src/swathgeo/netsim.py). Sources and the # reasoning behind each number: se…`
- **Bash**: `~/.local/bin/mise exec -- pixi run python - <<'EOF' 2>&1 | tail -12 import subprocess, sys, os, requests from osgeo import gdal gdal.UseExceptions() p=subproce…`
- **Bash**: `cut -c1-120 data/bench_locate.log | tail -4; ~/.local/bin/mise exec -- pixi run python - <<'EOF' 2>&1 | tail -8 from osgeo import gdal; gdal.UseExceptions() ds…`
- **Write**: `l2-swath-geolocation/src/swathgeo/readers.py`

Now testing VirtualiZarr parsers (HDF5, HDF4, DMR++) → icechunk on local files.

- **Bash**: `for f in data/raw/*/dmrpp/*.dmrpp; do cp -n "$f" "$(dirname $(dirname $f))/"; done; ls data/raw/*/*.dmrpp; mkdir -p data/tmp && ~/.local/bin/mise exec -- pixi …`
- **Bash**: `~/.local/bin/mise exec -- pixi run python - <<'EOF' 2>&1 | grep -v Warning | tail -30 import time, warnings; warnings.filterwarnings('ignore') import h5py from…`
- **Bash**: `~/.local/bin/mise exec -- pixi run python - <<'EOF' 2>&1 | grep -v Warning | tail -20 import warnings, traceback; warnings.filterwarnings('ignore') from virtua…`
- **Bash**: `grep -o '<Group name="[^"]*"' data/raw/modis/MOD11_L2.A2023154.1825.061.2023155151846.hdf.dmrpp | head; grep -o 'dmrpp:href="[^"]*"' data/raw/modis/MOD11_L2.A2…`
- **Bash**: `cut -c1-110 data/bench_locate.log | tail -3; wc -l data/bench_locate.log`
- **Write**: `l2-swath-geolocation/scripts/30_bench_read.py`
- **Bash**: `cut -c1-110 data/bench_locate.log | tail -2; which moto_server; ls .pixi/envs/default/bin | grep -i moto`

While the locator benchmark grinds through VIIRS/ECOSTRESS brute force (I'm holding off on heavy jobs to keep timings clean), I'll load the dataviz guidance before writing any figure code.

- **Skill**: `dataviz`
- **Bash**: `cd /tmp/claude-0/bundled-skills/2.1.322/436dbe7d8885d6de8e73917e5944c354/dataviz && sed -n 1,200p references/palette.md | head -120`
- **Bash**: `cd /tmp/claude-0/bundled-skills/2.1.322/436dbe7d8885d6de8e73917e5944c354/dataviz && sed -n 120,220p references/palette.md; sed -n 1,80p references/anti-pattern…`

Writing a shared matplotlib style using the validated palette (categorical in fixed order; blue sequential; blue↔red diverging).

- **Bash**: `cd /home/user/simon-code-research/l2-swath-geolocation && cat > src/swathgeo/plotstyle.py <<'EOF' """Shared matplotlib style (validated reference palette from …`
- **Bash**: `mkdir -p report && cat > report/_quarto.yml <<'EOF' project: type: website output-dir: _site render: - "*.qmd" resources: - data/ - figures/ website: title: "L…`

Writing tests while waiting.

- **Bash**: `cat > tests/test_core.py <<'EOF' import json import os import subprocess import sys import time import numpy as np import pytest import shapely from swathgeo i…`
- **Bash**: `cat > config/psf.toml <<'EOF' # Parametric separable PSFs in units of each pixel's own sample spacing (along-scan "s", # along-track "t"). Each axis = convolut…`

Running a quick Part B smoke test on one MODIS scene (single‑threaded, light).

- **Bash**: `cat > /tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad/fp1.py <<'EOF' import sys, time, numpy as np, geopandas as g…`
- **Bash**: `python3 - <<'EOF' p='src/swathgeo/netsim.py'; s=open(p).read() s=s.replace(''' self.redirect_ms = cfg.get("redirect_ms", 0.0)''',''' self.redirect_ms = cfg.get…`

Saving both research reports as notes in the experiment (they're the citation base for the methods pages).

- **Bash**: `mkdir -p /home/user/simon-code-research/l2-swath-geolocation/notes && cat > /home/user/simon-code-research/l2-swath-geolocation/notes/psf_sources.md <<'EOF' # …`
- **Bash**: `python3 - <<'EOF' p='src/swathgeo/psf.py'; s=open(p).read() s=s.replace('''def quadrature(psf, k=9): """Nodes (u, v) and masses for a separable PSF, k nodes pe…`
- **Bash**: `sed -i 's/w = P.psf_weights(pg, poly, P.BOX, k=9, cell=100, pou=True)/w = P.psf_weights(pg, poly, P.BOX, cell=100, pou=True)/' tests/test_core.py && ~/.local/b…`
- **Bash**: `git add -A . && git commit -q -m "l2-swath-geolocation: locators, footprints/PSF, network simulator, readers, consistency results Co-Authored-By: Claude Opus 5…`

Prototyping the read harness on VIIRS only (1 rep, a few profiles) to shake out bugs before the real run.

- **Bash**: `timeout 1500 ~/.local/bin/mise exec -- pixi run python scripts/30_bench_read.py --profiles local,zero_http,zero_s3,https_earthdata --sensors viirs --reps 1 --s…`
- **Bash**: `~/.local/bin/mise exec -- pixi run python -c " import icechunk c=icechunk.RepositoryConfig.default(); print([a for a in dir(c) if not a.startswith('_')]) print…`
- **Bash**: `sed -i 's/ cfg.max_concurrent_requests_for_object = concurrency/ cfg.max_concurrent_requests = concurrency/' src/swathgeo/readers.py && rm -rf data/icechunk &&…`
- **Bash**: `sleep 100; cat /tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/tasks/by8u08k7y.output | grep -v -i warn | tail -30`
- **ToolSearch**: `select:Monitor`
- **Monitor**: `{"description": "read-bench prototype progress", "timeout_ms": 900000, "command": "tail -n +1 -f /tmp/claude-0/-home-user-simon-code-research/cb779936-c969-501…`

Prototype read benchmark running (VIIRS only) while the locator benchmark continues. Drafting the figures script in the meantime.

- **Write**: `l2-swath-geolocation/scripts/40_figures.py`
- **Bash**: `~/.local/bin/mise exec -- pixi run python scripts/40_figures.py analytic 2>&1 | tail -3; grep -v -i warn /tmp/claude-0/-home-user-simon-code-research/cb779936-…`
- **Read**: `l2-swath-geolocation/figures/analytic_window.png`
- **Bash**: `sed -i 's/"semibold"/"bold"/' src/swathgeo/plotstyle.py && sed -i 's/fontweight="semibold"/fontweight="bold"/' scripts/40_figures.py && grep -v -i warn /tmp/cl…`

While benchmarks run, writing the methods pages with interactive Observable JS explainers. Starting with Part A.

- **Write**: `l2-swath-geolocation/report/locate-methods.qmd`

Now the Part B methods page (footprint trig, Voronoi, PSFs, weighting schemes) with explainers.

- **Write**: `l2-swath-geolocation/report/footprint-methods.qmd`
- **Bash**: `cut -c1-100 data/bench_locate.log | tail -2; ls results/; cat /tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/tasks/by8u08k7y…`
- **Bash**: `~/.local/bin/mise exec -- pixi run python -c " import pandas as pd; d=pd.read_csv('results/read_bench.csv'); cols=[c for c in ['task','profile','reader','rep',…`
- **Bash**: `~/.local/bin/mise exec -- pixi run python - <<'EOF' 2>&1 | grep -v -i warn | tail -15 import subprocess, sys, os, time, h5py p=subprocess.Popen([sys.executable…`
- **Bash**: `ls /tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/tasks/ | head; ps aux | grep -c "30_bench_read"; ~/.local/bin/mise exec --…`
- **Bash**: `~/.local/bin/mise exec -- pixi run python -c " import pandas as pd; d=pd.read_csv('results/read_bench.csv'); d=d[d.task=='full'] cols=[c for c in ['task','prof…`
- **Bash**: `~/.local/bin/mise exec -- pixi run python - <<'EOF' 2>&1 | tail -8 import subprocess, sys, os, time, h5py, requests p=subprocess.Popen([sys.executable,'-m','sw…`
- **Bash**: `python3 - <<'EOF' p='src/swathgeo/readers.py'; s=open(p).read() s=s.replace('''def fsspec_open(access: Access, key: str, cache_type="readahead", block_size=Non…`

Writing the Part C methods page (simulator design, profiles with citations, readers, and a what‑if profile simulator widget).

- **Write**: `l2-swath-geolocation/report/read-methods.qmd`
- **Bash**: `ps aux | grep "30_bench_read" | grep -v grep | wc -l; cut -c1-100 data/bench_locate.log | tail -2; ~/.local/bin/mise exec -- pixi run python -c " import pandas…`
- **Bash**: ``cat > report/reproduce.qmd <<'EOF' --- title: "Reproduce" --- Everything is pinned: tools with [mise](https://mise.jdx.dev) (`mise.toml`: pixi, Quarto) and the…``
- **Bash**: `until ! pgrep -f "30_bench_read.py --profiles local,zero_http" >/dev/null; do sleep 5; done; echo done`

Waiting on the prototype read run and the ECOSTRESS locator benchmark.

- **Bash**: `until ! pgrep -f "30_bench_read.py --profiles local,zero_http" >/dev/null; do sleep 5; done; cd /home/user/simon-code-research/l2-swath-geolocation && ~/.local…`
- **Bash**: `cat >> PROMPT.md <<'EOF' ## Follow-up 2 (Sent while Claude was reporting that MODIS HDF4 has no working virtual-Zarr path: "The HDF4 route is a dead end for no…`
- **TaskCreate**: `{"subject": "Fix VirtualiZarr HDF4/DMR++ for MODIS (vendored submodule; blunt then minimal patch; options)", "description": "After everything else: vendor virt…`

Now replacing moto with a native S3‑API handler in the proxy (HEAD/GET with Range, ListObjectsV2, NoSuchKey errors, served from local files).

- **Bash**: `python3 - <<'EOF' p='src/swathgeo/netsim.py'; s=open(p).read() s=s.replace(''' reader --HTTP--> [proxy :port (profile)] --> moto S3 server (S3 profiles) \\\\--…`
- **Bash**: `python3 - <<'EOF' p='src/swathgeo/netsim.py'; s=open(p).read() s=s.replace(''' session: dict = {} async def get_session(): if "s" not in session: session["s"] …`
- **Bash**: `python3 - <<'EOF' p='src/swathgeo/readers.py'; s=open(p).read() s=s.replace(''' def __init__(self, repo_root: Path, concurrency: int = 16): self.repo_root = re…`
- **Bash**: `python3 - <<'EOF' p='scripts/30_bench_read.py'; s=open(p).read() s=s.replace(''' try: stats(port) t = time.perf_counter() arrs = {}''',''' try: if hasattr(rdr,…`
- **Bash**: `for spec in "VirtualiZarr https://github.com/zarr-developers/VirtualiZarr v2.8.0" "kerchunk https://github.com/fsspec/kerchunk 0.2.10"; do set -- $spec; git su…`
- **Bash**: `cd /home/user/simon-code-research/l2-swath-geolocation && SP=.pixi/envs/default/lib/python3.12/site-packages; diff -rq $SP/virtualizarr vendor/VirtualiZarr/vir…`
- **Bash**: `cd /home/user/simon-code-research/l2-swath-geolocation/vendor/VirtualiZarr/virtualizarr && ls parsers; cat parsers/hdf4.py 2>/dev/null | head -150 || ls parser…`
- **Bash**: `sed -n 150,330p parsers/hdf4.py`
- **Bash**: `cd /home/user/simon-code-research/l2-swath-geolocation && sed -n 150,330p vendor/kerchunk/kerchunk/hdf4.py`
- **Bash**: `cd /home/user/simon-code-research/l2-swath-geolocation/vendor/VirtualiZarr/virtualizarr && grep -rn "FillValueCoder\|_FillValue" --include=*.py . | grep -v tes…`
- **Bash**: `sed -n 90,125p parsers/utils.py; sed -n 470,500p parsers/dmrpp.py; grep -n "def _parse_attribute\|def _get_attrib\|Attribute" parsers/dmrpp.py | head`
- **Bash**: `sed -n 500,560p parsers/dmrpp.py; grep -n '_FillValue' -B2 -A3 /home/user/simon-code-research/l2-swath-geolocation/data/raw/modis/MOD11_L2.A2023154.1825.061.20…`
- **Bash**: `cd /home/user/simon-code-research/l2-swath-geolocation && PYTHONPATH=vendor/VirtualiZarr:vendor/kerchunk ~/.local/bin/mise exec -- pixi run python -c " import …`
- **Bash**: `mkdir -p /home/user/simon-code-research/l2-swath-geolocation/scripts && cat > /home/user/simon-code-research/l2-swath-geolocation/scripts/50_hdf4_virtual_check…`

Baseline reproduces all five failures. Applying the blunt fixes in the vendored copies.

- **Bash**: `cd /home/user/simon-code-research/l2-swath-geolocation/vendor/kerchunk/kerchunk && grep -n "def _dec_comp" -A 25 hdf4.py; grep -n "^comp\|^spec\|COMP\b" hdf4.p…`
- **Bash**: `sed -n 515,530p hdf4.py && python3 - <<'EOF' p='hdf4.py'; s=open(p).read() s=s.replace(''' elif t == "SD": if isinstance(inf2["data"][-1], (tuple, list)):''','…`

Now the VirtualiZarr side: fill‑value encoding helper, HDF4 per‑variable compression and `_FillValue` encoding.

- **Bash**: `cd /home/user/simon-code-research/l2-swath-geolocation/vendor/VirtualiZarr/virtualizarr && python3 - <<'EOF' p='parsers/utils.py'; s=open(p).read() s=s.replace…`
- **Bash**: `PYTHONPATH=vendor/VirtualiZarr:vendor/kerchunk ~/.local/bin/mise exec -- pixi run python - <<'EOF' 2>&1 | grep -v -i warn | tail -25 import numpy as np, xarray…`
- **Bash**: `sed -n 1,30p vendor/kerchunk/kerchunk/hdf4.py | grep -n "f4\|f8\|dtypes\|str" ; grep -n "^dtypes" -A 22 vendor/kerchunk/kerchunk/hdf4.py | head -26; grep -n 'n…`
- **Bash**: `sed -n 440,470p vendor/VirtualiZarr/virtualizarr/parsers/dmrpp.py`
- **Bash**: `python3 - <<'EOF' p='vendor/kerchunk/kerchunk/hdf4.py'; s=open(p).read() s=s.replace('''dtypes = { 5: "f4", 6: "f8",''','''dtypes = { 5: ">f4", # BLUNT FIX: HD…`

MYD11_L2 and the MOD11_L2 DMR++ now read bit‑identical to pyhdf. MYD03 has 3‑D variables (e.g. `T_inst2ECR`, 203×3×3) but dimension names are only generated for up to 2‑D.

- **Bash**: `python3 - <<'EOF' p='vendor/VirtualiZarr/virtualizarr/parsers/hdf4.py'; s=open(p).read() old=''' "dimension_names": [f"{name}_x", f"{name}_y"][: len(shape)] if…`
- **Bash**: `PYTHONPATH=vendor/VirtualiZarr:vendor/kerchunk ~/.local/bin/mise exec -- pixi run python - <<'EOF' 2>&1 | grep -v -i warn | tail -5 import numpy as np, xarray …`
- **Bash**: `PYTHONPATH=vendor/VirtualiZarr:vendor/kerchunk ~/.local/bin/mise exec -- pixi run python - <<'EOF' 2>&1 | grep -v -i warn | tail -5 import numpy as np, xarray …`

The `Scan Type` "mismatch" is just xarray's default character concatenation (`[b'D',b'a',b'y',...]` → `b'Day'`); the data is identical. Disabling that in the check:

- **Bash**: `sed -i 's/consolidated=False, zarr_format=3, mask_and_scale=False, decode_times=False)/consolidated=False, zarr_format=3, mask_and_scale=False, decode_times=Fa…`
- **Bash**: `cd /home/user/simon-code-research/l2-swath-geolocation && mkdir -p patches && git -C vendor/VirtualiZarr diff > patches/blunt-virtualizarr.diff && git -C vendo…`
- **Bash**: `grep -n "def build_virtual_repos" -A 30 scripts/30_bench_read.py | head -40; grep -n "_virtual_build_worker" -A 25 scripts/30_bench_read.py | head -30`
- **Bash**: `python3 - <<'EOF' p='scripts/30_bench_read.py'; s=open(p).read() s=s.replace('''PROFILES = [''','''# MODIS HDF4: only possible with the patched VirtualiZarr/ke…`
- **Bash**: `python3 - <<'EOF' p='scripts/30_bench_read.py'; s=open(p).read() s=s.replace(''' procs, ports = start_services(profiles) try: if "virtual_hdf4" in steps: build…`
- **Bash**: `python3 - <<'EOF' p='scripts/30_bench_read.py'; s=open(p).read() old=''' procs, ports = start_services(profiles) try:''' assert old in s s=s.replace(old,''' if…`
- **Bash**: `rm -rf data/tmp/ictest4 && PYTHONPATH=vendor/VirtualiZarr:vendor/kerchunk ~/.local/bin/mise exec -- pixi run python - <<'EOF' 2>&1 | grep -v -i warn | tail -5 …`
- **Bash**: `python3 - <<'EOF' p='src/swathgeo/psf.py'; s=open(p).read() s=s.replace('''def psf_weights(pg: PixelGeom, poly_local, psf, k=None, cell=None, pou=True, batch=2…`

Chaining the remaining heavy runs so they execute back‑to‑back without overlapping (locator benchmark → Part B → read benchmark).

- **Bash**: `rm -f results/read_bench.csv results/virtual_build.csv && rm -rf data/icechunk && cat > data/chain.sh <<'EOF' #!/bin/bash cd /home/user/simon-code-research/l2-…`
- **Monitor**: `{"description": "pipeline stages (locate → footprints → read bench)", "timeout_ms": 1800000, "command": "tail -n +1 -f /home/user/simon-code-research/l2-swath-…`

Committing code + submodules (the vendored trees stay at the upstream tags; the edits live in `patches/`).

- **Bash**: `cd /home/user/simon-code-research && git add .gitmodules l2-swath-geolocation && git status --short | head -20 && git commit -q -m "l2-swath-geolocation: read …`
- **Bash**: `git ls-files -s l2-swath-geolocation/vendor; git status --short | head -5`
- **Bash**: `cd /home/user/simon-code-research/l2-swath-geolocation/vendor && ls VirtualiZarr/virtualizarr/tests/test_parsers/ | head -30; ls kerchunk/kerchunk/tests | grep…`
- **Bash**: `sed -n 1,60p VirtualiZarr/virtualizarr/tests/test_parsers/test_hdf4.py; ls kerchunk/tests | grep -i hdf; grep -n "hdf4\|def test" kerchunk/tests/test_hdf4.py 2…`
- **Bash**: `until grep -q "locate done" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log; do sleep 15; done; cut -c1-160 /home/user/simon-code-research/l…`
- **Bash**: `until grep -q "locate done" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log; do sleep 15; done; echo ok`
- **Bash**: `cut -c1-200 /home/user/simon-code-research/l2-swath-geolocation/data/bench_locate.log | tail -4; ps aux | grep -E "10_bench|multiprocessing" | grep -v grep | a…`
- **Bash**: `pkill -f data/chain.sh; pkill -f 10_bench_locate; sleep 2; pkill -f "multiprocessing.spawn"; sleep 1; ps aux | grep -E "bench|chain|spawn" | grep -v grep | wc …`
- **Bash**: `ps aux | grep -E "bench|chain|spawn" | grep -v grep | cut -c1-200`

Now patching the harness (worker timeout, resume, polygon budget for pykdtree).

- **Bash**: `cd /home/user/simon-code-research/l2-swath-geolocation && python3 - <<'EOF' p='src/swathgeo/locate.py'; s=open(p).read() old=''' k = 4096 q = geom.unit_xyz(c.y…`
- **Bash**: `~/.local/bin/mise exec -- pixi run python scripts/40_figures.py locate 2>&1 | tail -2`
- **Read**: `l2-swath-geolocation/figures/locate_times.png`

Layout reads well. One fix: the naive methods have no index, so their "build time" of zero gets clipped to 10⁻⁵ s and looks like a measurement — I'll label those "no index" instead.

- **Bash**: `python3 - <<'EOF' p='scripts/40_figures.py'; s=open(p).read() old=''' y = np.arange(len(order)) + (k - 1) * 0.22 v = sub[col].clip(lower=1e-5)''' assert old in…`

While ECOSTRESS locators re‑run, I'll develop the *minimal* patches in separate git worktrees (so the blunt vendored copies used by the pipeline stay untouched).

- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; cd /home/user/simon-code-research/l2-swath-geolocation && git -…`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; sed -n 118,150p $S/kc-min/kerchunk/hdf4.py`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; cd $S/kc-min && python3 - <<'EOF' p='kerchunk/hdf4.py'; s=open(…`

Now the minimal VirtualiZarr patch (Option A: kerchunk fixed at the source, VirtualiZarr only fixes its own logic).

- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; cd $S/vz-min/virtualizarr && python3 - <<'EOF' # utils: tolerat…`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; sed -i 's/ except ValueError:\n warnings.warn(f"Ignoring/X/' $S…`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; python3 - <<EOF p='$S/vz-min/virtualizarr/parsers/utils.py'; s=…`
- **Bash**: `cat /home/user/simon-code-research/l2-swath-geolocation/data/chain.log; cut -c1-130 /home/user/simon-code-research/l2-swath-geolocation/data/bench_locate.log |…`
- **Monitor**: `{"description": "pipeline stages (locate ECOSTRESS → footprints → read bench)", "timeout_ms": 1800000, "command": "tail -n +1 -F /home/user/simon-code-research…`

While that runs, building Option B — a VirtualiZarr‑only patch that works around the two kerchunk bugs inside VirtualiZarr, so it works with stock kerchunk 0.2.10.

- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; cd /home/user/simon-code-research/l2-swath-geolocation && git -…`

Option B also passes with stock kerchunk. Checking it stays correct once kerchunk is fixed (forward compatibility):

- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; cd /home/user/simon-code-research/l2-swath-geolocation && PYTHO…`

Both options verified. Next (light work while the pipeline runs): regression tests for each failure mode, generated on the fly with pyhdf/h5py so no binary fixtures are needed.

- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; cat > $S/vz-min/virtualizarr/tests/test_parsers/test_nasa_regre…`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; mkdir -p $S/regtest && cp $S/vz-min/virtualizarr/tests/test_par…`

Data all correct; only my fill‑value assertion was wrong (xarray moves `_FillValue` into `.encoding`). Fixing the assertion and running stock vs A vs B from outside the worktrees:

- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; for f in $S/regtest/test_nasa_regressions.py $S/vz-min/virtuali…`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; cd /home/user/simon-code-research/l2-swath-geolocation && PYTHO…`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; for f in $S/regtest/test_nasa_regressions.py $S/vz-min/virtuali…`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; for f in $S/regtest/test_nasa_regressions.py $S/vz-min/virtuali…`

Regression tests behave as intended: stock fails all 3; Options A and B pass all 3 (B also with a fixed kerchunk). Full upstream test suites still to run once the CPU is free. Checking the pipeline:

- **Bash**: `cat data/chain.log | grep -E "done|exit"; cut -c1-120 data/bench_locate.log | tail -3; tail -3 data/footprints.log 2>/dev/null | cut -c1-200`

I'll hold off on further CPU work until the ECOSTRESS locator run completes.

- **Bash**: `until grep -q "locate done" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log; do sleep 20; done; date`

While waiting, drafting `patches/README.md` (options, recommendation) — text only.

- **Write**: `l2-swath-geolocation/patches/README.md`
- **Bash**: `until grep -q "locate done" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log; do sleep 20; done; date; cut -c1-150 /home/user/simon-code-rese…`

Locator benchmark complete. Part B is now running. Making the Part A figures and summarizing:

- **Bash**: `~/.local/bin/mise exec -- pixi run python scripts/40_figures.py locate 2>&1 | tail -1; ~/.local/bin/mise exec -- pixi run python -c " import pandas as pd; pd.s…`
- **Bash**: `git add results/locate_bench.csv results/site figures scripts src patches/README.md && git commit -q -m "l2-swath-geolocation: locator benchmark results (all s…`
- **TaskUpdate**: `{"taskId": "3", "status": "completed"}`
- **TaskUpdate**: `{"taskId": "4", "status": "in_progress"}`
- **Bash**: `~/.local/bin/mise exec -- pixi run python -c " import pandas as pd; pd.set_option('display.width',250) d=pd.read_csv('results/locate_bench.csv') d=d[d.scene.is…`

Writing the Part A results page.

- **Write**: `l2-swath-geolocation/report/locate.qmd`
- **Bash**: `tail -4 data/footprints.log | cut -c1-300; ~/.local/bin/mise exec -- pixi run python -c " import pandas as pd; s=pd.read_csv('results/analytic_selfcal_constant…`
- **Bash**: `grep -E "^modis" data/footprints.log | grep -E "box|circle|colusa" | sed -E "s/'n_psf_contrib': [0-9]+, //" | cut -c1-330; tail -2 data/footprints.log | cut -c…`
- **Bash**: `python3 - <<'EOF' p='report/locate.qmd'; s=open(p).read() s=s.replace(''' the documentation. One calibration per platform is enough; the self-calibrated consta…`
- **Monitor**: `{"description": "pipeline: footprints → read bench", "timeout_ms": 1800000, "command": "tail -n +1 -F /home/user/simon-code-research/l2-swath-geolocation/data/…`
- **Bash**: `tail -3 data/footprints.log | cut -c1-400; ls -la results/vectors | head; du -sh results/vectors data/vectors`
- **Bash**: `until grep -qE "footprints exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log; do sleep 20; done; grep "footprints exit" /home/user/simon…`
- **Bash**: `until grep -qE "footprints exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log; do sleep 20; done; grep "footprints exit" /home/user/simon…`

Part B finished. Read benchmark has started (I'll keep my own work light). Looking at the synthetic‑truth results:

- **Bash**: `~/.local/bin/mise exec -- pixi run python -c " import pandas as pd, numpy as np; pd.set_option('display.width',250) s=pd.read_csv('results/synthetic_errors.csv…`
- **Bash**: `cat >> src/swathgeo/psf.py <<'EOF' def psf_lsq_weights(pg: PixelGeom, poly_local, psf, k=None, cell=None, group=None, cell_factor=0.5, max_pixels=8000): """PSF…`
- **Bash**: `sed -i 's/for k,v in W.items() if k!=.naive_center.}/for k,v in W.items() if k not in ("naive_center",)}/' /tmp/claude-0/-home-user-simon-code-research/cb77993…`

Works (NNLS adds ~1 s for the largest MODIS subset). Wiring it into the figures and methods page:

- **Bash**: `python3 - <<'EOF' p='scripts/40_figures.py'; s=open(p).read() s=s.replace('''"psf": "PSF", "psf_pou": "PSF (overlap-aware)"}''','''"psf": "PSF", "psf_pou": "PS…`

Queuing the Part B rerun (with NNLS weights and 200 synthetic polygons) to start automatically after the read benchmark:

- **Bash**: `cat > data/chain2.sh <<'EOF' #!/bin/bash cd /home/user/simon-code-research/l2-swath-geolocation until grep -q "readbench exit" data/chain.log; do sleep 20; don…`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; cd /home/user/simon-code-research/l2-swath-geolocation && git -…`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; until ! pgrep -f run_suites.sh >/dev/null; do sleep 15; done; c…`

Meanwhile, rendering the Part B footprint figures (light) to check them:

- **Bash**: `nice -n 19 ~/.local/bin/mise exec -- pixi run python scripts/40_figures.py footprint 2>&1 | tail -2`
- **Bash**: `cat /tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/tasks/bwyedm9rk.output`

The suites didn't run (mise can't find pixi from outside the experiment folder). Using the environment's Python directly:

- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; sed -i 's#^PY=.*#PY="nice -n 19 /home/user/simon-code-research/…`
- **Read**: `l2-swath-geolocation/figures/footprint_size.png`

The model tracks the files closely, including VIIRS's aggregation‑zone sawtooth. Checking the footprint maps:

- **Read**: `l2-swath-geolocation/figures/footprint_maps.png`
- **Bash**: `python3 - <<'EOF' p='scripts/40_figures.py'; s=open(p).read() old=''' for i, (gg, lab) in enumerate([(g, "trig footprints"), (vor, "Voronoi cells")]): ax = axe…`
- **Read**: `l2-swath-geolocation/figures/footprint_maps.png`
- **Bash**: `nice -n 19 ~/.local/bin/mise exec -- pixi run python - <<'EOF' 2>&1 | tail -6 import numpy as np, h5py, glob from swathgeo import config f=h5py.File(glob.glob(…`
- **Bash**: `python3 - <<'EOF' p='src/swathgeo/footprint.py'; s=open(p).read() s=s.replace('''def angular_widths(''','''def viirs_bowtie_deleted(rows, cols): """True for VI…`

Upstream suites ran. Comparing the exact failing test IDs between stock and patched (pre‑existing environment failures should be identical), and checking the kerchunk collection error:

- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; PY=/home/user/simon-code-research/l2-swath-geolocation/.pixi/en…`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; PY=/home/user/simon-code-research/l2-swath-geolocation/.pixi/en…`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; PY=/home/user/simon-code-research/l2-swath-geolocation/.pixi/en…`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; P=/home/user/simon-code-research/l2-swath-geolocation/patches; …`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; for w in vz-min vz-b kc-min; do echo "== $w"; git -C $S/$w diff…`

Updating the patch README with the final numbers and test results:

- **Bash**: ``python3 - <<'EOF' p='README.md'; s=open(p).read() s=s.replace('''* **VirtualiZarr** (`optionA-virtualizarr.diff`, +32/−5):''','''* **VirtualiZarr** (`optionA-v…``
- **Bash**: `cd /home/user/simon-code-research/l2-swath-geolocation && grep -v -i warn data/bench_read.log | tail -6 | cut -c1-220`
- **Bash**: `python3 - <<'EOF' p='scripts/30_bench_read.py'; s=open(p).read() old=''' vds = open_virtual_dataset(url, registry=reg, parser=DMRPPParser(group="/" + g.replace…`

Committing progress (patch work, figures, fixes):

- **Bash**: `python3 - <<'EOF' p='report/footprint-methods.qmd'; s=open(p).read() s=s.replace('''deletion", which is why VNP21 has fill values at the edges of scans off-nad…`
- **TaskUpdate**: `{"taskId": "7", "status": "in_progress"}`
- **TaskUpdate**: `{"taskId": "5", "status": "in_progress"}`
- **Monitor**: `{"description": "read bench progress (per reader/profile lines + stage ends)", "timeout_ms": 1800000, "command": "tail -n 0 -F /home/user/simon-code-research/l…`

While the read benchmark runs, drafting the experiment README (Part B/C numbers will be filled in when their runs finish).

- **Bash**: `grep -v -i warn data/bench_read.log | grep -E "^(modis|viirs|ecostress)" | tail -30 | cut -c1-170`
- **Bash**: `grep -v -i warn data/bench_read.log | tail -4 | cut -c1-250`

Notable: VirtualiZarr's HDF5 scan of the 780 MB ECOSTRESS GEO file transfers **264 MB** just to build references. Checking why (reading the parser's I/O path — no CPU needed):

- **Bash**: `cd /home/user/simon-code-research/l2-swath-geolocation/vendor/VirtualiZarr/virtualizarr && grep -n "Reader\|reader\|block_size\|buffer" parsers/hdf/hdf.py | he…`
- **Bash**: `cd /home/user/simon-code-research/l2-swath-geolocation && sed -n 13,60p .pixi/envs/default/lib/python3.12/site-packages/obspec_utils/readers/_block.py; sed -n …`
- **Bash**: `until grep -qE "^(modis|viirs|ecostress) " /home/user/simon-code-research/l2-swath-geolocation/data/bench_read.log; do sleep 30; done; grep -E "^(modis|viirs|e…`
- **Bash**: `grep -v -i warn data/bench_read.log | tail -3 | cut -c1-260`
- **Write**: `l2-swath-geolocation/README.md`
- **Bash**: `until grep -qE "readbench exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log; do sleep 30; done; tail -2 /home/user/simon-code-research/l…`
- **Bash**: `grep -E "^(modis|viirs|ecostress) " data/bench_read.log | cut -c1-170 | tail -40`
- **Bash**: `grep -v -i warn data/bench_read.log | tail -2 | cut -c1-200; date`

Still in the build phase (MODIS HDF4 over the simulated NCCS portal: 26 s). The read phase proper will take a couple of hours; I'll wait in chunks and check periodically.

- **Bash**: `sleep 1; until grep -qE "^(modis|viirs|ecostress) " /home/user/simon-code-research/l2-swath-geolocation/data/bench_read.log || grep -q "readbench exit" /home/u…`

MODIS now reads through icechunk virtual refs (45 requests, 2 MB for the site window vs 44 MB for download‑then‑read). Continuing to wait.

- **Bash**: `until grep -qE "^viirs " /home/user/simon-code-research/l2-swath-geolocation/data/bench_read.log || grep -q "readbench exit" /home/user/simon-code-research/l2-…`
- **TaskStop**: `{"task_id": "b5hbobsek"}`
- **Bash**: `~/.local/bin/mise exec -- pixi run python -c " import pandas as pd d=pd.read_csv('results/read_bench.csv'); e=d[d.error.notna()] for _,r in e.groupby(['reader'…`
- **Bash**: `until grep -q "readbench exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log; do sleep 30; done; tail -1 /home/user/simon-code-research/l2…`
- **Bash**: `grep -E "^viirs " /home/user/simon-code-research/l2-swath-geolocation/data/bench_read.log | cut -c1-165 | tail -45`
- **Bash**: `until grep -q "readbench exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log; do sleep 30; done; tail -1 /home/user/simon-code-research/l2…`
- **Bash**: `grep -E "^(viirs|ecostress) " /home/user/simon-code-research/l2-swath-geolocation/data/bench_read.log | cut -c1-150 | tail -4; date`
- **Write**: `l2-swath-geolocation/report/footprint.qmd`
- **Bash**: ``python3 - <<'EOF' p='report/footprint.qmd'; s=open(p).read() s=s.replace(''' try { return await FileAttachment(`data/site/${fpScene}__${fpPoly}__${fpKind}.geoj…``

Now the Part C results page skeleton (tables driven from the CSV):

- **Write**: `l2-swath-geolocation/report/read.qmd`
- **Bash**: `until grep -q "readbench exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log; do sleep 30; done; tail -1 /home/user/simon-code-research/l2…`
- **Bash**: `grep -E "^(viirs|ecostress) " /home/user/simon-code-research/l2-swath-geolocation/data/bench_read.log | cut -c1-150 | tail -3; date`
- **Bash**: `pkill -f data/chain2.sh; pkill -f data/chain3.sh; pkill -f data/chain.sh; pkill -f 30_bench_read; sleep 2; pkill -f swathgeo.netsim; pkill -f "multiprocessing.…`
- **Bash**: `cat > data/chain4.sh <<'EOF' #!/bin/bash cd /home/user/simon-code-research/l2-swath-geolocation ~/.local/bin/mise exec -- pixi run python scripts/30_bench_read…`
- **Bash**: `until grep -q "readbench exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log; do sleep 30; done; tail -1 /home/user/simon-code-research/l2…`

While that runs, adding the experiment to the root README and committing the pages:

- **Bash**: `cd /home/user/simon-code-research && cat README.md && cat >> README.md <<'EOF' - [l2-swath-geolocation](l2-swath-geolocation/): locating pixels (KD-tree, S2, H…`

Writing the site overview page skeleton:

- **Write**: `l2-swath-geolocation/report/index.qmd`
- **Bash**: `grep -E "^(viirs|ecostress) " /home/user/simon-code-research/l2-swath-geolocation/data/bench_read.log | cut -c1-150 | tail -3; date`
- **Bash**: `sleep 590 2>/dev/null || true; grep -E "^(viirs|ecostress) " /home/user/simon-code-research/l2-swath-geolocation/data/bench_read.log | cut -c1-150 | tail -4`
- **Bash**: `until [ $(grep -cE "^ecostress " /home/user/simon-code-research/l2-swath-geolocation/data/bench_read.log) -gt 0 ] || grep -q "readbench exit" /home/user/simon-…`
- **Bash**: `grep -E "^(viirs|ecostress) " /home/user/simon-code-research/l2-swath-geolocation/data/bench_read.log | cut -c1-150 | tail -4; date`

The read benchmark is progressing (VIIRS windows on the NCCS profile now). I'll test‑render the Quarto site at low priority to catch site problems early.

- **Bash**: `cd /home/user/simon-code-research/l2-swath-geolocation && nice -n 19 ~/.local/bin/mise exec -- pixi run python scripts/40_figures.py read areal synthetic 2>&1 …`

Site renders. Checking the interactive pages in a headless browser (console errors + a screenshot of a methods page):

- **Bash**: `cd /home/user/simon-code-research/l2-swath-geolocation/report/_site && (nice -n 19 python3 -m http.server 8765 >/dev/null 2>&1 &) && sleep 1 && cd /tmp/claude-…`
- **Bash**: `cd /tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad && nice -n 19 node shot.js 2>&1 | grep -E "^(locate|footprint|r…`

Only the footprint results page has errors, and those are the two CSVs that the pending Part B rerun will produce. Viewing the footprint methods page to check the widgets visually:

- **Bash**: `cd /tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad && python3 -c " from PIL import Image im=Image.open('shot_footp…`
- **Read**: `/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad/fm_top.png`
- **Bash**: `cd /home/user/simon-code-research/l2-swath-geolocation/report && grep -n '\${' *.qmd | grep -v '^\S*:\s*//' | grep -v "ojs" | awk -F: '{print $1":"$2}' | head …`
- **Bash**: `sed -n 55,60p locate-methods.qmd; sed -n 114,122p locate-methods.qmd; sed -n 99,103p footprint-methods.qmd; sed -n 173,177p footprint-methods.qmd; sed -n 249,2…`

Converting every prose sentence that embeds OJS values into an `md` template cell (robust against Pandoc's `$…$` math detection):

- **Bash**: ``python3 - <<'EOF' import re def ojs_md(text): t = text.strip().replace("`", "\\`") return "```{ojs}\n//| echo: false\nmd`" + t + "`\n```\n" edits = { "locate-m…``

Single‑expression sentences are safe. I'll re‑render and re‑check once all results are in. Checking the benchmark:

- **Bash**: `grep -E "^(viirs|ecostress) " /home/user/simon-code-research/l2-swath-geolocation/data/bench_read.log | cut -c1-150 | tail -3; date`
- **Bash**: `until [ $(grep -cE "^viirs +window_poly" /home/user/simon-code-research/l2-swath-geolocation/data/bench_read.log) -gt 20 ] || grep -q "readbench exit" /home/us…`
- **Bash**: `until [ $(grep -cE "^viirs +full" /home/user/simon-code-research/l2-swath-geolocation/data/bench_read.log) -gt 1 ] || grep -q "readbench exit" /home/user/simon…`
- **Bash**: `grep -E "^(viirs|ecostress) " /home/user/simon-code-research/l2-swath-geolocation/data/bench_read.log | cut -c1-150 | tail -3; date`

Roughly 25 min per VIIRS task; ECOSTRESS remains. Probably ~2 more hours. Waiting.

- **Bash**: `until grep -q "readbench exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log || [ $(grep -cE "^ecostress " /home/user/simon-code-research/…`
- **Bash**: `until grep -q "readbench exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log || [ $(grep -cE "^ecostress " /home/user/simon-code-research/…`
- **Bash**: `grep -E "^(viirs|ecostress) " /home/user/simon-code-research/l2-swath-geolocation/data/bench_read.log | cut -c1-150 | tail -3; date`
- **Bash**: `until grep -q "readbench exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log || [ $(grep -cE "^viirs +full" /home/user/simon-code-research…`
- **Bash**: `grep -E "^(viirs|ecostress) " /home/user/simon-code-research/l2-swath-geolocation/data/bench_read.log | cut -c1-150 | tail -2; date`

~2 more hours expected. Meanwhile, checking the transcript helper (needed at the end):

- **Bash**: `cd /home/user/simon-code-research && sed -n 1,40p _helpers/transcript.py | head -40`
- **Bash**: `until grep -q "readbench exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log || [ $(grep -cE "^ecostress " /home/user/simon-code-research/…`
- **Bash**: `grep -E "^(viirs|ecostress) " /home/user/simon-code-research/l2-swath-geolocation/data/bench_read.log | cut -c1-150 | tail -2; date`
- **Bash**: `until grep -q "readbench exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log || [ $(grep -cE "^ecostress " /home/user/simon-code-research/…`
- **Bash**: `grep -E "^(viirs|ecostress) " /home/user/simon-code-research/l2-swath-geolocation/data/bench_read.log | cut -c1-150 | tail -2; date`
- **Bash**: `cd /home/user/simon-code-research/l2-swath-geolocation && python3 - <<'EOF' p='scripts/30_bench_read.py'; s=open(p).read() old=''' for reader_name in READERS: …`
- **Bash**: `until grep -q "readbench exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log || [ $(grep -cE "^ecostress " /home/user/simon-code-research/…`
- **Bash**: `grep -E "^(viirs|ecostress) " /home/user/simon-code-research/l2-swath-geolocation/data/bench_read.log | cut -c1-150 | tail -2; date`
- **Bash**: `until grep -q "readbench exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log || [ $(grep -cE "^ecostress " /home/user/simon-code-research/…`
- **Bash**: `grep -E "^(viirs|ecostress) " /home/user/simon-code-research/l2-swath-geolocation/data/bench_read.log | cut -c1-150 | tail -2; date`
- **Bash**: `until grep -q "readbench exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log || [ $(grep -cE "^ecostress " /home/user/simon-code-research/…`

Still waiting on the read benchmark: VIIRS is done and the ECOSTRESS runs (the last sensor) have started. Continuing to wait; the Part B rerun and the DMR++ rebuild are queued after it.

- **Bash**: `until grep -q "readbench exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log || [ $(grep -cE "^ecostress +window_poly" /home/user/simon-co…`
- **Bash**: `grep -E "^ecostress" /home/user/simon-code-research/l2-swath-geolocation/data/bench_read.log | cut -c1-150 | tail -3; date`

For one ECOSTRESS site window in‑region: icechunk virtual refs take 0.36 s (0.8 MB) versus 15.5 s to download the 983 MB granule pair. Continuing.

- **Bash**: `until grep -q "readbench exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log || [ $(grep -cE "^ecostress +window_poly" /home/user/simon-co…`
- **Bash**: `grep -E "^ecostress" /home/user/simon-code-research/l2-swath-geolocation/data/bench_read.log | cut -c1-150 | tail -2; date`
- **Bash**: `until grep -q "readbench exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log || [ $(grep -cE "^ecostress +window_poly" /home/user/simon-co…`
- **Bash**: `grep -E "^ecostress" /home/user/simon-code-research/l2-swath-geolocation/data/bench_read.log | cut -c1-150 | tail -2; date`
- **Bash**: `until grep -q "readbench exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log || [ $(grep -cE "^ecostress +window_poly" /home/user/simon-co…`
- **Bash**: `grep -E "^ecostress" /home/user/simon-code-research/l2-swath-geolocation/data/bench_read.log | cut -c1-150 | tail -2; date`
- **Bash**: `until grep -q "readbench exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log || [ $(grep -cE "^ecostress +window_poly" /home/user/simon-co…`
- **Bash**: `grep -E "^ecostress" /home/user/simon-code-research/l2-swath-geolocation/data/bench_read.log | cut -c1-150 | tail -2; date`
- **Bash**: `python3 - <<'EOF' p='scripts/30_bench_read.py'; s=open(p).read() old=''' if sensor == "ecostress" and task == "full" and reader_name not in ECO_FULL_READERS:''…`
- **Bash**: `until grep -q "readbench exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log || [ $(grep -cE "^ecostress +window_poly" /home/user/simon-co…`
- **Bash**: `until grep -q "readbench exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log || [ $(grep -cE "^ecostress +full" /home/user/simon-code-rese…`
- **Bash**: `grep -E "^ecostress" /home/user/simon-code-research/l2-swath-geolocation/data/bench_read.log | cut -c1-150 | tail -2; date`
- **Bash**: `until grep -q "readbench exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log || [ $(grep -cE "^ecostress +full" /home/user/simon-code-rese…`
- **Bash**: `grep -E "^ecostress" /home/user/simon-code-research/l2-swath-geolocation/data/bench_read.log | cut -c1-150 | tail -2; date`
- **Bash**: `until grep -q "readbench exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log || [ $(grep -cE "^ecostress +full" /home/user/simon-code-rese…`
- **Bash**: `grep -E "^ecostress" /home/user/simon-code-research/l2-swath-geolocation/data/bench_read.log | cut -c1-150 | tail -2; date`
- **Bash**: `until grep -q "readbench exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log || [ $(grep -cE "^ecostress +full" /home/user/simon-code-rese…`
- **Bash**: `grep -E "^ecostress" /home/user/simon-code-research/l2-swath-geolocation/data/bench_read.log | cut -c1-150 | tail -2; date`
- **Bash**: `until grep -q "readbench exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log || [ $(grep -cE "^ecostress +full" /home/user/simon-code-rese…`

On the last task (ECOSTRESS full granule). Roughly 30–40 more minutes.

- **Bash**: `until grep -q "readbench exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log; do sleep 30; done; date; tail -2 /home/user/simon-code-resea…`

The session's worker restarted and plan mode is now active, so I can only look, not run anything. Checking what survived the restart:

- **Bash**: `cd /home/user/simon-code-research/l2-swath-geolocation 2>&1 && cat data/chain.log | grep -E "exit|done"; ps aux | grep -E "bench|chain|netsim|footprints" | gre…`
- **Read**: `~/.claude/plans/experiment-l2-swath-geolocation-download-iterative-wilkinson.md`
- **Edit**: `~/.claude/plans/experiment-l2-swath-geolocation-download-iterative-wilkinson.md`
- **ToolSearch**: `select:ExitPlanMode`

<details><summary><b>Proposed plan</b></summary>

# Plan: `l2-swath-geolocation`

## Resume plan (after the session worker restart, 2026-11-11 00:18 UTC)

The original plan (below) is implemented. The restart killed the background pipeline
(`data/chain4.sh`) part-way through the **last** read-benchmark task. Status:

- Done & committed: data, targets, Part A (locators + 53-scene analytic consistency), Part B
  first pass, network simulator + read harness, methods pages, the HDF4/VirtualiZarr work
  (blunt patch + minimal Options A/B with regression tests and upstream-suite comparison,
  `patches/README.md`), README draft, root README line.
- Interrupted: `results/read_bench.csv` has everything except the rest of **ECOSTRESS `full`**
  (stopped at `s3_cross_region`); not yet run: Part B rerun (NNLS "PSF-optimal" weights, VIIRS
  bow-tie exclusion, 200 synthetic polygons) and the DMR++ virtual-build rerun (group-name fix).
- The user's repeated message about the HDF4 dead end is already handled (Follow-up 2 in
  PROMPT.md; the patches exist). No new work needed beyond presenting the options at the end.

### Remaining steps

1. **Finish benchmarks** (sequential, background, one at a time so timings stay clean):
   `30_bench_read.py --steps read` (resumes; only remaining ECOSTRESS-full combos run) →
   `20_footprints.py areal synthetic` → `30_bench_read.py --steps build --build-parsers dmrpp`.
2. **Figures + site data**: `scripts/40_figures.py` (all steps). Keep only small vector exports
   in `results/vectors/` (box/circle; move county-sized `.fgb` to `data/vectors/`); no release
   needed (nothing > ~4 MB the site requires) — if that changes, ask first.
3. **Write-up**: fill the `<!-- … -->` placeholders in `report/index.qmd`, `footprint.qmd`,
   `read.qmd` and `README.md` (key results) from the final CSVs; mention the time-budget rules
   (90 s per combination, ECOSTRESS-full reader subset, default-GDAL skip on slow profiles for the
   ECOSTRESS county window) and the icechunk no-retry finding.
4. **Render & check**: `mise run site`; Playwright screenshots of every page, no console/OJS
   errors; `uv run _helpers/build_site.py --only l2-swath-geolocation --skip-assets` passes.
5. **Tests**: `mise run test` (core tests incl. netsim) passes.
6. **Record**: update PLAN.md with this plan (own commit); TRANSCRIPT.md via
   `uv run _helpers/transcript.py -o l2-swath-geolocation/TRANSCRIPT.md` (skim/redact);
   `publish.toml` (build = `mise run site`, output = `report/_site`, models, tools).
7. **Git**: commit in logical pieces (prefix `l2-swath-geolocation: `), push branch, fetch,
   rebase on `origin/main`, fast-forward + push `main`, delete `exp/l2-swath-geolocation` locally
   and on origin. Leave the vendored submodules at their upstream tags (patches live in `patches/`).
8. **Report back**: summary of results + the HDF4 fix options with the recommendation
   (Option A upstream in kerchunk + VirtualiZarr, keeping Option B's guards until a fixed kerchunk
   is released).

### Verification
- `results/read_bench.csv` has rows for every (sensor, task, profile, reader) combination that
  the harness selects; `results/synthetic_errors.csv` has 200 polygons × 5 scenes incl. `err_psf_lsq`.
- Site renders; footprint page loads `areal_means.csv`/`synthetic_errors.csv` without OJS errors.
- `scripts/50_hdf4_virtual_check.py` with `PYTHONPATH=vendor/...` (blunt patch) still prints ALL OK.

## Context

Extracting values from L2 *swath* products (curvilinear lat/lon, no grid) for points and
polygons is a recurring pain point. This experiment benchmarks how to (a) find the right
pixels (naive search, KD-tree, S2, H3, analytic inverse geolocation from orbit/scan geometry),
(b) represent what a pixel actually "sees" (view-angle-dependent footprint + point spread
function), and how much that matters for areal averages, and (c) read the data efficiently
(direct, GDAL, virtual Zarr/icechunk, DMR++, …) locally and under simulated network profiles.
MODIS, VIIRS and ECOSTRESS are deliberately different: whiskbroom with bow-tie overlap and
~2×5 km edge pixels (MODIS), on-board aggregation zones and bow-tie deletion (VIIRS), and a
70 m, ±25.5° ISS-mounted scanner (ECOSTRESS).

Decisions from Q&A: LST products for all sensors; I choose a CONUS same-day overlap region;
Quarto report site; follow CLAUDE.md git workflow (`exp/l2-swath-geolocation` → main).

Verified in the sandbox: Earthdata credentials (`EARTHDATA_LOGIN_USER/PASSWORD`) work for
LP DAAC and LAADS HTTPS downloads; CMR reachable; DMR++ sidecars exist (e.g. VNP21 `.nc.dmrpp`);
conda-forge and GitHub release-asset downloads work; mise is not installed yet (install via
mise.run). No real S3 in-region access → network behaviour is simulated (as requested).

## Data

| Sensor | L2 product | Geolocation | Format |
|---|---|---|---|
| MODIS Terra (+Aqua if useful) | MOD11_L2 v061 (LST, 1 km) | MOD03 v6.1 (1 km, incl. orbit pos/vel, attitude per scan) | HDF4 |
| VIIRS SNPP | VNP21 v002 (LST, 750 m M-band) | VNP03MOD v2 (incl. navigation data) | NetCDF4/HDF5 |
| ECOSTRESS | ECO_L2_LSTE v002 (70 m) | ECO_L1B_GEO v002 | HDF5 |

- `scripts/00_find_granules.py`: CMR search for a clear-sky summer day where all three overlap
  a chosen CONUS site; pick ~2 granules per sensor: site near nadir and site near swath edge
  (ECOSTRESS: whatever overlaps). Write chosen granule IDs/URLs to `config/granules.toml`
  (committed, so download is reproducible).
- `scripts/01_download.py`: earthaccess/requests with env-var credentials → `data/raw/`
  (git-ignored). Also fetch `.dmrpp` sidecars where present.
- Targets (`config/targets/`, committed, tiny): 1 flux-tower point (e.g., an AmeriFlux site in
  a heterogeneous landscape inside the overlap); 100 random points (fixed seed) inside the
  3-sensor common footprint; one ~30–50 km watershed (HUC) or county polygon (GeoJSON).

## Layout

```
l2-swath-geolocation/
  README.md PROMPT.md PLAN.md TRANSCRIPT.md publish.toml
  mise.toml            # pins pixi, quarto; tasks: download, locate, footprint, psf, readbench, site, all
  pixi.toml pixi.lock  # python + gdal(hdf4/hdf5 plugins) + pyhdf + h5py/h5netcdf + xarray + scipy
                       # + pykdtree + xoak + scikit-learn + pys2index/s2sphere + h3 + shapely/geopandas/pyogrio + virtualizarr
                       # + icechunk + kerchunk + fsspec/aiohttp + moto[server] + earthaccess + matplotlib
  config/              # granules.toml, targets/*.geojson, net_profiles.toml, psf.toml
  src/swathgeo/        # library code (readers, locators, footprint, psf, netsim, bench utils)
  scripts/             # numbered pipeline steps calling src/
  results/             # committed small CSV/Parquet tables of timings & accuracy
  figures/             # PNGs (in git if small; else release assets)
  report/              # Quarto project (index.qmd + sections), renders results/figures only
  data/                # git-ignored raw granules + derived indexes
```

## Part A — Pixel location / subsetting benchmarks (`src/swathgeo/locate/`)

Common interface `Locator.build(lat, lon)` / `.query_points(pts)` / `.query_polygon(poly)`,
returning (row, col) indices + distance. Timed separately: load geolocation, build index,
query (1 point, 100 points, polygon). Repeated runs (timeit-style, median + IQR), memory peak.

1. **Naive**: vectorized haversine/ECEF distance argmin over full arrays (numpy); plus
   `xarray` 2-D approach (note `sel(method="nearest")` doesn't work on curvilinear coords with
   default indexes — document); polygon via bbox prefilter + shapely `contains_xy` on centers.
2. **KD-tree**: scipy `cKDTree` and `pykdtree` on ECEF unit vectors (avoids dateline/pole issues).
2b. **xarray-native indexes**: [xoak](https://xoak.readthedocs.io/) (`ds.xoak.set_index` /
   `ds.xoak.sel`) with each of its backends (scipy KD-tree, sklearn BallTree/haversine,
   pys2index S2), plus xarray's built-in `NDPointIndex` (custom-index API that enables
   `sel(method="nearest")` on 2-D coords) if available in the pinned xarray. Evaluate both
   **performance** (build/query, same harness) and **usability**: lines of code, API
   ergonomics, dask/lazy support, polygon support (or lack thereof), handling of out-of-swath
   points, maintenance status/compatibility with current xarray. Summarised as a table.
3. **S2**: `pys2index` S2PointIndex (C++); polygon via S2 cell covering (s2sphere/`spherely`)
   then exact test.
4. **H3**: `h3` v4 — index pixel centers at resolution matched to pixel size, cell→pixel lookup
   (sorted array + searchsorted), point query with k-ring fallback; polygon via
   `polygon_to_cells` with a buffer for partial pixels.
5. **Analytic inverse geolocation**: use orbit position/velocity per scan (MOD03 `orb_pos/orb_vel`,
   VNP03 navigation data; ECOSTRESS: from L1B_GEO metadata if present, else derive a ground track
   from the nadir-most column) to (i) find the scan/line whose scan plane contains the target,
   (ii) compute scan angle satellite→target, (iii) map to sample index (MODIS linear in angle;
   VIIRS piecewise through 3:1/2:1/1:1 aggregation zones; ECOSTRESS linear), (iv) local
   refinement using the real lat/lon in a k×k window around the analytic guess. Report accuracy
   vs KD-tree truth (exact-hit rate, row/col offset distribution, distance error) and speed
   (needs no index; reads only a small window of geolocation).
   - **Neighbourhood size**: not fixed at 3×3. From the analytic-vs-truth offset distribution,
     choose the smallest window that contains the true pixel with ~100% (report p99/p99.9/max
     offsets) — i.e. the largest error we can *reliably* bound — separately for rows/cols and
     per sensor; report the read-cost/accuracy trade-off vs window size.
   - **Consistency across scenes**: a separate geolocation-only scene set (just MOD03 /
     VNP03MOD / ECO_L1B_GEO, no L2) spanning very different locations (tropics, mid-lat N & S,
     high latitude, near-dateline), ascending/descending orbits, and epochs: MODIS Terra & Aqua
     ~2012–2015 vs 2023–2025 (post-constellation-exit orbit drift: lower altitude, shifted
     equator-crossing time), VIIRS SNPP vs NOAA-20, ECOSTRESS across ISS altitude changes
     (reboosts). Show whether a single parameter set (altitude, IFOV, scan rate) works or
     per-granule parameters from the orbit vectors are required, and how window size must grow.

All methods must also report "is the point inside the swath at all" and handle MODIS bow-tie
(multiple scans covering a point → return all candidates, choose nearest center).

## Part B — Pixel footprints & PSF (`src/swathgeo/footprint.py`, `psf.py`)

- **Trigonometric footprint model** (spherical Earth, altitude h, IFOV): scan angle θ →
  Earth-central angle β = asin((R+h)/R·sinθ) − θ; along-scan size = R·IFOV·dβ/dθ, along-track
  size = slant range · IFOV_track. Sensor params in `config/psf.toml` (MODIS 705 km, ±55°,
  1 km@nadir; VIIRS 829 km with aggregation zones; ECOSTRESS ~400 km ISS altitude from metadata,
  ±25.5°). Validate against empirical spacing between neighbouring pixel centers and against
  view zenith in the geolocation files; plot size vs scan angle per sensor.
- **Voronoi tessellation** (relevant: it is exactly the partition implied by nearest-neighbour
  extraction): spherical Voronoi (`scipy.spatial.SphericalVoronoi`, or planar Voronoi in a
  local equal-area projection for speed) of pixel centers for the target subsets. Compare
  Voronoi cell area/shape vs the trig footprint model: they agree away from edges, but Voronoi
  cells are non-overlapping, so in MODIS bow-tie overlap regions they shrink/fragment while the
  true footprints overlap, and they ignore the PSF. Voronoi is also used as an extra weighting
  scheme in the areal-average comparison and as a vector export option.
- **Vector export**: per-pixel quadrilaterals oriented along scan/track directions (from
  local Jacobian of the lat/lon grid, scaled by the model size) → GeoParquet + FlatGeobuf for
  the target subsets (small subsets committed/released; full-granule export via a task, not
  committed). Also a "naive" export (nominal square at center) for comparison.
- **PSF research** (web: ATBDs, literature): MODIS — triangular along-scan × rectangular
  along-track (Nishihama/Wolfe MOD03 ATBD; Tan et al. 2006; Campagnolo & Montaño 2014 Gaussian
  approx); VIIRS — pre-launch LSF/MTF & aggregation effects (VIIRS SDR/geolocation ATBD,
  Wolfe et al. 2013); ECOSTRESS — L1 ATBD/MTF spec. Encode as parametric 2-D PSFs in pixel
  coordinates, with citations in `config/psf.toml` and the report. Where only MTF is given,
  derive a Gaussian-equivalent and state the assumption.
- **Areal averages**: for the polygon (plus 2–3 extra representative polygons: small vs large,
  near nadir vs swath edge), compute LST means with weights from (1) naive equal-size pixels
  (center-in-polygon / nominal-square area fraction), (1b) Voronoi-cell area fraction, (2) true footprint area fraction,
  (3) footprint ⊗ PSF energy fraction (numerical integration on a fine sub-pixel grid).
  Plus a **synthetic-truth test**: high-res synthetic LST field (e.g., land-cover-like
  patches), simulate each sensor's observation via PSF at real geometry, recover polygon mean
  with each weighting → error vs known truth. Figures: weight maps, bias by method/sensor/
  scan position.

## Part C — Read performance (`src/swathgeo/readers/`, `netsim/`)

Read tasks: (1) full LST + lat/lon arrays, (2) point extraction (geolocation + single pixel),
(3) polygon window. Readers:
- direct: `pyhdf` (HDF4) / `h5py` (HDF5/NetCDF4); `xarray` + `h5netcdf`/`netCDF4`
- GDAL: `osgeo.gdal` HDF4/HDF5 drivers, `/vsicurl/` and `/vsis3/` for remote (with tuned
  `GDAL_*` cache/merge options as a variant)
- fsspec + h5py (HTTP/S3) with block-cache variants (none/readahead/blockcache, block sizes)
- VirtualiZarr → icechunk (virtual refs to original files), read via xarray/zarr; HDF4 via
  kerchunk HDF4 or DMR++ parser if possible — failure documented as a result if not
- DMR++ sidecar → VirtualiZarr (no file-scan needed), kerchunk JSON refs as baseline
- (optional) earthaccess `open()` style for parity with common user code

**Network simulator** (`netsim`): local `moto` S3 server holding the granules + a Python
asyncio reverse proxy that injects per-request latency (TTFB), connection setup cost,
per-connection and aggregate bandwidth caps, jitter, stalls, and 5xx errors, serving both S3
API and plain HTTP Range requests — so GDAL, fsspec, h5py and icechunk all do *real* network
I/O. Profiles in `config/net_profiles.toml` (values justified from published AWS/Earthdata
measurements where findable; otherwise stated assumptions):
1. `s3-in-region`: ~20–40 ms TTFB, ~80–100 MB/s per connection
2. `s3-cross-region`: ~80–150 ms TTFB, ~20–50 MB/s
3. `earthdata-https`: extra redirect round-trips on first request (URS → CloudFront → signed
   S3), ~100–300 ms TTFB, ~10–30 MB/s
4. `nccs-portal`: heavy-tailed latency (lognormal, p99 multi-second), random bandwidth
   1–50 MB/s, occasional stalls and ~1–2% 5xx needing retries
Metrics per run: wall time, # requests, bytes transferred (from proxy logs); repeated runs,
distributions shown (especially for nccs). Also report the raw local baseline.

## Report & publishing

- Quarto website in `report/` (pinned via mise), rendering only committed `results/` tables
  and `figures/` (no Python execution in CI; pre-rendered matplotlib PNGs).
  `publish.toml`: `build = "mise run site"`, `output = "report/_site"`.
- Pages: overview/results (`index.qmd`) + for **each part a results page and a dedicated
  methods page** describing the method in detail (equations, sensor parameters, citations).
  Methods pages carry client-side interactive explainers using Quarto's built-in Observable JS
  (runs in the browser; nothing to execute in CI; small JSON/CSV inputs only), e.g.:
  - Locate: toy swath where you click a target and step through naive / KD-tree / S2 / H3 /
    analytic search (cells visited, candidates); H3/S2 resolution slider vs pixel size.
  - Footprint: sliders for altitude, IFOV, scan angle → footprint size/shape (spherical trig),
    MODIS bow-tie overlap and VIIRS aggregation-zone visualisation; Voronoi vs true footprint
    toggle on a real subset (Leaflet/Observable Plot map of exported pixel polygons).
  - PSF: PSF shape explorer per sensor (triangular×rect, Gaussian, MTF-derived) and a
    polygon-weight demo showing naive vs footprint vs PSF weights and the resulting mean.
  - Read/network: profile simulator — sliders for latency, bandwidth, jitter, concurrency →
    predicted read time per reader, driven by the measured request counts/bytes logs, shown
    next to the actual measured distributions.
- README: question, headline results, `mise run all`, Pages link. Root README line added.
- Release `l2-swath-geolocation`: only if figures/vector exports are too large for git —
  **I'll ask before creating/uploading, listing files and sizes.**
- PROMPT.md (verbatim prompt + my Q&A), PLAN.md (this plan), TRANSCRIPT.md via
  `uv run _helpers/transcript.py -o l2-swath-geolocation/TRANSCRIPT.md` at the end.

## Git

Branch `exp/l2-swath-geolocation`; commits per logical step prefixed
`l2-swath-geolocation: `; PROMPT.md/PLAN.md in their own commits; push regularly. At the end:
fetch, rebase onto `origin/main`, fast-forward and push `main`, delete branch locally and on
origin.

## Verification

- Unit-ish checks (`pytest` in `tests/`): footprint model reproduces MODIS ~2×4.8 km and VIIRS
  ~1.6 km edge sizes; Voronoi cell areas match model areas away from bow-tie/edges; all
  locators (incl. xoak backends) agree with brute force on the 100 points (excluding
  documented analytic misses); weights sum to ~1 and footprint/PSF integrals are normalized;
  netsim proxy delivers configured latency/bandwidth within tolerance (self-test).
- `mise run all` end-to-end from downloaded data produces `results/` + `figures/`.
- `uv run _helpers/build_site.py --only l2-swath-geolocation --skip-assets` builds; inspect
  `_site/l2-swath-geolocation/index.html` (Playwright screenshots of each methods page and a
  scripted slider interaction to confirm the OJS widgets run without console errors).

</details>

## User

[Request interrupted by user for tool use]

## Claude

No response requested.

## User

> The HDF4 route is a dead end for now: the parser crashes on both products, and the one sidecar that parses hits the same string fill-value bug, so remote MODIS reads will fall back to download-then-read. I'm checking the locator benchmark next.

When done everything else, try to resolve this. Vendor virtualizarr or whatever else you need as a shallow submodule clone; then, inspect the source and try to modify it to make it work. First, do the solution bluntly (breaking changes OK; ignore irrelevant code paths); then, once you've solved it, figure out the smallest possible patch that resolves the problems without breaking or degrading other Virtualizarr functionality. If multiple options are feasible, describe them all and present to me (with your recommendation fix and why).

## Claude

That HDF4 work is already done; summary below. First I'll restart the remaining benchmark steps that the worker restart interrupted, so they run while I report.

- **Bash**: `cd /home/user/simon-code-research/l2-swath-geolocation && ps aux | grep -E "bench|chain|netsim|footprints" | grep -v grep | wc -l; nohup data/chain4.sh > /dev/…`

The benchmarks are running again. Your HDF4 request was already done earlier in this session; here's where it stands.

**Root causes (8, all fixed):**
- **kerchunk:**
  - Uncompressed contiguous HDF4 arrays aren't recorded, which gives MYD03's `KeyError: 'data'`.
  - HDF4 float types are decoded as little‑endian, but HDF4 stores them big‑endian. Every float array and float attribute comes out byte‑swapped, i.e. silently corrupted.
- **VirtualiZarr:**
  - The HDF4 parser doesn't CF‑encode `_FillValue`.
  - It applies zlib to every array, including uncompressed ones.
  - It rejects char arrays.
  - It rejects 3‑D variables.
  - The DMR++ parser ignores `byteOrder="BE"`.
  - String fill values such as `"NA"` and `"n/a"` on numeric variables make the whole file unreadable. This is the same bug that hit VNP21.

**Blunt fix:** done in the vendored submodules. All five test files read bit‑identical to pyhdf/h5py: MYD03 (45 variables), MYD11_L2, MOD11_L2, the MOD11_L2 DMR++ sidecar, and VNP21. MODIS now also works through icechunk in the read benchmark.

**Minimal options** (details in `patches/README.md`):
- **A — fix each bug where it lives.** kerchunk +11/−3 lines; VirtualiZarr +33/−5 lines in 4 files.
- **B — VirtualiZarr only.** Works with the released kerchunk by adding two guarded work‑arounds (+46/−5). The guards become no‑ops once kerchunk is fixed.
- **C — monkeypatch from user code.** Possible, but brittle; I didn't build it.

Both A and B pass three new regression tests that fail on stock. In the VirtualiZarr parser, writer and manifest test suites, their failure lists are identical to stock apart from those three tests, so no regressions.

**Recommendation:** Option A, as two small upstream PRs. The kerchunk float bug corrupts data for anyone using kerchunk directly, so it should be fixed at the source. Keep Option B's guards in VirtualiZarr until a fixed kerchunk release is pinned.

Now finishing the rest. While the benchmarks run, I'll do the light housekeeping: trim the vector exports and add `publish.toml`.

- **Bash**: `ls -la results/vectors | awk '{print $5, $9}' | sort -n | tail -12; du -sh results/vectors`

Keeping county‑sized vector exports out of git (they'll go to `data/vectors/`), which brings the committed vectors down to ~3 MB:

- **Bash**: `python3 - <<'EOF' p='scripts/20_footprints.py'; s=open(p).read() old=''' small = len(idx) < 20000 outdir = VEC if small else VEC_FULL''' assert old in s s=s.re…`

Making the site task install its own tools in CI and git‑ignoring the copied build inputs:

- **Bash**: `python3 - <<'EOF' p='mise.toml'; s=open(p).read() s=s.replace('''run = [ "rm -rf report/data report/figures",''','''run = [ "mise install", "rm -rf report/data…`

Waiting for the resumed read benchmark (remaining ECOSTRESS full‑granule combinations), then the Part B rerun and DMR++ rebuild.

- **Bash**: `until grep -q "readbench exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log; do sleep 30; done; date; grep -E "^ecostress +full" /home/us…`
- **Bash**: `grep -E "^ecostress +full" /home/user/simon-code-research/l2-swath-geolocation/data/bench_read.log | cut -c1-150 | tail -3; date`
- **Bash**: `until grep -q "readbench exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log; do sleep 30; done; date`
- **Bash**: `grep -E "^ecostress +full" /home/user/simon-code-research/l2-swath-geolocation/data/bench_read.log | cut -c1-150 | tail -3; date`
- **Bash**: `until grep -q "readbench exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log; do sleep 30; done; date; tail -1 /home/user/simon-code-resea…`
- **Bash**: `cat /home/user/simon-code-research/l2-swath-geolocation/data/chain.log | grep exit; grep -E "^ecostress +full" /home/user/simon-code-research/l2-swath-geolocat…`

The read benchmark is on its very last combination (ECOSTRESS full granule, icechunk over the simulated NCCS portal). Part B rerun follows automatically.

- **Bash**: `until grep -q "footprints2 exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log; do sleep 20; done; grep exit /home/user/simon-code-researc…`

Read benchmark complete. While Part B reruns, generating the read figures and pulling the headline numbers:

- **Bash**: `nice -n 19 ~/.local/bin/mise exec -- pixi run python scripts/40_figures.py read 2>&1 | tail -1; nice -n 19 ~/.local/bin/mise exec -- pixi run python -c " impor…`

Clear picture for Part C. Checking one read figure renders sensibly:

- **Read**: `l2-swath-geolocation/figures/read_window_site.png`
- **Bash**: `python3 - <<'EOF' p='scripts/40_figures.py'; s=open(p).read() i=s.index('def read_figs():'); j=s.index("if __name__ == \"__main__\":") new='''PROFILE_COLOR = {…`
- **Read**: `l2-swath-geolocation/figures/read_window_site.png`
- **Bash**: `until grep -q "footprints2 exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log; do sleep 20; done; grep exit /home/user/simon-code-researc…`
- **Bash**: `tail -3 data/footprints2.log | cut -c1-200; wc -l results/synthetic_errors.csv; date`

Part B rerun is in the areal step (the NNLS weights are slow for the county‑sized MODIS subsets). Waiting.

- **Bash**: `until grep -q "footprints2 exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log; do sleep 20; done; grep exit /home/user/simon-code-researc…`
- **Bash**: `tail -2 data/footprints2.log | cut -c1-120; date`
- **Bash**: `pkill -f data/chain4.sh; pkill -f 20_footprints.py; sleep 1; sed -i 's/ max_pixels=8000):/ max_pixels=2500):/' src/swathgeo/psf.py && grep -n "max_pixels=2500"…`

While Part B runs, writing the Part C narrative. Pulling the virtual‑build numbers:

- **Bash**: `nice ~/.local/bin/mise exec -- pixi run python -c " import pandas as pd, numpy as np; pd.set_option('display.width',250) v=pd.read_csv('results/virtual_build.c…`

Big DMR++ result: building ECOSTRESS GEO references from the sidecar takes 0.6 s and 1.6 MB in‑region, versus 15.7 s and 264 MB scanning the HDF5 file. Writing the Part C narrative:

- **Bash**: `python3 - <<'EOF' p='report/read.qmd'; s=open(p).read() s=s.replace('''**Bottom line.** <!-- C-BOTTOM -->''','''**Bottom line.** For **subsets** (a site, a cou…`

Waiting for the Part B rerun (now in the 200‑polygon synthetic step soon).

- **Bash**: `until grep -q "footprints2 exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log; do sleep 20; done; grep exit /home/user/simon-code-researc…`
- **Bash**: `tail -2 data/footprints2.log | cut -c1-100; ls -la results/synthetic_errors.csv results/areal_means.csv; date`
- **Bash**: `until grep -q "footprints2 exit" /home/user/simon-code-research/l2-swath-geolocation/data/chain.log; do sleep 20; done; grep exit /home/user/simon-code-researc…`
- **Bash**: `nice ~/.local/bin/mise exec -- pixi run python -c " import pandas as pd, numpy as np; pd.set_option('display.width',250) s=pd.read_csv('results/synthetic_error…`
- **Bash**: `nice ~/.local/bin/mise exec -- pixi run python scripts/40_figures.py 2>&1 | grep -E "^(ok|skip)|Error"`
- **Read**: `l2-swath-geolocation/figures/areal_synthetic.png`

Fixing the overlapping log‑axis tick labels:

- **Bash**: `python3 - <<'EOF' p='scripts/40_figures.py'; s=open(p).read() old=''' ax.set_xticks([2, 5, 10, 20], ["2", "5", "10", "20"])''' assert old in s s=s.replace(old,…`
- **Read**: `l2-swath-geolocation/figures/areal_real.png`

Moving the legend out of the data in the real‑LST figure:

- **Bash**: `python3 - <<'EOF' p='scripts/40_figures.py'; s=open(p).read() old=''' axes[2].legend(loc="lower right", fontsize=7.5) fig.suptitle("Real LST: how much does the…`
- **Bash**: `nice ~/.local/bin/mise exec -- pixi run python -c " import pandas as pd, numpy as np v=pd.read_csv('results/virtual_build.csv'); d=v[v.parser=='dmrpp'] print(d…`
- **Bash**: `python3 - <<'EOF' p='report/footprint.qmd'; s=open(p).read() s=s.replace('''**Bottom line.** <!-- B-BOTTOM -->''','''**Bottom line.** Simple spherical-Earth tr…`

Fixing one wording issue (200 polygons × 5 scenes, not 1,000 polygons), then rendering the site and checking every page in a headless browser:

- **Bash**: `sed -i 's/through real MODIS\/VIIRS geometry, 1,000 polygons)/through real MODIS\/VIIRS geometry; 200 polygons × 5 scenes)/' README.md && grep -c "200 polygons…`

All eight pages load with no console or OJS errors. A visual check of the footprint results page (the interactive map) and the bow‑tie widget fix:

- **Bash**: `cd /tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad && /home/user/simon-code-research/l2-swath-geolocation/.pixi/en…`
- **Read**: `/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad/fp_mid.png`
- **Bash**: `cd /home/user/simon-code-research/l2-swath-geolocation && python3 - <<'EOF' p='report/footprint.qmd'; s=open(p).read() old='''fpTarget = ({type: "FeatureCollec…`
- **Read**: `/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad/fp_map.png`

Frame gone. But the 3 km square looks like a parallelogram: the azimuthal projection is centred at 0°N 0°E, so California is heavily distorted. Centring the projection on the target:

- **Bash**: `cd /home/user/simon-code-research/l2-swath-geolocation && python3 - <<'EOF' p='report/footprint.qmd'; s=open(p).read() old='''Plot.plot({width: 640, height: 52…`
- **Read**: `/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad/fp_map.png`

The square now looks square, and the 4.8 × 2 km swath‑edge footprints overlap as expected. Running the test suite and the repository's site build check:

- **Bash**: `pkill -f "http.server 8765"; cd /home/user/simon-code-research/l2-swath-geolocation && ~/.local/bin/mise run test 2>&1 | tail -3; cd .. && timeout 900 uv run _…`

All 9 tests pass and the repository's site builder produces the page with its colophon. Committing in logical pieces:

- **Bash**: `git status --short | grep -v "^ m" | head -40; du -sh l2-swath-geolocation/results l2-swath-geolocation/figures; find l2-swath-geolocation -path '*/.pixi' -pru…`

No file over 2 MB; committed results total ~9 MB. Committing:

- **Bash**: `T=" Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com> Claude-Session: https://claude.ai/code/session_01W8w7tXbVNX8oCFug8CGrtd" && git add l2-swath-geoloc…`

Now the transcript:

- **Bash**: `uv run _helpers/transcript.py -o l2-swath-geolocation/TRANSCRIPT.md 2>&1 | tail -3; wc -c l2-swath-geolocation/TRANSCRIPT.md; grep -n -i -E "password|token|sec…`

Transcript is clean (no credentials or personal data). Committing it, then finishing the CLAUDE.md git workflow: rebase onto `origin/main`, fast‑forward and push `main`, delete the branch.

- **Bash**: `git add l2-swath-geolocation/TRANSCRIPT.md && git commit -q -m "l2-swath-geolocation: add TRANSCRIPT.md Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>…`
- **Bash**: `git checkout -q main && git merge --ff-only exp/l2-swath-geolocation 2>&1 | tail -1 && git push origin main 2>&1 | tail -2`

`main` is pushed. Deleting the experiment branch locally and on origin:

- **Bash**: `git branch -d exp/l2-swath-geolocation && git push origin --delete exp/l2-swath-geolocation 2>&1 | tail -1; git status --short | head -3; git log --oneline -1`
- **Bash**: `git ls-remote --heads origin | cut -c42-`
- **Bash**: `git push origin :refs/heads/exp/l2-swath-geolocation 2>&1 | tail -2; git ls-remote --heads origin | cut -c42-`

The remote branch deletion was rejected by the session's git proxy. Checking the proxy notes:

- **Bash**: `grep -n -i -E "delet|ref|branch|hung up" ~/.ccr/README.md | head -20`
- **Bash**: `sed -n 55,90p ~/.ccr/README.md`
- **ToolSearch**: `select:mcp__github__actions_list,mcp__github__get_job_logs`
- **mcp__github__actions_list**: `{"method": "list_workflow_runs", "owner": "ashiklom", "repo": "simon-code-research", "perPage": 3}`

The deploy workflow is running. Updating the task list while it runs:

- **TaskUpdate**: `{"taskId": "4", "status": "completed"}`
- **TaskUpdate**: `{"taskId": "5", "status": "completed"}`
- **TaskUpdate**: `{"taskId": "7", "status": "completed"}`
- **mcp__github__actions_list**: `{"method": "list_workflow_jobs", "owner": "ashiklom", "repo": "simon-code-research", "resource_id": "42941852140"}`

The build job succeeded but took only 15 s, fast for installing Quarto and rendering. Checking the log to confirm the Quarto site really built:

- **mcp__github__get_job_logs**: `{"owner": "ashiklom", "repo": "simon-code-research", "job_id": 130265284481, "return_content": true, "tail_lines": 40}`

The uploaded site artifact is 5.3 MB, consistent with the full experiment site. Confirming the Quarto render lines in the build step:

- **mcp__github__get_job_logs**: `{"owner": "ashiklom", "repo": "simon-code-research", "job_id": 130265284481, "return_content": true, "tail_lines": 110}`

The CI artifact contains the full Quarto site (all pages, data, targets, vectors). Final check on the deploy job:

- **mcp__github__actions_list**: `{"method": "list_workflow_runs", "owner": "ashiklom", "repo": "simon-code-research", "perPage": 1}`
- **TaskUpdate**: `{"taskId": "6", "status": "completed"}`

The experiment is finished and merged to `main`, and the Pages deploy succeeded: https://ashiklom.github.io/simon-code-research/l2-swath-geolocation/

**One thing for you to do:** the session's git proxy refused to delete the remote branch `exp/l2-swath-geolocation`, so it's still on GitHub. Its contents are all in `main`.

#### HDF4 → virtual Zarr

MODIS HDF4 now works as virtual Zarr with patched VirtualiZarr and kerchunk. All five test files read back bit‑identical to pyhdf/h5py: MYD03 (45 variables), MYD11_L2, MOD11_L2, the MOD11_L2 DMR++ sidecar, and VNP21 with its `"n/a"` fill values. MODIS also ran through icechunk in the read benchmark.

There were eight separate bugs:
- **kerchunk:**
  - Uncompressed contiguous arrays are not recorded, which causes the `KeyError: 'data'` crash.
  - HDF4 floats are decoded as little‑endian when they are big‑endian. Float values and float attributes come out silently corrupted.
- **VirtualiZarr:**
  - `_FillValue` is not encoded for the HDF4 parser.
  - zlib is applied to every array, including uncompressed ones.
  - Char arrays are not supported.
  - Arrays with more than two dimensions are not supported.
  - The DMR++ parser ignores the big‑endian byte‑order flag.
  - A text fill value on a numeric variable makes the whole file unreadable.

**Options** (full write‑up in `patches/README.md`):
- **A — fix each bug where it lives.** kerchunk +11/−3 lines; VirtualiZarr +33/−5 lines in 4 files.
- **B — change VirtualiZarr only.** Works with the current kerchunk release through two guarded work‑arounds (+46/−5). The guards do nothing once kerchunk is fixed.
- **C — monkeypatch from your own code.** Possible but brittle; I didn't build it.

A and B both pass three new regression tests that fail on stock. Their upstream test‑suite failures are exactly the stock failures, minus those three tests, so nothing regressed.

**Recommendation:** Option A, as two small upstream PRs. The kerchunk float bug corrupts data for anyone using kerchunk directly, so it should be fixed at the source. Keep B's guards in VirtualiZarr until a fixed kerchunk is released.

#### Results

**Part A — finding pixels**
- Brute force costs 0.3–1.8 s per point. A KD‑tree takes 1–9 s and 0.4–1.7 GB to build, then answers in about 0.1 ms.
- xarray's default `NDPointIndex` picks the wrong pixel for 4–10 % of points. The xoak BallTree/S2 adapters fix this.
- The analytic method (orbit + scan geometry) needs no index. Calibrated once per platform, it found the right pixel within ±1/±2/±3 pixels (MODIS/VIIRS/ECOSTRESS) in all 53 test scenes from 2013 and 2024, when the target's elevation is known. Without elevation it needs ±3/±9/±16.
- ECOSTRESS only works with the ISS attitude data; the station flew pitched about 7°.

**Part B — pixel size and areal means**
- Simple trigonometry matches the real pixel sizes in the files (MODIS grows from 1 km to 4.8 × 2 km at the swath edge).
- In the synthetic test, counting overlapping scans correctly cut swath‑edge errors by 30–40 %. Plain Voronoi cells did as well as the full footprint model.
- Adding the PSF didn't improve areal means on average.
- On real LST, the choice of pixel model moved means by up to 0.9 K for a 3 km box, and by less than 0.1 K for polygons of 10 km and up.

**Part C — reading**
- **Small subsets:** icechunk virtual references are fastest on every simulated network (0.4–4 s, under 1 MB moved). Library defaults move 0.5–2 GB for the same 33 × 33 window.
- **Whole granules:** downloading the file is fastest.
- **Robustness gaps:** icechunk 2.3 doesn't retry transient server errors, and the ROS3 driver can't follow Earthdata's redirects.
- **DMR++ sidecars:** they build references in under 2 s, versus up to 2 minutes and 264 MB to scan the ECOSTRESS file directly.

#### Compromises

- **Read‑benchmark time limits:** each reader/network combination stopped repeating after 90 s. Full ECOSTRESS reads used only six readers. Default GDAL wasn't rerun for the ECOSTRESS county window on slow networks, because it had already timed out on the smaller window.
- **NNLS cap:** the least‑squares PSF weights are limited to subsets of up to 2,500 pixels, so the county rows show "–".
- **Big exports kept out of git:** county‑sized vector exports are in `data/vectors/`; no release was created.
- **Patched code not committed:** the vendored submodules are committed at their upstream tags; the patched versions live only in `patches/`.

The only uncommitted changes are the blunt edits inside the vendored submodule working trees. They're already saved as `patches/blunt-*.diff`, and the submodules are meant to stay at their upstream tags. I'll confirm the saved patches match exactly, then reset the submodule trees.

- **Bash**: `cd /home/user/simon-code-research/l2-swath-geolocation && for m in VirtualiZarr kerchunk; do f=patches/blunt-$(echo $m | tr A-Z a-z).diff; git -C vendor/$m dif…`
- **Bash**: `git -C vendor/VirtualiZarr checkout -- . && git -C vendor/kerchunk checkout -- . && cd .. && git status --short; git log --oneline -1; git status -sb | head -1`

The repository is now clean and `main` matches `origin/main`, so there was nothing left to commit or push. The only uncommitted changes were the blunt fixes inside the two vendored submodules (VirtualiZarr and kerchunk). I checked they match `patches/blunt-*.diff` byte for byte, then reset the submodules to their upstream release tags.

To get the patched versions back:

```bash
git -C l2-swath-geolocation/vendor/VirtualiZarr apply ../../patches/blunt-virtualizarr.diff
```

```bash
git -C l2-swath-geolocation/vendor/kerchunk apply ../../patches/blunt-kerchunk.diff
```

The remote branch `exp/l2-swath-geolocation` is still on GitHub because the session's git proxy refused the delete; everything in it is already in `main`.

## User

Kerchunk is in maintenance mode. Consider implementing HDF4 directly in Virtualizarr instead.

## Claude

Good point — with kerchunk in maintenance mode, the cleaner fix is a native HDF4 reader inside VirtualiZarr: parse the HDF4 tag/descriptor structure directly and build `ManifestArray`s, reading through VirtualiZarr's own obstore registry instead of kerchunk + fsspec. I'll build that as a new option, test it against everything so far plus new fixtures (including chunked and compressed layouts), and update the recommendation. First, branch setup and recording your message.

- **Bash**: `git fetch -q origin && git checkout -q -B exp/l2-swath-geolocation origin/main && git status -sb | head -1 && cat >> l2-swath-geolocation/PROMPT.md <<'EOF' ## …`

Now studying how VirtualiZarr's HDF5 parser reads bytes through the registry (to reuse the same reader machinery) and what the existing HDF4 tests expect:

- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; cd $S/vz-stock/virtualizarr && sed -n 440,500p parsers/hdf/hdf.…`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; cd $S/vz-stock/virtualizarr && sed -n 200,400p tests/test_parse…`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; cd $S/vz-stock && sed -n 70,90p pyproject.toml; grep -n "Reader…`

Using kerchunk's decoder as a format reference (MIT‑licensed; I'll write a fresh, smaller implementation with credit). Reading its tag decoders:

- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; sed -n 1,60p $S/kc-stock/kerchunk/hdf4.py; sed -n 330,500p $S/k…`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; sed -n 60,118p $S/kc-stock/kerchunk/hdf4.py`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; grep -n "^import\|^from" $S/vz-stock/virtualizarr/parsers/kerch…`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; cd /home/user/simon-code-research/l2-swath-geolocation && git -…`

Now writing the native HDF4 parser:

- **Write**: `/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad/vz-native/virtualizarr/parsers/hdf4.py`

Checking the translator helper's signature before testing:

- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; grep -n "def manifest_from_kerchunk_chunk_dict" -A30 $S/vz-nati…`
- **TaskCreate**: `{"subject": "Native HDF4 parser in VirtualiZarr (no kerchunk) — Option D", "description": "Implement, test on real files + VZ suite + new fixtures (chunked/com…`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; cd /home/user/simon-code-research/l2-swath-geolocation && PYTHO…`

Off‑by‑a‑factor bug in the NDG (tag list) decoding. Fixing and tidying that loop:

- **Edit**: `/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad/vz-native/virtualizarr/parsers/hdf4.py`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; cd /home/user/simon-code-research/l2-swath-geolocation && PYTHO…`
- **Edit**: `/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad/vz-native/virtualizarr/parsers/hdf4.py`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; sed -i 's/^_NULL, _COMPRESSED, _CHUNK = 1, 40, 61$/_NULL, _LINK…`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; mkdir -p $S/natcheck && cat > $S/natcheck/allvars.py <<'EOF' im…`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; cd /home/user/simon-code-research/l2-swath-geolocation && PYTHO…`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; sed -i 's/ arr = zarr.open_array(store, path=name, mode=.r.)/ i…`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; cd /home/user/simon-code-research/l2-swath-geolocation && PYTHO…`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; python3 - <<EOF p='$S/vz-native/virtualizarr/parsers/hdf4.py'; …`

All 220 datasets match (data and real dimension names), plus all variable attributes. The only mismatches are two long global string attributes. Checking how they differ:

- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; cd /home/user/simon-code-research/l2-swath-geolocation && PYTHO…`

The attribute holds several NUL‑separated strings; my decoder stopped at the first NUL. Changing it to keep the full declared length and strip only trailing NULs:

- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; python3 - <<EOF p='$S/vz-native/virtualizarr/parsers/hdf4.py'; …`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; grep -n 'split(b' $S/vz-native/virtualizarr/parsers/hdf4.py`
- **Edit**: `/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad/vz-native/virtualizarr/parsers/hdf4.py`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; cd /home/user/simon-code-research/l2-swath-geolocation && PYTHO…`

The remaining difference is only that pyhdf keeps a trailing NUL byte. Comparing with trailing NULs ignored:

- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; sed -i "s/ ok = (v == g) if isinstance(v, str)/ ok = (v.rstrip(…`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; cd /home/user/simon-code-research/l2-swath-geolocation && time …`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; cd /home/user/simon-code-research/l2-swath-geolocation && PYTHO…`

One remaining mismatch: a 2024 MYD03 attribute ends in stray `0xFF` bytes (not valid UTF‑8). I'll decode strictly as UTF‑8 and fall back to Latin‑1, which is lossless and matches pyhdf:

- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; python3 - <<EOF p='$S/vz-native/virtualizarr/parsers/hdf4.py'; …`
- **Edit**: `/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad/vz-native/virtualizarr/parsers/hdf4.py`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; sed -i 's/ return b\[pos + 2 : pos + 2 + n\].split(b"\\x00", 1)…`

The worker restarted during the 32‑file comparison. Checking what survived:

- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; ls $S | head -30; cd /home/user/simon-code-research && git stat…`

The parser edits survived and the repository is clean. Re‑running the full comparison as a detached background job so it survives restarts:

- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; cd /home/user/simon-code-research/l2-swath-geolocation && nohup…`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; cd $S/vz-native && grep -n "requires_kerchunk" virtualizarr/tes…`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; cd $S/vz-native && python3 - <<'EOF' p='virtualizarr/tests/test…`

Updating the FAQ line, then writing the new native‑parser tests (fixtures generated with pyhdf):

- **Bash**: ``S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; cd $S/vz-native && sed -i 's/| `open_virtual_dataset(..., parse…``
- **Write**: `/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad/vz-native/virtualizarr/tests/test_parsers/test_hdf4_native.py`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; cd $S/vz-native && PYTHONPATH=$S/vz-native timeout 600 nice /ho…`

The fixture writer fails; checking which pyhdf call it doesn't like:

- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; cd $S/vz-native && PYTHONPATH=$S/vz-native timeout 300 /home/us…`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; cd $S && /home/user/simon-code-research/l2-swath-geolocation/.p…`
- **Bash**: `/home/user/simon-code-research/l2-swath-geolocation/.pixi/envs/default/bin/python -c " import inspect; from pyhdf.SD import SDS; print(inspect.signature(SDS.se…`
- **Bash**: `/home/user/simon-code-research/l2-swath-geolocation/.pixi/envs/default/bin/python -c " from pyhdf.SD import SDS; print([n for n in dir(SDS) if 'chunk' in n.low…`

pyhdf doesn't wrap HDF4's chunking API, so I'll generate a small committed fixture through the HDF4 C library via `ctypes`, the way VirtualiZarr already ships `MOD14.hdf4`. Locating the library:

- **Bash**: `ls /home/user/simon-code-research/l2-swath-geolocation/.pixi/envs/default/lib/ | grep -E "mfhdf|libdf" ; cat /tmp/claude-0/-home-user-simon-code-research/cb779…`
- **Bash**: `ps aux | grep allvars | grep -v grep | wc -l; wc -c /tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad/natcheck/all32…`

Still running (output is printed at the end). Writing the chunked‑fixture generator against the HDF4 C API:

- **Write**: `/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad/vz-native/virtualizarr/tests/data/make_hdf4_chunked.py`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; E=/home/user/simon-code-research/l2-swath-geolocation/.pixi/env…`

The library needs `libdf` loaded globally first:

- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; E=/home/user/simon-code-research/l2-swath-geolocation/.pixi/env…`

Wrong flag constants: in the HDF4 headers `HDF_CHUNK = 0x1` and `HDF_COMP = 0x3`:

- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; E=/home/user/simon-code-research/l2-swath-geolocation/.pixi/env…`

The sparse‑chunk fixture's expectation is off; checking what pyhdf actually returns:

- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; E=/home/user/simon-code-research/l2-swath-geolocation/.pixi/env…`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; E=/home/user/simon-code-research/l2-swath-geolocation/.pixi/env…`

Fixture verified against the C library. Updating the tests: pyhdf‑generated fixtures for the non‑chunked layouts, the committed fixture for the chunked ones:

- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; cd $S/vz-native/virtualizarr/tests/test_parsers && python3 - <<…`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; cat $S/natcheck/all32.log | grep -v -i warn | tail -2; ps aux |…`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; PY=/home/user/simon-code-research/l2-swath-geolocation/.pixi/en…`
- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; P=/home/user/simon-code-research/l2-swath-geolocation/patches; …`
- **Bash**: `cd /home/user/simon-code-research/l2-swath-geolocation && python3 - <<'EOF' p='scripts/30_bench_read.py'; s=open(p).read() old='''def _virtual_build_worker(pro…`
- **Bash**: `git -C vendor/VirtualiZarr status --short | head -5; ps aux | grep "30_bench_read" | grep -v grep | wc -l; tail -3 data/bench_read_native.log`
- **Bash**: `until ! pgrep -f "build-parsers hdf4_native" >/dev/null; do sleep 10; done; cd /home/user/simon-code-research/l2-swath-geolocation && grep -v -i warn data/benc…`
- **Bash**: `git -C vendor/VirtualiZarr checkout -q -- . && git -C vendor/VirtualiZarr clean -q -fd && git -C vendor/VirtualiZarr status --short | wc -l && sed -n 40,75p pa…`
- **Bash**: `python3 - <<'EOF' p='patches/README.md'; s=open(p).read() i=s.index('### Option C'); j=s.index('## Test results') new='''### Option C — no fork: monkeypatch at…`

Verifying the two counts I quoted (parser length, number of new tests):

- **Bash**: `S=/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad; wc -l $S/vz-native/virtualizarr/parsers/hdf4.py; cd $S/vz-nativ…`
- **Bash**: `cd /home/user/simon-code-research/l2-swath-geolocation && sed -i 's/(~480 lines; the/(494 lines incl. docstrings; the/; s/a new ~480-line module/a new 494-line…`

Updating the README, results page and site data to mention the native parser:

- **Bash**: `python3 - <<'EOF' import re p='README.md'; s=open(p).read() old=s[s.index('* **MODIS HDF4 as virtual Zarr**'):s.index('Full write-up with methods pages')] s=s.…`

Committing (patch and write‑up separately from the prompt record, which is already committed):

- **Bash**: `cd /home/user/simon-code-research && ls -la l2-swath-geolocation/report/_site/read.html | awk '{print $6,$7,$8}'; T=" Co-Authored-By: Claude Opus 5.5 <noreply@…`

Regenerating the transcript to include this follow‑up, then merging to `main`:

- **Bash**: `uv run _helpers/transcript.py -o l2-swath-geolocation/TRANSCRIPT.md 2>&1 | tail -1; U=$(printenv EARTHDATA_LOGIN_USER); grep -c -- "$U" l2-swath-geolocation/TR…`
- **Bash**: `git branch -d exp/l2-swath-geolocation 2>&1 | tail -1; git push origin --delete exp/l2-swath-geolocation 2>&1 | tail -1; git ls-remote --heads origin | cut -c4…`

`main` is pushed and the working tree is clean. As before, the proxy won't let me delete the remote `exp/l2-swath-geolocation` branch. Checking the Pages deploy:

- **mcp__github__actions_list**: `{"method": "list_workflow_runs", "owner": "ashiklom", "repo": "simon-code-research", "perPage": 1}`
- **mcp__github__actions_list**: `{"method": "list_workflow_jobs", "owner": "ashiklom", "repo": "simon-code-research", "resource_id": "42944071894"}`
- **TaskUpdate**: `{"taskId": "8", "status": "completed"}`
- **mcp__github__actions_list**: `{"method": "list_workflow_runs", "owner": "ashiklom", "repo": "simon-code-research", "perPage": 1}`

I built the native reader you suggested: VirtualiZarr now reads HDF4 itself, with no kerchunk, and it's my new recommendation (Option D).

**What it does.** A new `parsers/hdf4.py` (494 lines) reads the HDF4 Scientific Data Set structure directly. It reads through VirtualiZarr's own object‑store reader, like the HDF5 parser, so it needs neither kerchunk nor fsspec. kerchunk is no longer a dependency for HDF4.
- **Storage it handles:** uncompressed contiguous arrays, deflate‑compressed arrays, and chunked arrays with or without deflate. Chunks that were never written read as the fill value stored in the chunk header.
- **Storage it refuses:** RLE, SZIP, JPEG and other codings, plus data split into linked blocks or external files, raise a clear `NotImplementedError`; `skip_variables` lets you open the rest of the file.
- **Fixed in passing:**
  - Floats come out in the correct byte order.
  - Attributes with several values keep all of them (kerchunk kept only the first).
  - Attributes made of several NUL‑separated strings stay intact.
  - MOD03's `Land/SeaMask` is no longer dropped: `/` in a name becomes `_`, and the original name is kept in an `hdf4_name` attribute.
- **New option:** `dimension_names="hdf4"` uses the dimension names stored in the file, so variables sharing a dimension line up. The default keeps the old `<variable>_x/_y` names.

**Checks:**
- **Against the HDF4 C library (pyhdf):** 32 MODIS granules (MOD03/MYD03 from 2013 and 2024, plus the LST files). That is 1,324 datasets compared on values and dimension names, and 4,652 attributes, with 0 mismatches.
- **VirtualiZarr test suite:** 510 passed, and the failure list is identical to stock apart from my three earlier regression tests, which now pass. The existing HDF4 tests run with the kerchunk requirement removed.
- **New tests:** 12, including a small committed chunked fixture (18 KB) written with the HDF4 C library, since pyhdf can't create chunked files.
- **Remote reference building:** for MYD03 over the simulated Earthdata HTTPS link it moves 35 MB in 16 s, versus 205 MB in 27 s for the patched kerchunk route.

**Recommendation:** send it as two VirtualiZarr PRs. The first carries the small fixes that aren't HDF4‑specific (big‑endian DMR++ and text fill values, about 20 lines). The second swaps the kerchunk wrapper for the native reader. Separately, the 2‑line kerchunk float‑byte‑order fix from Option A is still worth sending upstream, because anyone calling `kerchunk.hdf4` directly is getting silently corrupted floats. Options A and B remain in `patches/README.md` if maintainers want the smallest possible change.

**Two caveats:**
- The read benchmark's MODIS virtual repositories were built with the earlier kerchunk‑based patch. Reads don't depend on which parser built them, so I didn't rebuild them.
- The vendored submodules stay at their upstream tags. Option D is `patches/optionD-virtualizarr-native-hdf4.diff`.

Everything is merged to `main`. The Pages deploy was still running when I last checked; the previous identical build succeeded. The proxy again refused to delete the remote branch `exp/l2-swath-geolocation`, so you'll need to remove that by hand.

## User

The "analytic method in detail" description on the website is a bit hard to follow. For example, ECEF, and many of the constants (e.g., t_off), are not defined. Expand this section to make it easier to read, and add some simple figures/diagrams that clarify what the mathematical terms are.

## Claude

I'll rewrite that section with defined terms, a table of constants with their calibrated values, and a set of simple diagrams. First, setting up the branch and recording your request:

- **Bash**: `git fetch -q origin && git checkout -q -B exp/l2-swath-geolocation origin/main && cat >> l2-swath-geolocation/PROMPT.md <<'EOF' ## Follow-up 4 > The "analytic …`
- **Bash**: `cd /home/user/simon-code-research/l2-swath-geolocation && grep -n "## The analytic method in detail" -A 60 report/locate-methods.qmd | head -80`

Now the diagrams. I'm writing a separate script, `scripts/41_diagrams.py`, for schematic figures. Where numbers appear, they come from the calibrated constants in `results/analytic_models.json`.

- **Write**: `l2-swath-geolocation/scripts/41_diagrams.py`
- **Bash**: `~/.local/bin/mise exec -- pixi run python scripts/41_diagrams.py 2>&1 | tail -5; ls figures/diagram_*`

## User

*[Earlier context was compacted]*

## Claude

- **Read**: `l2-swath-geolocation/figures/diagram_scans.png`
- **Read**: `l2-swath-geolocation/figures/diagram_scan_plane.png`
- **Read**: `l2-swath-geolocation/report/locate-methods.qmd`
- **Edit**: `~/.claude/plans/experiment-l2-swath-geolocation-download-iterative-wilkinson.md`
- **ToolSearch**: `select:ExitPlanMode`

<details><summary><b>Proposed plan</b></summary>

# Plan: `l2-swath-geolocation`

## Follow-up 4 plan: readable "The analytic method in detail" (2026-11-11)

**Context.** The user found the section in `report/locate-methods.qmd` (lines 65–97) hard to follow:
ECEF and many constants (e.g. `t_off`) are never defined. Goal: expand it into a readable,
self-contained explanation with simple diagrams. Already done: branch `exp/l2-swath-geolocation`,
PROMPT.md commit (917bbd0), and a first draft of `scripts/41_diagrams.py` that renders 7 PNGs to
`figures/diagram_*.png` (ecef, scan_plane, scans, frames, index_maps, timing, refine) using
`swathgeo.plotstyle` and constants from `results/analytic_models.json`.

### Steps
1. **Polish diagrams** (`scripts/41_diagrams.py`): view every PNG and fix overlaps — e.g. in
   `diagram_scans` the φ−φ₀ label covers the "scan k" label and the y-axis label crowds the bottom
   (move the φ annotation left / above, shift the axes glyph); in `diagram_scan_plane` "local
   vertical" runs into the θ/η legend (move the legend right or the label left). Move the stray
   `AXIS_C = ps.AXIS` to the top of the file. Keep figures schematic, ≤ ~150 KB each.
   Add a `diagrams` task to `mise.toml` and include it in `figures`/`all`.
2. **Rewrite the section** in `report/locate-methods.qmd`, keeping the existing
   "Why a window, and how big?" widget after it:
   - *Plain-language overview* (what "inverse geolocation" means: predict line/sample from target
     lat/lon instead of searching), then a short **glossary**: ECEF/ECR (with `diagram_ecef`),
     ECI/J2000 & GCRS, nadir, line of sight, scan / detector / line / sample, scan angle θ,
     along-track angle φ, view zenith η, slant range, roll/pitch/yaw, quaternion, bow-tie.
   - *Step by step*, one subsection per step with its figure: geometry (`diagram_scan_plane`,
     `diagram_scans`), frame (`diagram_frames`; per-sensor source: MODIS `T_inst2ECR`, VIIRS orbital
     frame from `orb_pos/vel` with inertial velocity v + ω×S, ECOSTRESS ISS quaternions rotated
     J2000→ECEF), angles (θ = atan2(u_y,u_z), φ = asin(u_x), sign conventions), timing
     (`diagram_timing`: t_scan = scan start time from the file, t_off, κ, s), indices
     (`diagram_index_maps`: j = j_c + sθ/α, VIIRS native→aggregated, d = d_c + (φ−φ0)/δ,
     line = k·N_det + d, in-swath test), candidate scans + refinement (`diagram_refine`).
   - **Constants table**: symbol, meaning, units, where the spec value comes from, spec value, and
     calibrated values for Terra/Aqua/SNPP/NOAA-20/ISS (from `results/analytic_models.json`;
     N_det, N_samp, α, j_c, s, δ, d_c, φ0, κ, t_off, pitch, yaw; note roll is degenerate with j_c).
   - Keep the calibration/53-scene validation paragraph, reworded with the newly defined terms.
   - Use `<sub>`/Unicode rather than `$…$` math outside OJS (avoids the Pandoc/OJS `$` clash);
     check `src/swathgeo/analytic.py` so every formula matches the code (signs, s, t_scan meaning).
3. **Render & check**: `mise run site`; Playwright screenshot of `locate-methods.html` (images load,
   no console/OJS errors, widget still works); `uv run _helpers/build_site.py --only
   l2-swath-geolocation --skip-assets` passes.
4. **Commit** (prefix `l2-swath-geolocation: `, trailer lines): diagrams script + figures + mise
   task; methods page rewrite. Regenerate TRANSCRIPT.md (`uv run _helpers/transcript.py -o
   l2-swath-geolocation/TRANSCRIPT.md`, skim/redact) in its own commit.
5. **Git**: push branch, fetch, rebase onto `origin/main`, fast-forward + push `main`, delete local
   branch; try deleting the remote branch (the session's git proxy refused this before — report if so).
   Check the "Deploy site" Actions run succeeds.

### Verification
- All 7 diagrams viewed after fixes: no overlapping text, labels legible.
- Every symbol used in the section is defined in the glossary or constants table (grep the section
  for `t_off`, `κ`, `j_c`, `ECEF`, etc.).
- Rendered page shows all figures; zero console errors; deployed page updated.

---

## Resume plan (after the session worker restart, 2026-11-11 00:18 UTC)

The original plan (below) is implemented. The restart killed the background pipeline
(`data/chain4.sh`) part-way through the **last** read-benchmark task. Status:

- Done & committed: data, targets, Part A (locators + 53-scene analytic consistency), Part B
  first pass, network simulator + read harness, methods pages, the HDF4/VirtualiZarr work
  (blunt patch + minimal Options A/B with regression tests and upstream-suite comparison,
  `patches/README.md`), README draft, root README line.
- Interrupted: `results/read_bench.csv` has everything except the rest of **ECOSTRESS `full`**
  (stopped at `s3_cross_region`); not yet run: Part B rerun (NNLS "PSF-optimal" weights, VIIRS
  bow-tie exclusion, 200 synthetic polygons) and the DMR++ virtual-build rerun (group-name fix).
- The user's repeated message about the HDF4 dead end is already handled (Follow-up 2 in
  PROMPT.md; the patches exist). No new work needed beyond presenting the options at the end.

### Remaining steps

1. **Finish benchmarks** (sequential, background, one at a time so timings stay clean):
   `30_bench_read.py --steps read` (resumes; only remaining ECOSTRESS-full combos run) →
   `20_footprints.py areal synthetic` → `30_bench_read.py --steps build --build-parsers dmrpp`.
2. **Figures + site data**: `scripts/40_figures.py` (all steps). Keep only small vector exports
   in `results/vectors/` (box/circle; move county-sized `.fgb` to `data/vectors/`); no release
   needed (nothing > ~4 MB the site requires) — if that changes, ask first.
3. **Write-up**: fill the `<!-- … -->` placeholders in `report/index.qmd`, `footprint.qmd`,
   `read.qmd` and `README.md` (key results) from the final CSVs; mention the time-budget rules
   (90 s per combination, ECOSTRESS-full reader subset, default-GDAL skip on slow profiles for the
   ECOSTRESS county window) and the icechunk no-retry finding.
4. **Render & check**: `mise run site`; Playwright screenshots of every page, no console/OJS
   errors; `uv run _helpers/build_site.py --only l2-swath-geolocation --skip-assets` passes.
5. **Tests**: `mise run test` (core tests incl. netsim) passes.
6. **Record**: update PLAN.md with this plan (own commit); TRANSCRIPT.md via
   `uv run _helpers/transcript.py -o l2-swath-geolocation/TRANSCRIPT.md` (skim/redact);
   `publish.toml` (build = `mise run site`, output = `report/_site`, models, tools).
7. **Git**: commit in logical pieces (prefix `l2-swath-geolocation: `), push branch, fetch,
   rebase on `origin/main`, fast-forward + push `main`, delete `exp/l2-swath-geolocation` locally
   and on origin. Leave the vendored submodules at their upstream tags (patches live in `patches/`).
8. **Report back**: summary of results + the HDF4 fix options with the recommendation
   (Option A upstream in kerchunk + VirtualiZarr, keeping Option B's guards until a fixed kerchunk
   is released).

### Verification
- `results/read_bench.csv` has rows for every (sensor, task, profile, reader) combination that
  the harness selects; `results/synthetic_errors.csv` has 200 polygons × 5 scenes incl. `err_psf_lsq`.
- Site renders; footprint page loads `areal_means.csv`/`synthetic_errors.csv` without OJS errors.
- `scripts/50_hdf4_virtual_check.py` with `PYTHONPATH=vendor/...` (blunt patch) still prints ALL OK.

## Context

Extracting values from L2 *swath* products (curvilinear lat/lon, no grid) for points and
polygons is a recurring pain point. This experiment benchmarks how to (a) find the right
pixels (naive search, KD-tree, S2, H3, analytic inverse geolocation from orbit/scan geometry),
(b) represent what a pixel actually "sees" (view-angle-dependent footprint + point spread
function), and how much that matters for areal averages, and (c) read the data efficiently
(direct, GDAL, virtual Zarr/icechunk, DMR++, …) locally and under simulated network profiles.
MODIS, VIIRS and ECOSTRESS are deliberately different: whiskbroom with bow-tie overlap and
~2×5 km edge pixels (MODIS), on-board aggregation zones and bow-tie deletion (VIIRS), and a
70 m, ±25.5° ISS-mounted scanner (ECOSTRESS).

Decisions from Q&A: LST products for all sensors; I choose a CONUS same-day overlap region;
Quarto report site; follow CLAUDE.md git workflow (`exp/l2-swath-geolocation` → main).

Verified in the sandbox: Earthdata credentials (`EARTHDATA_LOGIN_USER/PASSWORD`) work for
LP DAAC and LAADS HTTPS downloads; CMR reachable; DMR++ sidecars exist (e.g. VNP21 `.nc.dmrpp`);
conda-forge and GitHub release-asset downloads work; mise is not installed yet (install via
mise.run). No real S3 in-region access → network behaviour is simulated (as requested).

## Data

| Sensor | L2 product | Geolocation | Format |
|---|---|---|---|
| MODIS Terra (+Aqua if useful) | MOD11_L2 v061 (LST, 1 km) | MOD03 v6.1 (1 km, incl. orbit pos/vel, attitude per scan) | HDF4 |
| VIIRS SNPP | VNP21 v002 (LST, 750 m M-band) | VNP03MOD v2 (incl. navigation data) | NetCDF4/HDF5 |
| ECOSTRESS | ECO_L2_LSTE v002 (70 m) | ECO_L1B_GEO v002 | HDF5 |

- `scripts/00_find_granules.py`: CMR search for a clear-sky summer day where all three overlap
  a chosen CONUS site; pick ~2 granules per sensor: site near nadir and site near swath edge
  (ECOSTRESS: whatever overlaps). Write chosen granule IDs/URLs to `config/granules.toml`
  (committed, so download is reproducible).
- `scripts/01_download.py`: earthaccess/requests with env-var credentials → `data/raw/`
  (git-ignored). Also fetch `.dmrpp` sidecars where present.
- Targets (`config/targets/`, committed, tiny): 1 flux-tower point (e.g., an AmeriFlux site in
  a heterogeneous landscape inside the overlap); 100 random points (fixed seed) inside the
  3-sensor common footprint; one ~30–50 km watershed (HUC) or county polygon (GeoJSON).

## Layout

```
l2-swath-geolocation/
  README.md PROMPT.md PLAN.md TRANSCRIPT.md publish.toml
  mise.toml            # pins pixi, quarto; tasks: download, locate, footprint, psf, readbench, site, all
  pixi.toml pixi.lock  # python + gdal(hdf4/hdf5 plugins) + pyhdf + h5py/h5netcdf + xarray + scipy
                       # + pykdtree + xoak + scikit-learn + pys2index/s2sphere + h3 + shapely/geopandas/pyogrio + virtualizarr
                       # + icechunk + kerchunk + fsspec/aiohttp + moto[server] + earthaccess + matplotlib
  config/              # granules.toml, targets/*.geojson, net_profiles.toml, psf.toml
  src/swathgeo/        # library code (readers, locators, footprint, psf, netsim, bench utils)
  scripts/             # numbered pipeline steps calling src/
  results/             # committed small CSV/Parquet tables of timings & accuracy
  figures/             # PNGs (in git if small; else release assets)
  report/              # Quarto project (index.qmd + sections), renders results/figures only
  data/                # git-ignored raw granules + derived indexes
```

## Part A — Pixel location / subsetting benchmarks (`src/swathgeo/locate/`)

Common interface `Locator.build(lat, lon)` / `.query_points(pts)` / `.query_polygon(poly)`,
returning (row, col) indices + distance. Timed separately: load geolocation, build index,
query (1 point, 100 points, polygon). Repeated runs (timeit-style, median + IQR), memory peak.

1. **Naive**: vectorized haversine/ECEF distance argmin over full arrays (numpy); plus
   `xarray` 2-D approach (note `sel(method="nearest")` doesn't work on curvilinear coords with
   default indexes — document); polygon via bbox prefilter + shapely `contains_xy` on centers.
2. **KD-tree**: scipy `cKDTree` and `pykdtree` on ECEF unit vectors (avoids dateline/pole issues).
2b. **xarray-native indexes**: [xoak](https://xoak.readthedocs.io/) (`ds.xoak.set_index` /
   `ds.xoak.sel`) with each of its backends (scipy KD-tree, sklearn BallTree/haversine,
   pys2index S2), plus xarray's built-in `NDPointIndex` (custom-index API that enables
   `sel(method="nearest")` on 2-D coords) if available in the pinned xarray. Evaluate both
   **performance** (build/query, same harness) and **usability**: lines of code, API
   ergonomics, dask/lazy support, polygon support (or lack thereof), handling of out-of-swath
   points, maintenance status/compatibility with current xarray. Summarised as a table.
3. **S2**: `pys2index` S2PointIndex (C++); polygon via S2 cell covering (s2sphere/`spherely`)
   then exact test.
4. **H3**: `h3` v4 — index pixel centers at resolution matched to pixel size, cell→pixel lookup
   (sorted array + searchsorted), point query with k-ring fallback; polygon via
   `polygon_to_cells` with a buffer for partial pixels.
5. **Analytic inverse geolocation**: use orbit position/velocity per scan (MOD03 `orb_pos/orb_vel`,
   VNP03 navigation data; ECOSTRESS: from L1B_GEO metadata if present, else derive a ground track
   from the nadir-most column) to (i) find the scan/line whose scan plane contains the target,
   (ii) compute scan angle satellite→target, (iii) map to sample index (MODIS linear in angle;
   VIIRS piecewise through 3:1/2:1/1:1 aggregation zones; ECOSTRESS linear), (iv) local
   refinement using the real lat/lon in a k×k window around the analytic guess. Report accuracy
   vs KD-tree truth (exact-hit rate, row/col offset distribution, distance error) and speed
   (needs no index; reads only a small window of geolocation).
   - **Neighbourhood size**: not fixed at 3×3. From the analytic-vs-truth offset distribution,
     choose the smallest window that contains the true pixel with ~100% (report p99/p99.9/max
     offsets) — i.e. the largest error we can *reliably* bound — separately for rows/cols and
     per sensor; report the read-cost/accuracy trade-off vs window size.
   - **Consistency across scenes**: a separate geolocation-only scene set (just MOD03 /
     VNP03MOD / ECO_L1B_GEO, no L2) spanning very different locations (tropics, mid-lat N & S,
     high latitude, near-dateline), ascending/descending orbits, and epochs: MODIS Terra & Aqua
     ~2012–2015 vs 2023–2025 (post-constellation-exit orbit drift: lower altitude, shifted
     equator-crossing time), VIIRS SNPP vs NOAA-20, ECOSTRESS across ISS altitude changes
     (reboosts). Show whether a single parameter set (altitude, IFOV, scan rate) works or
     per-granule parameters from the orbit vectors are required, and how window size must grow.

All methods must also report "is the point inside the swath at all" and handle MODIS bow-tie
(multiple scans covering a point → return all candidates, choose nearest center).

## Part B — Pixel footprints & PSF (`src/swathgeo/footprint.py`, `psf.py`)

- **Trigonometric footprint model** (spherical Earth, altitude h, IFOV): scan angle θ →
  Earth-central angle β = asin((R+h)/R·sinθ) − θ; along-scan size = R·IFOV·dβ/dθ, along-track
  size = slant range · IFOV_track. Sensor params in `config/psf.toml` (MODIS 705 km, ±55°,
  1 km@nadir; VIIRS 829 km with aggregation zones; ECOSTRESS ~400 km ISS altitude from metadata,
  ±25.5°). Validate against empirical spacing between neighbouring pixel centers and against
  view zenith in the geolocation files; plot size vs scan angle per sensor.
- **Voronoi tessellation** (relevant: it is exactly the partition implied by nearest-neighbour
  extraction): spherical Voronoi (`scipy.spatial.SphericalVoronoi`, or planar Voronoi in a
  local equal-area projection for speed) of pixel centers for the target subsets. Compare
  Voronoi cell area/shape vs the trig footprint model: they agree away from edges, but Voronoi
  cells are non-overlapping, so in MODIS bow-tie overlap regions they shrink/fragment while the
  true footprints overlap, and they ignore the PSF. Voronoi is also used as an extra weighting
  scheme in the areal-average comparison and as a vector export option.
- **Vector export**: per-pixel quadrilaterals oriented along scan/track directions (from
  local Jacobian of the lat/lon grid, scaled by the model size) → GeoParquet + FlatGeobuf for
  the target subsets (small subsets committed/released; full-granule export via a task, not
  committed). Also a "naive" export (nominal square at center) for comparison.
- **PSF research** (web: ATBDs, literature): MODIS — triangular along-scan × rectangular
  along-track (Nishihama/Wolfe MOD03 ATBD; Tan et al. 2006; Campagnolo & Montaño 2014 Gaussian
  approx); VIIRS — pre-launch LSF/MTF & aggregation effects (VIIRS SDR/geolocation ATBD,
  Wolfe et al. 2013); ECOSTRESS — L1 ATBD/MTF spec. Encode as parametric 2-D PSFs in pixel
  coordinates, with citations in `config/psf.toml` and the report. Where only MTF is given,
  derive a Gaussian-equivalent and state the assumption.
- **Areal averages**: for the polygon (plus 2–3 extra representative polygons: small vs large,
  near nadir vs swath edge), compute LST means with weights from (1) naive equal-size pixels
  (center-in-polygon / nominal-square area fraction), (1b) Voronoi-cell area fraction, (2) true footprint area fraction,
  (3) footprint ⊗ PSF energy fraction (numerical integration on a fine sub-pixel grid).
  Plus a **synthetic-truth test**: high-res synthetic LST field (e.g., land-cover-like
  patches), simulate each sensor's observation via PSF at real geometry, recover polygon mean
  with each weighting → error vs known truth. Figures: weight maps, bias by method/sensor/
  scan position.

## Part C — Read performance (`src/swathgeo/readers/`, `netsim/`)

Read tasks: (1) full LST + lat/lon arrays, (2) point extraction (geolocation + single pixel),
(3) polygon window. Readers:
- direct: `pyhdf` (HDF4) / `h5py` (HDF5/NetCDF4); `xarray` + `h5netcdf`/`netCDF4`
- GDAL: `osgeo.gdal` HDF4/HDF5 drivers, `/vsicurl/` and `/vsis3/` for remote (with tuned
  `GDAL_*` cache/merge options as a variant)
- fsspec + h5py (HTTP/S3) with block-cache variants (none/readahead/blockcache, block sizes)
- VirtualiZarr → icechunk (virtual refs to original files), read via xarray/zarr; HDF4 via
  kerchunk HDF4 or DMR++ parser if possible — failure documented as a result if not
- DMR++ sidecar → VirtualiZarr (no file-scan needed), kerchunk JSON refs as baseline
- (optional) earthaccess `open()` style for parity with common user code

**Network simulator** (`netsim`): local `moto` S3 server holding the granules + a Python
asyncio reverse proxy that injects per-request latency (TTFB), connection setup cost,
per-connection and aggregate bandwidth caps, jitter, stalls, and 5xx errors, serving both S3
API and plain HTTP Range requests — so GDAL, fsspec, h5py and icechunk all do *real* network
I/O. Profiles in `config/net_profiles.toml` (values justified from published AWS/Earthdata
measurements where findable; otherwise stated assumptions):
1. `s3-in-region`: ~20–40 ms TTFB, ~80–100 MB/s per connection
2. `s3-cross-region`: ~80–150 ms TTFB, ~20–50 MB/s
3. `earthdata-https`: extra redirect round-trips on first request (URS → CloudFront → signed
   S3), ~100–300 ms TTFB, ~10–30 MB/s
4. `nccs-portal`: heavy-tailed latency (lognormal, p99 multi-second), random bandwidth
   1–50 MB/s, occasional stalls and ~1–2% 5xx needing retries
Metrics per run: wall time, # requests, bytes transferred (from proxy logs); repeated runs,
distributions shown (especially for nccs). Also report the raw local baseline.

## Report & publishing

- Quarto website in `report/` (pinned via mise), rendering only committed `results/` tables
  and `figures/` (no Python execution in CI; pre-rendered matplotlib PNGs).
  `publish.toml`: `build = "mise run site"`, `output = "report/_site"`.
- Pages: overview/results (`index.qmd`) + for **each part a results page and a dedicated
  methods page** describing the method in detail (equations, sensor parameters, citations).
  Methods pages carry client-side interactive explainers using Quarto's built-in Observable JS
  (runs in the browser; nothing to execute in CI; small JSON/CSV inputs only), e.g.:
  - Locate: toy swath where you click a target and step through naive / KD-tree / S2 / H3 /
    analytic search (cells visited, candidates); H3/S2 resolution slider vs pixel size.
  - Footprint: sliders for altitude, IFOV, scan angle → footprint size/shape (spherical trig),
    MODIS bow-tie overlap and VIIRS aggregation-zone visualisation; Voronoi vs true footprint
    toggle on a real subset (Leaflet/Observable Plot map of exported pixel polygons).
  - PSF: PSF shape explorer per sensor (triangular×rect, Gaussian, MTF-derived) and a
    polygon-weight demo showing naive vs footprint vs PSF weights and the resulting mean.
  - Read/network: profile simulator — sliders for latency, bandwidth, jitter, concurrency →
    predicted read time per reader, driven by the measured request counts/bytes logs, shown
    next to the actual measured distributions.
- README: question, headline results, `mise run all`, Pages link. Root README line added.
- Release `l2-swath-geolocation`: only if figures/vector exports are too large for git —
  **I'll ask before creating/uploading, listing files and sizes.**
- PROMPT.md (verbatim prompt + my Q&A), PLAN.md (this plan), TRANSCRIPT.md via
  `uv run _helpers/transcript.py -o l2-swath-geolocation/TRANSCRIPT.md` at the end.

## Git

Branch `exp/l2-swath-geolocation`; commits per logical step prefixed
`l2-swath-geolocation: `; PROMPT.md/PLAN.md in their own commits; push regularly. At the end:
fetch, rebase onto `origin/main`, fast-forward and push `main`, delete branch locally and on
origin.

## Verification

- Unit-ish checks (`pytest` in `tests/`): footprint model reproduces MODIS ~2×4.8 km and VIIRS
  ~1.6 km edge sizes; Voronoi cell areas match model areas away from bow-tie/edges; all
  locators (incl. xoak backends) agree with brute force on the 100 points (excluding
  documented analytic misses); weights sum to ~1 and footprint/PSF integrals are normalized;
  netsim proxy delivers configured latency/bandwidth within tolerance (self-test).
- `mise run all` end-to-end from downloaded data produces `results/` + `figures/`.
- `uv run _helpers/build_site.py --only l2-swath-geolocation --skip-assets` builds; inspect
  `_site/l2-swath-geolocation/index.html` (Playwright screenshots of each methods page and a
  scripted slider interaction to confirm the OJS widgets run without console errors).

</details>

- **Read**: `l2-swath-geolocation/figures/diagram_ecef.png`
- **Read**: `l2-swath-geolocation/figures/diagram_frames.png`
- **Read**: `l2-swath-geolocation/figures/diagram_index_maps.png`
- **Read**: `l2-swath-geolocation/figures/diagram_timing.png`
- **Read**: `l2-swath-geolocation/figures/diagram_refine.png`
- **Bash**: `grep -n "def \|atan2\|arcsin\|t_off\|kappa\|cross\|omega\|OMEGA\|scan_start\|ev_mid\|quat\|n_c\|VIIRS_" src/swathgeo/analytic.py | head -120; wc -l src/swathge…`
- **Bash**: `sed -n 1,34p src/swathgeo/analytic.py; sed -n 60,90p src/swathgeo/analytic.py; sed -n 104,240p src/swathgeo/analytic.py`
- **Bash**: `grep -rn "time\b\|time=\|EV_start\|ev_mid\|scan_start\|att_ang\|body2ecef\|line_time" src/swathgeo/readers*.py src/swathgeo/swath*.py 2>/dev/null | head -40; l…`
- **Bash**: `grep -n "EV start\|EV_start\|ev_mid\|scan_start\|start_time\|att_\|body2\|quatern\|J2000\|gcrs\|GCRS\|time\[" src/swathgeo/io.py | head -40`
- **Bash**: `grep -n "EV start\|EV_start\|EV center\|t =\|time=" src/swathgeo/io.py | head -20`

Polishing the seven diagrams now (fixing overlapping labels), then I'll rewrite the methods section.

- **Bash**: `python3 - <<'EOF' import re p="scripts/41_diagrams.py"; s=open(p).read() s=s.replace('''BLUE, ORANGE, GREEN, RED, VIOLET = ps.CAT[0], ps.CAT[1], ps.CAT[2], ps.…`

Now rework the refine diagram so the pixel grid is visible and labels sit outside the windows.

- **Bash**: `python3 - <<'EOF' p="scripts/41_diagrams.py"; s=open(p).read() a=s.index("def fig_refine():"); b=s.index("if __name__") new='''def fig_refine(): """Prediction,…`
- **Read**: `l2-swath-geolocation/figures/diagram_refine.png`
- **Read**: `l2-swath-geolocation/figures/diagram_scans.png`
- **Read**: `l2-swath-geolocation/figures/diagram_timing.png`
- **Read**: `l2-swath-geolocation/figures/diagram_scan_plane.png`
- **Bash**: `python3 - <<'EOF' p="scripts/41_diagrams.py"; s=open(p).read() s=s.replace("T = np.array([2.1, nd * hgt + 2.6 * hgt])","T = np.array([2.1, nd * hgt + 3.55 * hg…`
- **Read**: `l2-swath-geolocation/figures/diagram_timing.png`
- **Read**: `l2-swath-geolocation/figures/diagram_scans.png`

Diagrams look clean. Now the mise task and the page rewrite.

- **Bash**: `grep -n "^\[tasks\|run =\|depends" mise.toml`
- **Bash**: `sed -n 32,35p mise.toml && python3 - <<'EOF' p="mise.toml"; s=open(p).read() s=s.replace('run = "pixi run python scripts/40_figures.py"','run = ["pixi run pyth…`
- **Bash**: `python3 -c " import json,math M=json.load(open('results/analytic_models.json')) for k,m in M.items(): print(k, m['sensor'], 'a=%.4e jc=%.2f s=%d d=%.4e dc=%.1f…`

Now the rewrite of the section (lines 65–97).

- **Bash**: `grep -n "!\[" report/locate-methods.qmd | head; grep -n "^#" report/locate-methods.qmd`
- **Bash**: `cat > /tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad/analytic_section.md <<'EOF' ## The analytic method in detail…`
- **Bash**: `sed -n 237,290p src/swathgeo/analytic.py`
- **Bash**: `python3 - <<'EOF' p="report/locate-methods.qmd"; s=open(p).read() old="""The window is clipped at scan edges, because pixels in the next scan are not neighbour…`
- **Bash**: `cd /home/user/simon-code-research/l2-swath-geolocation/report/_site && cat > /tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/…`
- **Read**: `/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad/am2.png`

The page renders cleanly (all 7 diagrams load, no console/OJS errors), but the 10-column constants table is cramped. Splitting it into a definitions table and a compact values table.

- **Bash**: `cd /home/user/simon-code-research/l2-swath-geolocation && python3 - <<'EOF' p="report/locate-methods.qmd"; s=open(p).read() a=s.index("| Symbol | Meaning | Uni…`
- **Read**: `/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad/am2.png`
- **Bash**: `cd /home/user/simon-code-research/l2-swath-geolocation && python3 - <<'EOF' p="report/locate-methods.qmd"; s=open(p).read() old="""| pitch, yaw | extra rotatio…`
- **Read**: `/tmp/claude-0/-home-user-simon-code-research/cb779936-c969-5010-9e11-3af4c0652b45/scratchpad/am1.png`

Page reads well. Running the site build check, then committing.

- **Bash**: `cd /home/user/simon-code-research && uv run _helpers/build_site.py --only l2-swath-geolocation --skip-assets 2>&1 | tail -3; git status --short | head -20`
- **Bash**: `git branch --show-current && T=$'\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_01W8w7tXbVNX8oCFug…`

Now regenerate the transcript, then merge to main.

- **Bash**: `uv run _helpers/transcript.py -o l2-swath-geolocation/TRANSCRIPT.md 2>&1 | tail -2; grep -ciE "[redacted]|[redacted]|EARTHDATA_LOGIN_PASSWORD=[^.]" l2-swath-geoloca…`
- **Bash**: `grep -niE "[redacted]|[redacted]|EARTHDATA_LOGIN_PASSWORD=[^.]" l2-swath-geolocation/TRANSCRIPT.md | cut -c1-200`
- **Bash**: `uv run _helpers/transcript.py -o l2-swath-geolocation/TRANSCRIPT.md --redact [redacted] --redact [redacted] 2>&1 | tail -1; grep -ciE "[redacted]|[redacted]" l2-swath-ge…`
