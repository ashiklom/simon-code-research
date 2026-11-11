# l2-swath-geolocation: prompts

## Prompt

Experiment: l2-swath-geolocation.

Download a few representative L2 swath files from MODIS, VIIRS, and ECOSTRESS locally. Create a few subsetting targets: A single site (point); 100 site points; and a spatial polygon (all pixels that at least partially intersect the area, and the fraction of each pixel's area inside the polygon).

For each dataset and subsetting target, try the following subset methods: extract the point naively (e.g., xarray sel (method="nearest"); numpy.which; or similar); build a KD-Tree index and use to extract; build an S2 index and use to extract; same for Uber H3 index; try to estimate the pixel (or the pixel region) analytically based on information you can find about the orbit and observing geometry. Compare the performance of these methods (for index methods, measure building the index and using the index separately).

Come up with a way to capture the variability in pixel size with view geometry (i.e., pixels at swath edge are much bigger) based on trigonometry. Create a way to export pixels as vectors that approximately capture the true pixel size. Also, try to find some data on real point spread functions of these sensors (ATBD; literature; etc.). For a few representative areal averages, show the impact of naive pixel size assumptions (all pixels same size) vs. accounting for true pixel size vs. accounting for pixel size *and* incorporating point spread function. Note that MODIS, VIIRS, and ECOSTRESS have very different characteristics for these.

Also, compare several different methods for read performance --- direct read, something GDAL-powered, virtual Zarr (virtualizarr) via icechunk, and others. For these, compare performance locally; also, create mock readers that simulate performance degradations due to reading over network, with "profiles" for (1) direct S3 reads in region (higher latency; very good bandwidth); (2) direct S3 reads out-of-region (more latency); (3) HTTPS reads (e.g., similar performance characteristics to NASA Earthdata HTTPS URLs); (4) NASA GSFC NCCS Data portal (highly noisy/variable/unpredictable latency and bandwidth because of scaling issues).

## Claude: questions (AskUserQuestion)

1. **Products** — Which L2 product family should anchor the comparison? (All three sensors need a separate geolocation file for full-res lat/lon; MODIS C6.1 is HDF4, which complicates the virtual-Zarr path — that becomes a finding.)
   - LST everywhere (Recommended): MOD11_L2 + MOD03 (1 km), VNP21 + VNP03MOD (750 m), ECO_L2_LSTE + ECO_L1B_GEO (70 m). Same geophysical variable across sensors, so areal averages are comparable.
   - Geolocation + L1B radiance: MOD021KM/MOD03, VNP02MOD/VNP03MOD, ECO_L1B_RAD/ECO_L1B_GEO. Closer to what PSFs are characterized for, but not 'L2'.
   - Mixed L2 products: Whatever L2 is most representative per sensor (e.g., MOD04 aerosol, VIIRS cloud props, ECOSTRESS LST). Less comparable.
2. **Targets** — How should I choose the subsetting targets (1 point, 100 points, 1 polygon)? ECOSTRESS swaths are only ~400 km wide, so all targets must fall inside a scene where all three sensors overlap on the same day.
   - I pick a CONUS region (Recommended): I choose a same-day MODIS/VIIRS/ECOSTRESS overlap over a heterogeneous US landscape: a flux-tower site as the point, 100 random points in the common footprint, and a ~30–50 km watershed/county polygon. Plus granules where the site sits near nadir and near swath edge.
   - Real site network: 100 real sites (e.g., AmeriFlux/NEON). They span far more than one ECOSTRESS scene, so ECOSTRESS would need many granules.
   - I'll give you sites: You provide the point, the 100 sites, and the polygon.
3. **Site** — How should the experiment's Pages site be built?
   - Quarto report (Recommended): Quarto installed via mise, multi-section report rendered from committed results/figures (frozen, no analysis re-run in CI).
   - README only: No build step; README.md with embedded figures and tables becomes the page. Simplest, but a long README.
   - Static HTML from a Python script: A small script turns committed results into HTML pages.
4. **Branch** — CLAUDE.md says to work on `exp/l2-swath-geolocation` and finally fast-forward `main`, but this session was told to push only to `claude/wonderful-feynman-f097an`. Which should I do?
   - Session branch only (Recommended): Commit and push to claude/wonderful-feynman-f097an; you merge to main yourself.
   - Follow CLAUDE.md: Use exp/l2-swath-geolocation, then rebase onto origin/main, fast-forward main and push main, and delete the branch.

## Answer

1. LST everywhere (Recommended)
2. I pick a CONUS region (Recommended)
3. Quarto report (Recommended)
4. Follow CLAUDE.md

## Plan feedback (comments on the first plan draft)

On selected text:
> (note sel(method="nearest") doesn't work on curvilinear coords —
> document)

Also look into xoak ---https://xoak.readthedocs.io/en/latest/. Evaluate performance and usability.

On selected text:
> 3×3 neighbourhood

Neighborhood can be larger. Pick the largest neighborhood that you can reliably estimate. Consider testing on a few different scenes from very different locations/orbits and different points in time (MODIS orbit drifts year to year; especially, last few years relative to 5-10 years ago) to see how consistent this really is.

On selected text:
> empirical spacing between neighbouring pixel centers

Is Voronoi tesselation relevant here? If so, consider it too.

On selected text:
> Quarto project

For each part above, also include a dedicated "methods" page that describes the method in detail, along with interactive visuals / data simulators with UI widgets that help explain the relevant concepts, as appropriate.

## Plan approved

(Revised plan approved; see PLAN.md.)

## Follow-up 2

(Sent while Claude was reporting that MODIS HDF4 has no working virtual-Zarr path: "The HDF4 route is a dead end for now: the parser crashes on both products, and the one sidecar that parses hits the same string fill-value bug, so remote MODIS reads will fall back to download-then-read. I'm checking the locator benchmark next.")

> When done everything else, try to resolve this. Vendor virtualizarr or whatever else you need as a shallow submodule clone; then, inspect the source and try to modify it to make it work. First, do the solution bluntly (breaking changes OK; ignore irrelevant code paths); then, once you've solved it, figure out the smallest possible patch that resolves the problems without breaking or degrading other Virtualizarr functionality. If multiple options are feasible, describe them all and present to me (with your recommendation fix and why).

## Follow-up 3

> Kerchunk is in maintenance mode. Consider implementing HDF4 directly in Virtualizarr instead.

## Follow-up 4

> The "analytic method in detail" description on the website is a bit hard to follow. For example, ECEF, and many of the constants (e.g., t_off), are not defined. Expand this section to make it easier to read, and add some simple figures/diagrams that clarify what the mathematical terms are.
