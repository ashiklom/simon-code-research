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


---

# Follow-up plan (2026-11-17): S3 storage, new credentials, volume-limited datasets

Approved in plan mode; shared across air-quality-data-comparison, climate-product-compare,
aws-emulator-tofu and l2-swath-geolocation. The original plan for this experiment is above.


## Context

The session now has credentials it lacked before. All of these were checked with read-only probes:
- OpenAQ, NEON, AmeriFlux and Earthdata all return 200. The CDS and ADS token works, and ADS shows `cc-by` and `terms-of-use-ads` accepted.
- AWS works through Cognito `credential_process` profiles in `~/.aws/config`:
  - `ycgs-all-buckets-reader` is the default profile.
  - `ycgs-all-buckets-writer` is the "read-write-cost" user.
  - `ycgs-cost-monitor` covers costs.
- `ycgs-use1-public` is public in two ways:
  - Through CloudFront at `$YCGS_PUBLIC_BUCKET_URL`. This sends `ACAO: *` and serves byte ranges (206), so hyparquet and Icechunk HTTP reads work.
  - Directly on S3 as requester-pays.
- `ycgs-aws-misc` is private and bucket-owner-pays.
- Neither bucket has versioning or lifecycle rules.

Experiments this affects:
- **air-quality-data-comparison (AQ)**
  - CAMS EAC4 and the CAMS forecast were skipped, because ADS returned 403. Readers exist in `src/aqc/products/cams.py`.
  - OpenAQ reference monitors, AirGradient and AirQo were skipped for lack of a key. OpenAQ also carries AirQo as a provider, so no separate AirQo token is needed.
  - Because of that, Tier 2 has only 104 sites and Tier 3 only 60 Sensor.Community sensors.
  - Site data is 433 MB in 6,688 files in the assets repo, pinned at `d9d0f12`.
  - Only 2023 is published at hourly resolution, to keep the repo small.
- **climate-product-compare (CPC)**
  - NEON (28 towers) and AmeriFlux (13 sites) are wired but have never run.
    - The code reads `NEON_API_TOKEN` and `AMERIFLUX_EMAIL`.
    - The environment provides `NEON_API_KEY` and `AMERIFLUX_USER_EMAIL`, so the code must accept both names.
  - PRISM is 4 km only. A measured 800 m daily file is 19 MB (ppt) or 52 MB (temperature/VPD), about 175 MB per day for 4 core variables. It downloads at about 10 MB/s.
  - ERA5 lags by a quarter, because the free Earthmover copy is used.
  - Site data is 576 MB in 1,224 files in the assets repo, pinned at `2a480a7`.
- Both AQ and CPC already support Icechunk stores on `s3://…` (writes) and `https://…` (CloudFront, reads) via `AQC_STORE` / `CPC_STORE`, `store.py:_storage()`, and `store-copy`.
  - The original stores (AQ about 15 GB, CPC 13 GB) were local and are **gone**.
  - Writing them to S3 means re-running extraction.
- **l2-swath-geolocation**: S3 behaviour was simulated with moto plus a throttling proxy, and the virtual-Zarr Icechunk repos stayed local.
- **aws-emulator-tofu**: several Cognito-identity → role → S3 findings are marked "unverified against AWS". The org's live Cognito identity pool is the same pattern.

Goal:
1. Move the site data from the assets repo to S3/CloudFront.
2. Ingest the newly unblocked sources.
3. Store the extraction stores durably in S3, at the cost tiers the user picks.
4. Add a few datasets that volume previously ruled out.

## Storage cost tiers

Prices are for us-east-1:
- S3 Standard: $0.023/GB-month.
- Intelligent-Tiering (IT): about $0.004/GB-month after 90 days without access. IT is for stores over 100 GB with chunks of at least 128 KB.
- CloudFront: the first 1 TB per month is free.
- Reading a store out of AWS from here costs about $0.09/GB per full read.

| Tier | Contents | Size | $/month |
|---|---|---|---|
| 0 | Site data for AQ and CPC (replaces the assets repo), plus the full AQ hourly record and the new sites | 1 GB now, 3–5 GB after | < $0.15 |
| 1 | Rebuilt site-extract Icechunk stores for AQ and CPC, including new sites and products (~35 GB), raw observation caches in the private bucket (~5–15 GB), and l2-swath granules plus virtual stores (~8 GB) | ~50–60 GB | ~$1.3 |
| 2a | PRISM 800 m **site extractions only**, common window, in the CPC site store. No CONUS grid. | < 1 GB (in Tier 1) | ~0 |
| 2b | CAMS EAC4 global gridded store, **complete record 2003-01→2025-12**, 12 AQ surface variables (pm2p5, pm10, go3, no2, so2, co, plus dust, sea salt, OM, BC, sulphate, nitrate at the lowest level), plus a **gridMET full-record CONUS** optimized store | 66–140 GB + 51–75 GB ≈ 120–215 GB | ~$0.5–0.9 idle / $2.8–5 hot |
| 3 | (not chosen) TB-scale stores | — | — |
| — | Not stored: PRISM 800 m CONUS grid, PRISM 4 km CONUS grid, the CAMS forecast grid (site extracts only), ERA5, ERA5-Land, HRRR, IMERG, CHIRPS, Daymet and CHELSA grids | | |

**User's choices:**
- Tiers 0, 1, 2a (site extracts only) and 2b (CAMS EAC4 12 variables full record plus gridMET), all **Intelligent-Tiering**.
- Total: about 175–280 GB, an estimated **$1–2/month** once idle and up to about $6/month while hot.
- **CAMS EAC4 estimate:**
  - 241×480 cells × 67,208 3-hourly steps gives 7.8e9 values per variable.
  - At an assumed 0.7–1.5 B/value, that is 66–140 GB for 12 variables.
  - This is the riskiest number. Measure B/value on the first year written, and stop and ask if the full-record projection exceeds 140 GB by more than 50 %.
  - Fetching it takes about 276 months × 2 ADS requests (surface and model level 60), about 200–300 GB downloaded and streamed. ADS queue time dominates.
- **CAMS forecast:** site extracts only.
- **How IT gets applied:**
  - The aws CLI and `publish_s3.py` upload with `--storage-class INTELLIGENT_TIERING`.
  - Icechunk writes set `StorageSettings(storage_class="INTELLIGENT_TIERING")`, checked in step 0.
  - Objects under 128 KB are billed at the Standard rate with no monitoring fee, which is fine.
  - Fallback if Icechunk can't set it: rewrite the store's storage class in place with the aws CLI.
  - **Before any in-place storage-class rewrite, or a similar per-object bulk operation, of about 100K objects or more (about $0.50), stop and warn the user.** Count the objects first with `aws s3 ls --summarize`.
  - I will not change bucket lifecycle or other bucket config, because both buckets are managed by OpenTofu in `ycgs-lab/ycgs-aws-infra`.
- A size check runs after each upload. If a store would exceed its estimate by more than 50 %, I stop and ask.
- Full re-run of extraction into S3.
- **Assets repo:** these two experiments' files stay there untouched. The repo stays documented in CLAUDE.md as a last resort, not deprecated. Its README gets a short note that these two experiments now read from S3, and I ask before pushing that.
- Both enhancements to the other experiments are included.

## Layout and conventions (new)

- **Public data:** `s3://ycgs-use1-public/simon-code-research/<folder>/`
  - `site-data/<vYYYYMMDD-hash8>/…` is immutable, with `Cache-Control: public, max-age=31536000, immutable`. The site pins it through `VITE_DATA_BASE=$YCGS_PUBLIC_BUCKET_URL/simon-code-research/<folder>/site-data/<v>`.
  - `stores/<kind>-<name>.icechunk` holds the Icechunk repos. They pin by snapshot ID, recorded in the README.
  - `README.md` describes the contents, licences/attribution and readers.
- **Private data:** `s3://ycgs-aws-misc/simon-code-research/<folder>/cache/…` holds raw downloads, so no redistribution question arises.
- **Shared helper:** `_helpers/publish_s3.py` (uv inline script) handles uploads.
  - Uploads use the writer profile and set the content type.
  - It computes a content-hash version, writes `site/.env.production`, and prints the size, object count and estimated $/month.
  - With `--prune`, it deletes older `site-data/` versions after the new pin is on `main`.
  - This replaces both experiments' `scripts/publish_site_data.sh`, through a mise task `publish-site-data`.
- **Credentials:** the env `AWS_ACCESS_KEY_ID` is a proxy placeholder.
  - For Icechunk and obstore, run with `AWS_PROFILE=ycgs-all-buckets-writer`, or use `eval "$(aws configure export-credentials --profile … --format env)"`.
  - Step 0 checks that requester-pays as owner works without `x-amz-request-payer`.
- **CLAUDE.md:** add an "S3 / CloudFront" section covering the layout above.
  - Large files go to S3, using Intelligent-Tiering.
  - Releases stay for small figures.
  - Ask before uploading, listing files and sizes, as for releases.
  - Warn before bulk per-object operations of ≥ 100K objects.
  - Keep "Assets repo (last resort)" as is, with one line saying S3 is preferred over it.

## Work items

### 0. Infrastructure (branch `claude/sharp-cannon-82c4l5`)
- Install mise.
- Run a write, read, range and delete probe in a scratch prefix with the aws CLI and with Icechunk.
- Add `_helpers/publish_s3.py`.
- Update CLAUDE.md.

### 1. Move site data from the assets repo (Tier 0)
- `add_repo ashiklom/simon-code-research-assets` (read), then a sparse clone at the pinned SHAs.
- Upload with `publish_s3.py`.
- Repoint `.env.production`.
- Update the "Publishing the site data" README sections and the `publish.toml` comments.
- Build with `uv run _helpers/build_site.py --only <folder>`, then check in Playwright that the map and a site's time series load from CloudFront.
- Assets repo: add a README note only, with permission asked before pushing.

### 2. CPC: unblocked sources, PRISM 800 m, ERA5 recent months
- `src/cpc/obs/neon.py` and `ameriflux.py` accept both env-var names. Run their readers for the first time on 2 sites, fix them, then `cpc obs --networks neon,ameriflux`.
- ERA5 fill from 2026-07 to the present via the CDS `reanalysis-era5-single-levels-timeseries` point dataset, appended to the `era5` series and flagged in metadata.
- **gridMET CONUS store (Tier 2b)** goes in `stores/conus-gridmet.icechunk`.
  - Source: annual per-variable NetCDFs from the gridMET HTTP server, 1979→now. About 50–115 GB downloaded, roughly 3 h.
  - Same quantization and pcodec as the site store, with (time, y, x) chunks of (366, 64, 64) or larger.
  - Written one variable-year at a time, staying within the ~30 GB disk allowance. Raw files are deleted after each year.
  - New code in `src/cpc/conus_store.py`, with the CLI `cpc conus-store gridmet`.
- Re-extract every product with `CPC_STORE=s3://ycgs-use1-public/simon-code-research/climate-product-compare/stores`.
  - Field products cost the same regardless of site count, so a full re-run costs about as much as adding sites. Estimate 15–25 h.
- Then run `metrics`, `figures`, `sitedata` and `publish-site-data`, and update the README key results, data sources, limitations, storage table and Tier 2 counts.
- **PRISM 800 m site extractions are deferred to the end of the plan** (step 6), because a better cloud-optimized copy may become available.

### 6. Last: PRISM 800 m site extractions (CPC)
- Before starting, check with the user whether a cloud-optimized copy is now available.
- Add product `prism800`, with `src/cpc/products/prism.py` parameterised by resolution. Sample the sites only, over the common window, and store nothing gridded.
- **Fallback source:** the PRISM daily zips, about 175 MB per day for ppt/tmin/tmax/tmean, roughly 450 GB streamed over about 12 h at 10 MB/s.
  - Use 3–4 parallel downloads.
  - Each file is read in memory and discarded.
- Then rerun metrics, sitedata and publish for CPC, and update the README.

### 3. AQ: CAMS, OpenAQ, AirGradient, AirQo, full hourly site data
- Run CAMS EAC4 and the CAMS forecast with the existing readers.
  - Fetch the global surface fields by year and month through `cdsapi` against ADS.
  - Extract the sites for the 4 scored variables.
  - EAC4 also streams the 12-variable global fields into `stores/global-cams_eac4.icechunk` over the complete record, 2003-01 → 2025-12.
    - The two products share one pass: each monthly download feeds both.
    - Raw NetCDFs are deleted after each month.
    - Chunk sizes are measured on the first year.
  - The CAMS forecast is site extracts only.
  - Add the 8 extra EAC4 variables to the component comparisons against IMPROVE/CSN where they match (sulphate, nitrate, OM, BC, dust, sea salt). SO2 and CO are stored but not scored.
- New `src/aqc/obs/openaq.py`:
  - The v3 API lists locations (reference monitors, `monitor=true`; AirGradient and AirQo providers).
  - Hourly data comes from the public `openaq-data-archive` S3 (per-location daily csv.gz), cached privately.
  - Site selection reuses the existing thinning and record-length rules. The aim is about 400 Tier 2 reference sites outside the US, and about 150 Tier 3 low-cost sites (AirGradient and AirQo plus Sensor.Community).
- Recompute the Tier 4 "remote" points against the larger monitor set (`src/aqc/remote.py`).
- Re-extract all products for the expanded site list into `AQC_STORE=s3://…/air-quality-data-comparison/stores`. Estimate 30–40 h.
- Export hourly parquet for all years, not just 2023. `export_site.py` drops the 800 MB budget.
- Then run metrics, figures, sitedata and publish, and update the README and site text (CAMS and OpenAQ now included).

### 4. Other experiments (both selected)
- **l2-swath-geolocation:** upload the granules and virtual Icechunk repos to S3.
  - Re-run `scripts/30_bench_read.py` against real S3 (us-east-1, from this container) and CloudFront HTTPS, alongside the moto and throttle profiles.
  - Report measured versus simulated results.
  - Publish the virtual stores so readers can open them.
- **aws-emulator-tofu:** add real-AWS spot checks of the Cognito-identity findings through the live org pool. These calls are read-only:
  - an off-group role is refused;
  - the reader role is denied `PutObject`;
  - explicit and implicit deny are enforced on S3.
  - Record them in `findings.toml` as `aws_verified`.
  - It cannot deploy API Gateway, Lambda or CloudFront: the roles are scoped to buckets.

### 5. Wrap-up (per experiment, per CLAUDE.md)
- **PROMPT.md:** in each touched experiment, append a `## Follow-up: S3 + new credentials` entry with this prompt verbatim, plus my AskUserQuestion questions, options and answers.
- **PLAN.md:** append the approved plan verbatim as a new section, keeping the original experiment plan above it. Update the experiment README as well.
- **Commits:** PROMPT/PLAN updates go in their own commits.
- **Long runs** (re-extraction and CONUS stores) run in the background with resumable logs.
  - Order: CPC first, because it is shorter, then AQ, then the CAMS EAC4 global store, which is bounded by the ADS queue. PRISM 800 m comes last (step 6).
  - Each finished store is checked with `aws s3 ls --summarize` against its estimate.
- Run `uv run _helpers/transcript.py -o <folder>/TRANSCRIPT.md`.
- Update the root README summaries.
- Make one commit per logical change, prefixed `<folder>: `, and push the branch regularly.
- At the end: rebase onto `origin/main`, fast-forward `main`, push.
- Make one Cost Explorer call (`ycgs-cost-monitor`, about $0.01) after the uploads to confirm the S3 line items.

## Verification
- Step 0 probe passes: write, read, 206 range over CloudFront, delete.
- `build_site.py --only <folder>` passes for every touched experiment.
- Playwright on the built `_site`: no failed network requests, and data loads from `d3v5kb9d29awwb.cloudfront.net`.
- `aws s3 ls --summarize --recursive` per prefix matches the tier budget.
- Each experiment's `mise run test` passes.
- The NEON, AmeriFlux, OpenAQ and CAMS readers have unit tests on small real samples.
- Icechunk stores open read-only over the CloudFront HTTPS URL (`store.py` `https://` backend).
