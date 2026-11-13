# Plan: `climate-product-compare`

## Context
Goal: find out how well gridded weather/climate products reproduce station-observable near-surface quantities: air T (mean/max/min), precipitation, humidity, shortwave radiation, IR surface (skin) temperature, soil moisture/temperature, wind and snow.
- **Reference:** USCRN first. A pilot sample measures data volume and performance, then all stations.
- **Second stage:** several dozen high-quality non-USCRN stations, chosen to be as independent of the products' inputs as possible.
- **Third stage:** 100 station-remote points across climate × land-cover strata, products compared only with each other.
- **Outputs:** compact extracted time series (Icechunk + pcodec, quantized) and a static site where you click a site and compare series across products.

Decisions already made (from Q&A):
- **Period:** extract every product's full overlap with USCRN (2008-01-01 onward). Products are ranked on a shared window; per-product full-period stats are reported too.
- **Time scales:** hourly for sub-daily products; daily for all products, with stations aggregated to each product's own day definition; monthly derived from daily.
- **Coverage:** Alaska and Hawaii are included, and each product is compared only where it has data.
- **Site:** full daily series for every site, plus hourly series lazy-loaded per site-year and trimmed to fit the Pages size budget.
- **ERA5:** Earthmover's free copy, which is updated quarterly and lags by months, not days.
- **PRISM:** add the emSign root certificate for PRISM requests only.
- **NEON/AmeriFlux:** credentials come from environment variables. Those sources are skipped cleanly until the variables are set.
- **Storage:** develop against a local, **non-persisted** Icechunk store. The store backend can be switched to S3 or HTTPS (CloudFront + S3) later. Only small results and site data are committed or released, so extraction scripts must be resumable and idempotent.
- **Updates:** one command updates every dataset to its latest date. It fetches only the missing span plus any provisional-revision window, and skips datasets that are already current.
- **Products added after the first prompt:** NLDAS-2 LSM outputs, NLDAS-3 (checked; only beta forcing exists) and GEOS-FP for the last 12 months.

## Products and access paths (one per product; all probed from this container)

All products are normalized to UTC, with each value stamped at the **end** of its interval (the USCRN convention), and to SI-ish units: °C, mm, W m⁻², m³ m⁻³, %, m s⁻¹, Pa.

| Product | Source picked | Why / notes | Res, coverage | Variables |
|---|---|---|---|---|
| **ERA5** | Earthmover free Icechunk: `s3://earthmover-icechunk-era5/icechunkV2` (us-east-1, anonymous), group `single/temporal` | User's choice. Bit-identical to CDS; chunks are 8736 h × 12 × 12. | 0.25°, hourly, 1940 to roughly a quarter ago | t2m, d2m, tp, sp, u10/v10, ssrd, skt, stl1–4, swvl1–4, sd (confirm with `ds.data_vars`) |
| **ERA5-Land** | ECMWF CDS ARCO **geoChunked** Zarr: `https://arco.datastores.ecmwf.int/cadl-arco-geo-NNN/arco/reanalysis_era5_land/<group>/geoChunked.zarr`. Groups 007 T, 009 sp/tp, 008 wind, 010 radiation, 043 skt, 006 soil T, 005 soil water, 030 snow. Auth is a Bearer `CDSAPI_KEY` header. | As requested. Chunks are 33792 h × 4 × 8, about 5 reads per point-variable. Check the de-accumulation in the pilot. | 0.1°, hourly, 1950 to ~5 days ago | t2m, d2m, tp, sp, u10/v10, ssrd, strd, skt, stl1–4, swvl1–4, sde/snowc |
| **MERRA-2** | (a) NASA POWER MERRA-2 hourly Zarr, `s3://nasa-power/merra2/temporal/power_merra2_hourly_temporal_utc.zarr` (anonymous; chunks 70128 h × 5 × 5, native grid). (b) Earthdata **Cloud OPeNDAP** day-file box subsets of M2T1NXRAD (SWGDN) and M2T1NXLND (SFMC, RZMC). | No official Zarr exists. POWER is a native-grid copy (units converted); the pilot verifies one day against original files. HH:30-centred averages are shifted to end-of-hour. | 0.5°×0.625°, hourly, 1980 to ~1 month ago | T2M, T2MDEW, QV2M, RH2M, PS, U/V2M+10M, PRECTOTCORR, TS, TSOIL1–6, SNODP; SWGDN, SFMC, RZMC via OPeNDAP |
| **NLDAS-2 forcing** | Giovanni Time Series API, `api.giovanni.earthdata.nasa.gov/timeseries?data=NLDAS_FORA0125_H_2_0_<VAR>` (Earthdata bearer token) | No Zarr. Data Rods is retired; Giovanni is its replacement and takes about 9 s per 10-year series. Verify the timestamp convention with a lag correlation. | 0.125°, hourly, 1979 to ~5 days ago | Tair, Qair, PSurf, Wind_E/N, SWdown, Rainf |
| **NLDAS-2 LSMs** (Noah, VIC, Mosaic) | Giovanni API (`NLDAS_{NOAH,VIC,MOS}0125_H_2_0_<VAR>`). Fallback: Earthdata Cloud OPeNDAP per-granule CONUS subsets. | No ARCO copy. Volumetric soil moisture = SoilM / layer thickness. | 0.125°, hourly, 1979 to ~5 days ago | SoilM/SoilT by layer, AvgSurfT (+ VIC RadT), SWE, SnowDepth |
| **NLDAS-3** | **Not released** (no CMR collection; model outputs are "expected mid-2026" and absent). Stretch goal: the beta *forcing* on public AWS, `s3://nasa-waterinsight/virtual-zarr-store/NLDAS-3-icechunk` (daily) and Kerchunk `nasa-waterinsight/virtual/nldas3_hourly.parq` | Beta only, 2001–2023, 0.01°. Labelled "beta" everywhere it appears. | 0.01°, 2001–2023 | Tair, Qair, PSurf, wind, SWdown, Rainf |
| **GEOS-FP** (last 12 months) | NCCS **OPeNDAP** GDS aggregation, `opendap.nccs.nasa.gov/dods/GEOS-5/fp/0.25_deg/assim/tavg1_2d_{slv,flx,rad,lnd}_Nx`. Request **one day per call for CONUS/AK/HI boxes**, then sample sites locally. Times are computed from the index, because the `time` coordinate decodes 2 days late. | See the note below this table on why OPeNDAP rather than the NCCS portal. Window: 2025-11-01 → 2026-10-31, with a known model upgrade on 2026-02-26. | 0.3125°×0.25°, hourly | T2M, QV2M, PS, U2M/V2M, U10M/V10M, TS, PRECTOT, SWGDN, SFMC, RZMC, TSOIL1–4, TSURF, SNODP, SNOMAS |
| **HRRR** | dynamical.org `noaa-hrrr-analysis` Icechunk (us-west-2, anonymous). The href is read from `stac.dynamical.org/noaa-hrrr-analysis/collection.json`. | ARCO; chunks are 2160 h × 45 × 45. Precipitation is the 0–1 h forecast from the previous run. Many hours are missing before 2018-08. Winds are grid-relative and get rotated. | 3 km LCC, hourly, 2014-10 to present | T2m, Td2m, RH2m, psfc, 10 m wind, SW down, SWE, snow depth, precip |
| **PRISM** | Original daily **4 km AN81d** zipped COGs, `data.prism.oregonstate.edu/time_series/us/an/4km/<var>/daily/YYYY/...zip`. Downloaded once per file with a cache index. TLS uses ccr bundle + emSign Root CA G1 (fingerprint-verified, committed `certs/`), for PRISM hosts only. Test 800 m at USCRN sites over the common window if in-zip range reads work. | No daily Zarr exists anywhere; the USGS one is monthly only. 4 km is about 140 GB streamed; 800 m whole files would be about 2 TB. | 4 km, daily (12Z–12Z), 1981 to present | ppt, tmin, tmax, tmean, tdmean, vpdmin/max (+ solar if available) |
| **GridMET** | USGS OSN Zarr, `s3://mdmf/gdp/gridMET.zarr` (endpoint `usgs.osn.mghpcc.org`, anonymous; chunks 2190 × 150 × 150). The tail after 2026-07-21 and VPD come from northwestknowledge THREDDS OPeNDAP over HTTPS. | Fast Zarr. PC's Zarr ends in 2020 and is chunked badly for points. | 1/24°, daily (ends 07Z), 1979 to present | tmmx, tmmn, pr, rmax, rmin, sph, srad, vs, vpd |
| **Daymet V4R1** | ORNL DAAC Earthdata Cloud NetCDF, `data.ornldaac.earthdata.nasa.gov/protected/daymet/Daymet_Daily_V4R1/data/daymet_v4_daily_{na,hi}_<var>_YYYY.nc`. HTTPS byte-range reads through h5netcdf/earthaccess. | PC's Zarr is V4 (not R1) and stops at 2020. daymet.ornl.gov and its THREDDS time out from here. | 1 km LCC, daily, 365-day calendar, 1980–2025 | tmax, tmin, prcp, srad, vp, swe |
| **CHELSA** | CHELSA-daily v2.1 COGs, `os.unil.cloud.switch.ch/chelsa02/chelsa/global/daily/<var>/YYYY/...tif` (anonymous). One windowed read per tile per day. Full period if pilot throughput allows, otherwise the common window. | The only CHELSA product with daily data through 2025. | 30″, daily, 1941 to ~2025-09 | tas, tasmax, tasmin (06–06 UTC), hurs, rsds, sfcWind, ps, prec; `pr` (GPCC-corrected) 1979–2019, analysed separately |
| **CHIRPS v3** | dynamical.org `ucsb-chc-chirps-analysis-final` Icechunk (rnl/ERA5-disaggregated; chunks 365 × 60 × 60) | ARCO. The original `sat` variant is not needed. | 0.05°, daily (UTC), 1981 to ~2 months ago | precipitation |
| **IMERG Final V07** | GES DISC OPeNDAP box subsets. GPM_3IMERGDF daily for the full period; GPM_3IMERGHH half-hourly for the common window, extended if throughput allows. | No time-series-chunked Final copy exists. V07 Final **ends 2025-09-30**, and V08 is not yet published. | 0.1°, half-hourly / daily | precipitation |
| **IMERG Late** (added) | dynamical.org `nasa-imerg-analysis-late` Icechunk (chunks 1440 × 100 × 100) | Cheap ARCO, and the only IMERG run that covers the GEOS-FP window. Kept clearly separate from Final. | 0.1°, half-hourly, 1998 to present | precipitation |

Why OPeNDAP rather than the NCCS portal for GEOS-FP: the NCCS HTTPS portal holds full global files, about 2.3 TB per year for slv+flx+rad+lnd. The portal returned 503 and FLUID returned 502 during research. The portal is the fallback for any collection whose OPeNDAP aggregation fails.

**Neighbourhoods.** For every product, store the **2×2 stencil of pixels that encloses the site**. Nearest-neighbour is one of the four, and bilinear (and inverse-distance) interpolation use all four. Also store each pixel's centre lat/lon, the product's elevation where available, and the pixel's distance to the site. A 3×3 block would make site extracts about 2.25× larger (about 30 GB); this container has about 30 GB of free disk.

## Storage volume estimates per product
Sizes are orders of magnitude, with ranges where uncertain. Assumptions:
- Original sizes use the native format's typical packing: GRIB about 2 B/value, NetCDF4 deflate, COG.
- The "optimized" columns assume per-variable quantization (see the compression study) plus pcodec in Icechunk, chunked for time series. That averages about 0.7 B/value for continuous fields (range 0.4–1.2) and about 0.3 B/value for precipitation.
- The **sites** column assumes about 320 sites × 4 stencil pixels, each product from 2008 (or its start) to its end, hourly where available.
- Global products are counted globally, except ERA5-Land and CHELSA, which count land pixels only.
- The pilot measures the actual bytes per value and the report updates this table.

| Product | Complete, all vars (original) | Complete, used vars (original) | Complete, used vars, optimized Icechunk | Optimized, sites only |
|---|---|---|---|---|
| ERA5 (17 vars, hourly 1940–) | ~0.3–0.5 PB single-level (~5 PB incl. pressure/model levels) | 25–55 TB | 8–20 TB | 1.5–4 GB |
| ERA5-Land (17 vars, hourly 1950–) | 0.3–0.6 PB | 15–30 TB | 5–12 TB | 1.5–4 GB |
| MERRA-2 (~19 vars, hourly 1980–) | 0.3–1 PB (all collections); 2D hourly collections ~30–40 TB | 2.5–6.5 TB | 1–2.5 TB | 1.5–4.5 GB |
| NLDAS-2 forcing (7 vars) | ~1–1.5 TB | 0.6–1 TB | 0.2–0.5 TB | 0.5–1.5 GB |
| NLDAS-2 LSMs (Noah+VIC+Mosaic, ~28 vars) | ~7.5 TB | 1–2 TB | 0.6–1.5 TB | 2–6 GB |
| NLDAS-3 beta forcing (8 vars, 2001–2023) | ~110 TB hourly + ~6 TB daily | same | 30–60 TB | 0.5–1.5 GB |
| GEOS-FP (19 vars, per 12 months) | ~20–30 TB/yr all DAS collections; slv+flx+rad+lnd ~2.3 TB/yr | 0.2–0.4 TB/yr | 0.07–0.15 TB/yr | 0.1–0.25 GB |
| HRRR (10 vars, hourly 2014-10–) | 2–5 PB full AWS archive (all forecasts); analysis files alone ~130 TB | 3–5 TB | 1–2 TB | 0.5–1.5 GB |
| PRISM 4 km (7 vars, daily 1981–) | ~160 GB (800 m: ~4 TB) | ~140 GB | 30–60 GB | 30–70 MB |
| GridMET (9 vars, daily 1979–) | ~150 GB | ~85 GB | 40–80 GB | 40–90 MB |
| Daymet V4R1 (6 vars, daily 1980–2025) | ~4 TB | ~3.3 TB | 1.5–3 TB | 30–70 MB |
| CHELSA-daily (9 vars, daily 1941–2025) | ~90–100 TB | 60–70 TB | 40–75 TB | 40–100 MB |
| CHIRPS v3 rnl daily (1981–) | ~0.5 TB (all variants/aggregations) | ~180 GB | 20–40 GB | ~3 MB |
| IMERG Final V07 (precip, HH + daily) | ~4.5 TB | 1–1.5 TB | 0.5–1 TB | 0.1–0.2 GB |
| IMERG Late (precip, HH) | ~4.5 TB | 1–1.5 TB | 0.5–1 TB | 0.1–0.2 GB |
| **Total, sites only** | | | | **~8–25 GB** (fits this container; obs add <2 GB) |

**Known dependencies (for interpreting results):**

| Product | Uses or assimilates |
|---|---|
| PRISM | USCRN, GHCN-D, SNOTEL/SCAN, RAWS, OK/NE/ND mesonets |
| Daymet | GHCN-D, which includes USCRN |
| HRRR | MADIS, which includes USCRN and most mesonets |
| GridMET | PRISM (T and P), NLDAS-2 (other variables) |
| NLDAS-2, MERRA-2 | CPC gauges (precipitation) |
| ERA5 | SYNOP/METAR, Stage IV precipitation |
| ERA5-Land | none directly |
| CHIRPS | blended at pentad scale |
| IMERG | GPCC monthly |

USCRN is therefore the best reference available, but not held-out truth for PRISM, Daymet, GridMET or HRRR.

## Comparison windows
- **W-full:** each product from 2008-01-01 (or the station's commissioning date) to the product's end.
- **W-common:** 2018-09-01 → 2025-08-31, roughly 7 years covered by every product except GEOS-FP, NLDAS-3 and IMERG Late. Rankings use this window.
- **W-recent:** 2025-11-01 → 2026-10-31. GEOS-FP against everything that covers it: ERA5-Land, HRRR, NLDAS-2, MERRA-2 (partial), GridMET, PRISM, CHIRPS (partial) and IMERG Late; ERA5 if its free copy extends that far.

## Stations and sites

**Tier 1: USCRN, all operational stations.** About 116 in CONUS, 40 in Alaska and 2 in Hawaii, from `products/stations.tsv`.
- Most variables come from `hourly02`. Wind comes from `subhourly01` (1.5 m), streamed and averaged to hourly.
- Keep only QC-good values (flag 0). Hourly values are stamped in UTC at the end of the hour. Station elevation is converted from feet.
- **Pilot:** 12 stations stratified by Köppen climate, including 1 in Alaska and 1 in Hawaii, run over the full period.

**Tier 2: independent and high-quality stations, about 60 sites.**

| Group | Sites | Why |
|---|---|---|
| **NEON** towers (~28), via `NEON_API_TOKEN` | HARV, BART, SCBI, SERC, OSBS, DSNY, JERC, TALL, ORNL, GRSM, UNDE, TREE, KONZ, UKFS, WOOD, NOGP, CPER, NIWO, YELL, ONAQ, MOAB, SRER, JORN, CLBJ, OAES, WREF, SJER, TEAK | Not in GHCN-D, MADIS or PRISM. Gives triple-aspirated T, RH, SW, soil T/moisture and precipitation (weighing gauges at core sites only; tipping-bucket sites flagged). |
| **AmeriFlux BASE** (~13 non-NEON, long records), via `AMERIFLUX_USER_ID`/`AMERIFLUX_EMAIL` | US-Ha1, US-MMS, US-NR1, US-Ne1, US-Var, US-Ton, US-Wkg, US-SRM, US-Seg, US-Mpj, US-UMB, US-Syv, US-ARM | Not in any product's inputs. **BASE**, not FLUXNET, because FLUXNET gap-fills with ERA5. |
| **SURFRAD** (7, open) | — | Research-grade radiation plus T, RH and wind. Not in any product's inputs. |
| **Open mesonets** (~10) | ISU Soil Moisture via IEM API (3), DEOS (2), FAWN (2), MAWN (2), plus 2 SCAN | Not GHCN-D. **In MADIS**, so they are partly dependent for HRRR and possibly PRISM; reported separately. SCAN adds soil moisture, which no product assimilates. |
| **Snow** (6 SNOTEL) | — | Only reliable SWE/snow-depth network. Flagged as a PRISM/Daymet T/P input; SWE itself is not assimilated by these products. |
| **Precipitation-only** (2 ARS Walnut Gulch gauges) | — | Dense, research-grade, not in product inputs. |

Not included: GHCN-D, COOP and RAWS, because nearly every station-based product ingests them, and RAWS hosts are unreachable from here. Oklahoma Mesonet, NDAWN and Nebraska are also out: they are confirmed PRISM inputs, and Oklahoma requires a data contract.

**Selection rules.**
- Check each candidate against the GHCN-D, USCRN and IEM/MADIS station lists by coordinates. Drop it if any of those has a station within 1 km, unless the overlap is useful (e.g. co-located NEON/USCRN pairs like CPER/Nunn and KONZ/Manhattan are kept as representativeness checks).
- Air temperature comes from the lowest tower level near 2 m, with the height recorded.
- **Credentials:** NEON and AmeriFlux fetchers read credentials from environment variables. If they are missing, they log a skip and the pipeline continues.

**Tier 3: 100 station-remote points**, products-only comparison.
- **Strata:** Köppen-Geiger (Beck et al. 2023, 1 km) × MODIS MCD12C1 IGBP land cover (0.05°), within CONUS. Allocation is proportional, with a minimum of 1 per non-trivial stratum.
- **Distance rule:** within each stratum, pick the cell that maximizes the distance to the nearest station. "Stations" is the union of GHCN-D (active since 2008), USCRN, NRCS AWDB, IEM network metadata and NEON/AmeriFlux. The minimum target is 25 km, relaxed where impossible (e.g. in the East); every point's distance is reported.
- The random seed is fixed, and the point list is committed.
- **Metrics:** inter-product spread, pairwise differences, and the ensemble median as a reference-free benchmark.

## Pipeline and code layout
`climate-product-compare/` (pinned with mise: Python 3.13, uv, Node 22; Python packages via uv: xarray, zarr 3, icechunk 2, numcodecs (pcodec), earthaccess, rioxarray/rasterio, h5netcdf, pyproj, pandas, pyarrow, scipy)
```
mise.toml, pyproject.toml, uv.lock, publish.toml, README.md, PROMPT.md, PLAN.md, TRANSCRIPT.md
certs/emsign-root-ca-g1.pem      # + fingerprint in README
src/cpc/
  sites.py                       # tier lists, remote-point sampler
  obs/{uscrn,neon,ameriflux,surfrad,iem,deos,fawn,mawn,nrcs,walnutgulch}.py
  products/<product>.py          # one module per product, common interface:
                                 #   locate(sites) -> pixel indices (3x3 or 2x2)
                                 #   extract(sites, t0, t1) -> Dataset(site, yi, xi, time)
                                 #   normalized names/units/time stamps (end-of-interval UTC)
  store.py                       # Icechunk writes, quantization, pcodec, resumable commits
  interp.py                      # nearest / bilinear / inverse-distance from stencils
  aggregate.py                   # hourly->daily for each product's day window; monthly
  metrics.py, export_site.py, figures.py
site/                            # static web app (Vite, package-lock.json)
results/                         # committed: site lists, metrics tables, pilot report, figures
data/                            # git-ignored: Icechunk store, caches
```
mise tasks: `sites`, `obs`, `extract -- <product> [--sites pilot|uscrn|tier2|remote]`, `update [-- --product X ...] [--dry-run]`, `store-copy`, `metrics`, `figures`, `sitedata`, `site`, `all`.

**Incremental update (`mise run update`).** Each product and observation module implements three things:
- `available_end()`: a cheap metadata probe that reads no data. Examples:

| Source | Probe |
|---|---|
| Icechunk/Zarr stores | last value of the time coordinate |
| NASA products | CMR latest granule |
| PRISM, CHIRPS, CHELSA | directory or bucket listing |
| GEOS-FP | GDS `.info` |
| USCRN | current-year file timestamp |

- `revision_window`: how far back provisional data can still change. Examples: PRISM 6 months, GridMET 60 days, CHIRPS preliminary→final, MERRA-2 (POWER) 1 month, HRRR 0. ERA5's free copy is final data, so 0.
- The `extract(sites, t0, t1)` it already has.

The store records `extracted_end` per product/group in Icechunk attributes. `update` then works as follows:
1. **Skip** products where `extracted_end >= available_end` and the revision window has expired.
2. Otherwise fetch only `[extracted_end − revision_window, available_end]` for all registered sites. Append along time (resize and write), overwrite the revised span, and record it as one Icechunk commit per product.
3. GEOS-FP keeps appending; metrics use a trailing 12-month window.

`--dry-run` prints what would be fetched (product, span, estimated bytes). After an update, `mise run all` recomputes metrics, site data and the site.

**Store backend (switchable).**
- Development uses a local, non-persisted repo. All code opens the store through `store.open_repo(url, mode)`. The URL comes from `--store`, else env `CPC_STORE`, else the default `file://data/extract.icechunk`.

| URL scheme | Backend | Access |
|---|---|---|
| `file://<path>` | `icechunk.local_filesystem_storage` | read/write |
| `s3://<bucket>/<prefix>` | `icechunk.s3_storage`, with region, endpoint and credentials from the standard AWS env or anonymous | read/write |
| `https://<host>/<prefix>` (e.g. CloudFront in front of S3) | Icechunk's HTTP storage | read-only; support is verified in the smoke test, with a fallback of reading the S3 bucket anonymously |

- A `mise run store-copy -- <src> <dst>` task copies a repo between backends, e.g. local → S3 later. Nothing else in the pipeline knows which backend is in use.

**Store layout.** One Icechunk repo (local by default: `data/extract.icechunk`).
- Groups `/<product>/<freq>/<var>(site, yi, xi, time)` and `/obs/<network>/<var>(site, time)`.
- Chunks are (1 site, full stencil, ~all time), so one chunk holds one site's series.
- Metadata includes pixel-centre coordinates, pixel elevation and distance to the site.
- Each product/site batch is written as an Icechunk commit, so reruns skip completed work.
- Requests run in parallel with bounded concurrency. Retries back off on 429/503.

**Compression study (on the pilot).**
- Compare zstd, lossless pcodec, and pcodec after rounding to a per-variable absolute precision: T/Td 0.01 °C, precip 0.01 mm, RH 0.1 %, SW 1 W m⁻², soil moisture 0.001 m³ m⁻³, pressure 1 Pa, wind 0.01 m s⁻¹, SWE 0.1 mm.
- Recompute every metric on both versions. Adopt quantization only if metric changes are negligible, i.e. far below inter-product differences.
- Report bytes per site-year per product.

**Time and units.**
- Every series is converted to UTC and stamped at the end of its interval: MERRA-2/GEOS-FP tavg values are shifted +30 min, IMERG start times become end times, and HRRR rates are converted to amounts.
- **Daily aggregation** follows each product's own day window:

| Product | Day window |
|---|---|
| PRISM | 12Z–12Z |
| GridMET | 07Z–07Z |
| CHIRPS, IMERG | UTC day |
| CHELSA | UTC day (Tmax/Tmin 06Z–06Z) |
| Daymet | local standard-time day |
| Hourly products | both UTC and LST days |

- Station data are aggregated to the same windows. Daily Tmax/Tmin come from the 5-minute extremes.
- **Completeness rules:** 22 of 24 hours for state variables; all 24 hours for precipitation.

**Metrics** (per site × product × variable × time scale × window × nearest-neighbour/bilinear):
- **Continuous variables:** n, bias, MAE, RMSE, unbiased RMSE, Pearson r, KGE components, and 5th/95th percentile errors.
- **Diurnal cycle:** amplitude and phase error at hourly scale.
- **Precipitation:** total bias, wet-day frequency, POD/FAR/CSI at 0.25, 1 and 10 mm d⁻¹, and 95th/99th percentile ratios.
- **Soil moisture:** anomaly correlation, because absolute values aren't comparable across depths and models. Layers are matched by depth overlap.
- **Wind:** raw 10 m vs 1.5 m, and log-law adjusted to 1.5 m (correlation is the primary score).
- **Secondary diagnostics:** lapse-rate-adjusted temperature (6.5 K km⁻¹ using pixel−station elevation), and the nearest-neighbour vs bilinear difference as a representativeness indicator.

## Website
Static Vite app built by `mise run site`. publish.toml builds it from committed `results/` plus one release asset, `site-data.tar`, which is extracted into `_site/data` at build time.
- **Libraries:** Leaflet map (sites coloured by tier or by a chosen metric), uPlot time series (fast with long series; product toggles; nearest vs bilinear toggle; daily/monthly view; brush-zoom), and hyparquet to read per-site Parquet in the browser.
- **Data:** each site has `daily.parquet` (all products and variables, full period) and `metrics.json`. Hourly files, `hourly/<site>/<year>.parquet` for hourly products, load only when you zoom below about 60 days.
- **Size:** about 800 MB in total. Hourly is trimmed (most recent years first) if needed.
- **Summary page:** heatmaps of product × variable skill, bias maps, and a per-window ranking table.

## Execution order and checkpoints
1. **Setup.** Scaffold the folder, mise/uv/npm lockfiles, PROMPT.md and PLAN.md (separate commits). Work on the designated branch `claude/climate-product-compare-75whba`, pushing regularly.
2. **Access smoke tests.** One point and one short period for each product; save a report in `results/access_check.md`. Also test `available_end()` for every product, and the S3/HTTPS store backends against a throwaway local MinIO or `file://` round-trip. Earthdata login currently fails with the email-style username: if the token or login doesn't work, I'll ask you to set the Earthdata username or `EARTHDATA_TOKEN`.
3. **USCRN ingest** for all stations. It's small: about 2 MB per station-year for hourly, plus streamed subhourly wind.
4. **Pilot:** 12 USCRN stations, all products, full period.
   - Measure bytes transferred and wall time per product, plus Icechunk size, and run the compression study.
   - Extrapolate the costs to all ~270 sites and write `results/pilot_report.md`.
   - **Checkpoint:** report to you. If extrapolated cost changes the plan (e.g. CHELSA/IMERG-HH limited to W-common), I'll say so before scaling.
5. Full USCRN extraction, then metrics.
6. Tier 2 site list (committed with a justification per site), obs ingest, extraction, metrics.
7. Tier 3 sampling (committed with a map), extraction, products-only metrics.
8. Figures, site data export, site build, local preview with `uv run _helpers/build_site.py --only climate-product-compare --skip-assets`.
9. **Releases.** Ask before creating the `climate-product-compare` release and uploading `site-data.tar` (and any figures), listing their sizes.
10. Finalize README (question, key results, `mise run all`, site link), root README line, TRANSCRIPT.md. Ask before fast-forwarding `main`, because the session branch rules conflict with CLAUDE.md's merge step.

## Verification
- **Unit checks:**
  - Nearest/bilinear indexing against known grid coordinates for each projection (LCC for HRRR/Daymet; 0–360 longitudes for ERA5).
  - Unit and time-shift sanity: lag-correlation of hourly product precipitation and SW against USCRN peaks at lag 0.
  - Daily-window aggregation tests on synthetic series.
- **Cross-checks:**
  - MERRA-2 from POWER vs the original M2T1NX file for one day.
  - ERA5-Land de-accumulation check.
  - Giovanni NLDAS vs one original granule.
  - Quantized vs lossless metrics.
- **Update:** `mise run update -- --dry-run` on a freshly extracted store reports everything as current. After truncating one product's last 30 days, it fetches only those 30 days plus the revision window, and the result is bit-identical to a full extraction.
- **End-to-end:** the pilot metrics are plausible (e.g. ERA5 T2m daily bias of order ±1–2 °C, r > 0.95). The site build passes locally, and in a headless Chromium (Playwright) you can click a site, load its series, and zoom into hourly data.

## Finalization (after the container restart, 2026-11-13)

**Context.** The container restarted while GEOS-FP was extracting. The local store survived (15 GB in
`data/store`), and so did the partial metrics (`data/results`) and the trial site export.
- Every product is complete except GEOS-FP, which reached 2026-10-27 of 2026-11-12.
- Station metrics exist for all products except GEOS-FP.
- Remote-point metrics must be recomputed: monthly precipitation was averaged instead of summed, now fixed in code.
- The AWS Emulator check is done (`results/emulator_check.md`).

Remaining steps, in order:

1. **Finish GEOS-FP.** Run `uv run cpc extract geosfp --sites all`. It resumes from `site_end`, about 16 days (~15 min).
   Then `uv run cpc compact` on all repos and `uv run cpc status` to confirm every product is current.
2. **Metrics.**
   - `cpc metrics geosfp --sites uscrn|tier2 --tag d`.
   - Re-run `cpc metrics --sites remote` (all products, fixed monthly sums).
   - `cpc merge-metrics`.
3. **Figures and report.**
   - `cpc figures`.
   - `cpc report` to regenerate `results/pilot/pilot_report.md` with final per-product store sizes.
   - Fill the README `<!-- STORAGE -->` section: measured MB/site and bytes/value per product vs the plan's estimates, plus the compression study.
   - Add the remote-point results to Key results (monthly, leave-one-out median).
   - Add a GEOS-FP line (recent window).
4. **Site.**
   - `cpc sitedata --sites all --metrics all --hourly-years 2` (~580 MB), then `mise run pack-site`, then `mise run site`.
   - Headless Chromium smoke test (map, site panel, hourly, summary, remote point; no console errors).
   - `uv run _helpers/build_site.py --only climate-product-compare --skip-assets` must pass.
5. **Docs and records.**
   - PROMPT.md: add Follow-up 4 (the aws-emulator request, verbatim).
   - PLAN.md: overwrite with this plan file, i.e. the original plan plus this section.
   - Root `README.md`: add the experiment line.
   - TRANSCRIPT.md: `uv run _helpers/transcript.py -o climate-product-compare/TRANSCRIPT.md`, skimmed for anything sensitive.
   - Commit (PROMPT/PLAN in their own commits) and push to `claude/climate-product-compare-75whba`.
6. **Ask before anything outward-facing.**
   - Creating the `climate-product-compare` release and uploading `site-data.tar`, with its size listed.
   - Fast-forwarding/pushing `main`, since the session's branch rules conflict with CLAUDE.md's merge step.

**Verification.**
- `uv run pytest -q` passes.
- `cpc status` shows every product at its available end.
- `metrics_all.parquet` covers all 17 products and 264 sites with observations or remote points.
- The site build passes and the smoke test shows no console errors.
- README numbers are re-checked against `metrics_all.parquet`.
