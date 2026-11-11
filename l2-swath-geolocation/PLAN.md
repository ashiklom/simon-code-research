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
