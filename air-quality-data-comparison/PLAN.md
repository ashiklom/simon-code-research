# Plan: `air-quality-data-comparison`

## Context
This is the air-quality analogue of `climate-product-compare`. The question is how well gridded near-surface air-quality products reproduce what monitors measure. The pollutants are PM2.5, PM10, PM2.5 components, O3 and NO2, compared at hourly, daily and monthly scales. Sites are US reference monitors, a global tier of embassy, OpenAQ and SPARTAN monitors, low-cost sensors, and about 100 station-remote points. The outputs are compact extracted time series and a static site where you click a site and compare products.

Decisions from the Q&A:
- **Scope:** a US core (Tier 1) plus a global tier (Tier 2). Rankings are reported separately for each.
- **Pollutants:** PM2.5, PM10, PM2.5 species, O3 and NO2.
- **Products:** the must-haves, plus CAMS, the US models, ACAG, GHAP and GEOS-FP (table below).
- **Stations:** AQS, AirNow, embassies, OpenAQ reference monitors, IMPROVE/CSN/SPARTAN filters, and free low-cost networks (AirQo, Sensor.Community, AirGradient). No PurpleAir.
- **Period:** extract from 2018-01 to each product's end. Rank on a common window, **2018-01..2023-12**. A recent window, **2025-08..2026-10**, covers GEOS-CF v2, GEOS-FP and the CAMS forecast.
- **Remote points:** about 100 global station-remote points, compared product-to-product.
- **Credentials:** read from environment variables. `EARTHDATA_LOGIN_*` and `CDSAPI_KEY` are already present; you'll add `OPENAQ_API_KEY`. A source whose credentials are missing or rejected is skipped cleanly and retried on the next run.
- **Publishing:** ask first, then try the GitHub release. If that's refused, push to the assets repo at the very end (one commit) and pin it.
- **Store:** local Icechunk, not persisted. As in the climate experiment, the backend can be switched by URL (`file://`, `s3://`, `https://`).

Research findings that shape the plan:
- The bias-corrected MERRA-2 product is **`MERRA2_CNN_HAQAST_PM25` V1** (DOI 10.5067/OCKK5HCFW5N3). It was trained on more than 5,000 OpenAQ reference monitors, so it is not independent of them.
- **GEOS-CF v1 ends 2026-01-02. v2 starts 2025-08-04**, plus a v2 hindcast for 2023–2025.
- GES DISC's on-premises OPeNDAP has been retired (HTTP 410).
- **WRI "CanAIRy Alert"** is a forecasting service built on GEOS-CF and local monitors, not a dataset. Its observations come from AirQo, AfriqAir and city networks, which this plan covers through AirQo and OpenAQ.
- **The State Department embassy monitors stopped reporting on 2025-03-04.** Their history is public on AirNow's S3.
- No product here has a time-series-chunked (ARCO) copy, so the extraction strategy below is the main cost risk. The pilot measures it.

## Products and access paths

All values are converted to UTC, stamped at the **end** of their averaging interval. Units: PM in µg m⁻³, gases in ppb.

Each product is sampled on the **2×2 pixel stencil** around each site, giving both nearest-pixel and bilinear values (code vendored from `climate-product-compare/src/cpc/grid.py`). Model PM components are stored separately, and total PM is computed at analysis time, so PM definitions can be compared after extraction.

| Product | Access (picked) | Res · period used | Variables | Surface obs used? |
|---|---|---|---|---|
| **GEOS-CF v1** (replay) | **Primary:** the public Zarr `s3://smce-geos-cf-public/geos-cf-rpl.zarr` (us-west-2, anonymous). Zarr v2, chunks 744 h × 50×50 pixels, so one chunk is about one site-month. **Species fallback:** v1 has no PM components in that Zarr. They come from NCCS OPeNDAP `geos-cf/assim/chm_tavg_1hr_g1440x721_v1`, at filter sites (IMPROVE, CSN, SPARTAN) only | 0.25°, 1 h, 2018-01-01 → 2026-01 (exact end read from data; the time axis is pre-allocated) | Zarr: pm25_rh35_gcc, o3, no2, co (+ t10m, rh, ps, zpbl). OPeNDAP: pm25 components | No (independent) |
| **GEOS-CF v2** (replay + ana-latest) | **Primary:** Zarr `s3://smce-geos-cf-public/geos-cf-v2-rpl.zarr` (chunks 663 h × 50×50) plus `geos-cf-v2-ana-latest.zarr` for the latest days. `geos-cf-v2-fcst-latest.zarr` is noted but not used, since forecast skill isn't the question. **Fallback:** `v2_hindcast` from portal HTTPS for 2023-01..2025-08, if the pilot shows it's worth the cost | 0.25°, 1 h, 2025-08-04 → now | pm25_rh35, **pm10_rh35**, pm25{bc,du,nh4,nit,oc,soa,ss,su}_rh35, o3, no2, so2, co | No (satellite O3 only) |
| **MERRA-2 aerosols** M2T1NXAER (+ M2T1NXSLV PS/T2M for ppb and RH) | Earthdata HTTPS (`data.gesdisc.earthdata.nasa.gov`) with h5py range reads of whole daily global fields; every site sampled from the same read. Cloud OPeNDAP is the fallback | 0.5°×0.625°, 1 h, 2018-01 → now (~3-week lag) | DUSMASS25, DUSMASS, SSSMASS25, SSSMASS, BCSMASS, OCSMASS, SO4SMASS | No (AOD only) |
| **MERRA-2 GMI** (O3, NO2) | NCCS portal `datashare/merra2_gmi/` | 0.5°×0.625°, 1 h, 2018 → 2025 | surface O3, NO2 | No |
| **MERRA2_CNN_HAQAST_PM25** V1 | Earthdata HTTPS `acdisc.gesdisc.eosdis.nasa.gov/data/HAQAST/MERRA2_CNN_HAQAST_PM25.1/` (daily files, about 10 MB each, read whole) | 0.5°×0.625°, 1 h, 2018-01 → latest | MERRA2_CNN_Surface_PM25, QFLAG | **Yes**, trained on OpenAQ reference monitors |
| **CAMS EAC4** | ADS API (`cams-global-reanalysis-eac4`), one global request per month and variable group | 0.75°, 3 h, 2018-01 → 2025-12 | pm2p5, pm10, aerosol species and O3/NO2 at the lowest model level | No (satellite only) |
| **CAMS global forecast** | ADS API (`cams-global-atmospheric-composition-forecasts`), 00 UTC run, leads 1–24 h, joined into a continuous series | 0.4°, 1 h, recent window only | pm2p5, pm10, O3, NO2 | No |
| **GEOS-FP aerosols** `tavg1_2d_aer_Nx` | NCCS OPeNDAP `GEOS-5/fp/0.25_deg/assim/` (reuse the climate experiment's GEOS-FP reader) | 0.3125°×0.25°, 1 h, recent window | Same species as MERRA-2 | No (MODIS AOD) |
| **HRRR-Smoke** | dynamical.org `noaa-hrrr-analysis-virtual` Icechunk `mass_density_8m`, read as whole GRIB-chunked fields once per hour. Fallback: `noaa-hrrr-bdp-pds` byte ranges from the `.idx` index | 3 km, 1 h, 2020-12 (HRRRv4) → now, CONUS | near-surface smoke PM2.5 (units change on 2021-12-21) | No (fire radiative power only) |
| **NOAA NAQFC / AQM** | `s3://noaa-nws-naqfc-pds/` GRIB2, 12 UTC cycle, leads 1–24 h joined. Raw and bias-corrected kept as two products | ~12 km, 1 h, from archive start (pilot checks) → now, CONUS | PM2.5, O3 | Raw: no. Bias-corrected: **yes** (AirNow) |
| **HAQES** (GMU/NASA ensemble) | GES DISC HTTPS `HAQES_NA_PM25_{TOT,OC,BC}` | 12 km, 3 h, archive span (pilot checks), North America | PM2.5 total, OC, BC | Partly (members include bias-corrected NAQFC) |
| **ACAG V6.GL.03** + **V6NA01 composition** | `s3://satpmdata` (anonymous). Windowed reads of the monthly NetCDF | 0.01°, monthly, 2018-01 → 2023-12 | PM2.5; in North America also BC, dust, NH4, NO3, OM | **Yes**, calibrated to ground monitors |
| **GHAP** (Wei et al. 2023) | Zenodo daily 1 km NetCDF, open years first. Restricted years are requested from you or skipped | 1 km, daily, 2018 → latest open year | PM2.5 | **Yes** (OpenAQ, EPA, EEA, CNEMC) |

**PM definitions.**
- GEOS-CF uses 35 % RH, which is closest to the FRM equilibration.
- MERRA-2 and GEOS-FP are dry mass with no nitrate. Total PM2.5 = DU25 + SS25 + BC + OC × f + SO4 × 132.14/96.06. Both f = 1 (GMAO FAQ) and f = 1.4 (Buchard et al. 2016) are reported, and f = 1.4 is the primary value. PM10 uses the full-size dust and sea salt.
- CAMS RH basis is checked in its documentation and noted.
- ML products inherit their training network's definition.

**Extraction strategy, chosen per product in the pilot by measured throughput:**
- **(a) Whole-field reads:** read the global or CONUS field for each time step, then sample every site. Cost does not depend on the number of sites.
- **(b) Tiled OPeNDAP hyperslabs:** group site stencils into about 4°×4° tiles and request tile × month. Cost scales with the number of tiles.

GEOS-CF needs neither (a) nor (b): it is read from the public SMCE Zarr stores.
- Sites are grouped by 50×50 chunk tile, and each chunk is read once for every site in that tile.
- v1 costs about 100 months × 4 variables × number of occupied tiles.
- v1 species are read by OPeNDAP at filter sites only.

## Stations and sites

| Tier | Source | Access | What and why |
|---|---|---|---|
| **1 US reference** | **EPA AQS** pre-generated files (`aqs.epa.gov/aqsweb/airdata`): hourly and daily 88101, 88502, 81102, 44201, 42602 for 2018–2025 | No key, about 0.2 GB/year zipped | Every monitor site meeting ≥ 75 % daily completeness for its parameter in the common window. Expected 1,500–2,500 sites. The AQS location setting (urban/suburban/rural) is kept for stratified scores. |
| 1 | **AirNow** hourly files (`files.airnowtech.org`, S3 listing), 2025-07 → now | No key | Preliminary data for the recent window, not yet in AQS. Joined to AQS sites by AQSID. |
| 1 | **IMPROVE + CSN** via FED (`views.cira.colostate.edu/fed`) | No key | 24 h filter PM2.5, PM10 and species (SO4, NO3, OC/OM, EC, soil, sea salt), every 3rd day. Research-grade, the closest analogue of USCRN. |
| **2 global reference** | **US embassy and consulate monitors**, AirNow `EmbassyHistorical/<City>/<YYYY>/` | No key | About 90 cities, hourly PM2.5, 2018 → 2025-03-04, when the network stopped. |
| 2 | **SPARTAN** (`s3://spartan-cloud`) | No key | About 25 global sites, filter mass and species plus nephelometer-based hourly PM2.5. Citation policy followed. |
| 2 | **OpenAQ reference monitors** (`isMonitor=true`) | Metadata from the API (`OPENAQ_API_KEY`); data from the anonymous S3 archive | Stratified sample of about 300 non-US locations: per region, the most complete PM2.5, PM10, O3 and NO2 monitors at least 25 km apart. Covers Europe (EEA), India (CPCB), China, LatAm, Africa and Oceania. |
| **3 low-cost** | **AirQo**, **AirGradient** (via OpenAQ), **Sensor.Community** (`archive.sensor.community`, ODbL) | No key except OpenAQ | About 100–150 sensors, preferring data-sparse regions plus some within 2 km of a reference monitor. QC: drop hours with RH > 75 % for SDS011, use PMS5003 dual-channel and range checks, and an RH-based correction from the literature. Scored as a separate tier. Pairs co-located with a reference monitor also get sensor-vs-reference scores. |
| **4 remote points** | About 100 land points | — | Stratified by region × pollution regime: ACAG 2018–2023 mean class × MERRA-2 dust fraction × fire (smoke) frequency. Each picks the cell farthest from any AQS, OpenAQ, embassy, SPARTAN or IMPROVE station, aiming for ≥ 100 km. Fixed seed; the point list is committed. Scored against the leave-one-out ensemble median at monthly scale. |

**Known dependencies, shown on the site and in the README:**
- MERRA2-CNN: OpenAQ reference, which includes AirNow/AQS and the embassies.
- GHAP: OpenAQ, EPA, EEA, CNEMC.
- ACAG: global monitors; the North America version also uses the speciation networks.
- NAQFC bias-corrected and HAQES: AirNow.
- CAMS Europe: EEA (not used here).

The station-independent products are GEOS-CF, MERRA-2 (+GMI), GEOS-FP, CAMS, HRRR-Smoke and raw NAQFC. The most independent references are IMPROVE, SPARTAN and the low-cost sensors.

## Comparison windows and time scales
- **Windows:**
  - W-full: 2018-01 to each product's end.
  - W-common: 2018-01..2023-12, every product except GEOS-CF v2, GEOS-FP and the CAMS forecast.
  - W-recent: 2025-08..2026-10, against AirNow and OpenAQ.
  - W-v1v2: GEOS-CF v1 vs v2 against the same stations, over 2025-08-04..2026-01, where both Zarr stores overlap. Extended back to 2023 if the v2 hindcast is extracted.
  - US-only and CONUS products are ranked within Tier 1 only.
- **Hourly:** products with an hourly or 3-hourly step.
- **Daily:** midnight-to-midnight local standard time, matching AQS daily summaries and the 24 h filters. Requires ≥ 18 h of data. O3 uses the daily maximum 8-hour average (MDA8).
- **Monthly:** ≥ 75 % of days present. ACAG is compared only at this scale.
- **Gas units:** station O3/NO2 reported in µg m⁻³ (EEA/OpenAQ) are converted to ppb at 25 °C, 1 atm, as the reporting standard implies.

## Metrics
Computed per site × product × variable × scale × window × nearest/bilinear (vendored and extended from `cpc/metrics.py`):
- **All variables:** n, bias, normalized mean bias (NMB), normalized mean error (NME), RMSE, unbiased RMSE, Pearson r, Spearman ρ, KGE.
- **PM2.5 exceedances:** POD, FAR and CSI for daily PM2.5 > 15 µg m⁻³ (WHO 24 h guideline) and > 35 (US NAAQS). Also 95th/99th-percentile ratios, US AQI category agreement, and a smoke-event subset (days where HRRR-Smoke > 20 µg m⁻³, or the station day is above its 98th percentile).
- **O3:** MDA8 bias and r, and exceedance skill at 70 ppb. Diurnal amplitude and phase error.
- **NO2:** daily mean, and the diurnal cycle at hourly scale.
- **Species** (IMPROVE, CSN, SPARTAN): bias and r for SO4, NO3, OM, BC/EC and dust per product, to show which component drives total-PM errors.
- **Summaries:** medians by tier, region, AQS location setting and season. The nearest-pixel vs bilinear difference is reported as a representativeness indicator.

## Code layout and storage
Pinned with mise (Python 3.13, uv, Node 22). uv packages: xarray, zarr 3, icechunk 2, numcodecs[pcodec], h5py/h5netcdf, earthaccess, cdsapi, cfgrib/eccodes, rasterio, pandas, pyarrow, scipy, s3fs.

```
air-quality-data-comparison/
  README.md PROMPT.md PLAN.md TRANSCRIPT.md publish.toml mise.toml pyproject.toml uv.lock
  src/aqc/
    grid.py store.py parallel.py http.py      # vendored from climate-product-compare/src/cpc (noted in headers)
    sites.py                                  # tier lists, OpenAQ stratified sample, remote-point sampler
    obs/{aqs,airnow,embassy,fed,spartan,openaq,sensorcommunity}.py
    products/{base,geoscf,merra2,merra2gmi,merra2cnn,cams,geosfp,hrrrsmoke,naqfc,haqes,acag,ghap}.py
    pm.py                                     # PM2.5/PM10 formulas from components, unit conversions (mol/mol, kg/kg → ppb, µg m⁻³)
    analysis.py metrics.py figures.py export_site.py cli.py
  site/      # Vite + Leaflet + uPlot + hyparquet, adapted from climate-product-compare/site
  results/   # committed: site lists, metrics tables, pilot report, figures
  data/      # git-ignored: Icechunk store, caches
```

- **Store:** one Icechunk repo per product and per observation network, with groups `/<freq>/<var>(site, stencil, time)`. Values are quantized (0.01 µg m⁻³, 0.01 ppb) and pcodec-encoded. Chunks hold one site's full series. Extraction is resumable: commits are per batch and `extracted_end` is recorded per product.
- **Updates:** `aqc update` re-uses that record to fetch only the missing tail, as in the climate experiment.
- **Credentials:** read from `EARTHDATA_LOGIN_USER`/`EARTHDATA_LOGIN_PASSWORD`, `CDSAPI_KEY` (ADS endpoint `https://ads.atmosphere.copernicus.eu/api`) and `OPENAQ_API_KEY`. A missing or rejected credential logs a skip; the pipeline continues.
- **mise tasks:** `sites`, `obs`, `extract -- <product...> --sites pilot|tier1|tier2|tier3|remote|all`, `update`, `lags`, `metrics`, `figures`, `sitedata`, `site`, `all`, `test`.

## Website
A static Vite app, adapted from the climate site:
- **Map:** sites coloured by tier, network or a chosen metric. Tier and pollutant filters.
- **Site panel:** product time series with toggles (hourly, daily, monthly), nearest vs bilinear, and species stacked bars at filter sites.
- **Summary page:**
  - product × pollutant skill heatmaps per tier;
  - an exceedance-skill table;
  - GEOS-CF v1 vs v2;
  - remote-point spread maps;
  - the dependency table.
- **Data:** per-site daily Parquet plus metrics JSON, with hourly per site-year loaded on demand. The target total is ≤ 800 MB; hourly years are trimmed if needed.

## Execution order and checkpoints
**Ordering rule (follow-up).** Work through everything that needs no action from you first, and don't stop for checkpoints or approvals along the way. Anything that needs you is queued and raised once, at the end.

| Group | Sources |
|---|---|
| **No intervention** | AQS, AirNow, embassies, FED (IMPROVE/CSN), SPARTAN, Sensor.Community, AirGradient public API, OpenAQ S3 archive, GEOS-CF v1/v2 (SMCE Zarr, plus NCCS OPeNDAP for v1 species), GEOS-FP (NCCS), HRRR-Smoke, NAQFC, ACAG (`satpmdata`), GHAP open Zenodo years |
| **Existing env credentials** (tried automatically; skipped if refused) | MERRA-2, MERRA-2 CNN and HAQES via Earthdata; CAMS via `CDSAPI_KEY` on ADS |
| **Needs you, deferred** | OpenAQ API key, AirQo token, ADS licence acceptance if refused, restricted GHAP years, the release or assets-repo push, and `main` |

- **OpenAQ without a key:** reference vs low-cost is classified from provider and instrument names in the S3 archive. It is re-classified with `isMonitor` once the key exists.
- **Pilot:** the pilot report is still written, but extraction scales up without waiting for your review.

1. **Setup.** Scaffold the folder and lockfiles. Write PROMPT.md (all prompts and Q&A verbatim) and PLAN.md, each in its own commit. Work on the session branch `ccr-10acad54-bjhr7u`, pushing regularly; the session requires it instead of `exp/<folder>`.
2. **Access smoke tests.** One point and one day per product and observation source, saved to `results/access_check.md`.
   - Checks ADS licence acceptance, the OpenAQ key, GHAP file availability and the NAQFC/HAQES archive spans.
   - If anything fails for credential or licence reasons, I'll tell you exactly what to accept or set.
3. **Station ingest:** AQS, AirNow, embassies, FED, SPARTAN, OpenAQ metadata and data, and low-cost sensors. Then build the site lists.
4. **Pilot:** about 20 sites, all products, the whole of 2023 (a smoke year).
   - Sites: 10 AQS spanning the Western smoke region, the East and rural settings, 5 embassies, 3 SPARTAN, 2 IMPROVE.
   - Measures bytes, wall time and store size per product, chooses strategy (a) or (b), and checks the lag of hourly O3/PM against AQS for each product.
   - Writes `results/pilot/pilot_report.md`, including extrapolated cost for the full run.
   - **Checkpoint:** I report to you before scaling up, especially if GEOS-CF, HRRR-Smoke or GHAP costs force cuts.
5. Full extraction: Tier 1, then Tiers 2–3, then remote-point sampling and extraction.
6. Metrics, figures, site data export, site build, and a local preview with `uv run _helpers/build_site.py --only air-quality-data-comparison --skip-assets`.
7. **Ask before publishing.** First the release `air-quality-data-comparison` with the files and sizes listed. If it's refused, the assets repo with one final commit, pinned.
8. Finalize: README (question, key results, `mise run all`, site link, requirements), the root README line, and TRANSCRIPT.md (skimmed for anything sensitive). **Ask before fast-forwarding and pushing `main`.**

## Verification
- **Unit tests** (pytest):
  - stencil and bilinear indexing on each grid, including NAQFC's Lambert conformal and HRRR's grid;
  - unit conversions (mol/mol → ppb; kg kg⁻¹ → µg m⁻³ using air density; µg m⁻³ → ppb);
  - MERRA-2 PM formula against a hand calculation;
  - LST daily and MDA8 aggregation on synthetic series.
- **Cross-checks:**
  - lag correlation of each hourly product's O3 and PM2.5 against AQS should peak at lag 0;
  - MERRA-2 PM2.5 from our extraction vs the CNN product's inputs at a few points;
  - GEOS-CF v1 vs v2 over the overlap;
  - AirNow vs AQS over 2025-01..06, where both exist, to quantify how much preliminary values differ from validated ones.
- **Plausibility:** pilot magnitudes should match the literature, e.g. GEOS-CF v1 PM2.5 biased high, about ×2, and the CNN product r ≈ 0.8 at OpenAQ sites.
- **End to end:**
  - `uv run pytest -q`;
  - `aqc status` shows every product at its available end;
  - the site build passes;
  - a headless Chromium (Playwright) check clicks a site, loads series, switches pollutant, opens hourly data, with no console errors;
  - README numbers are re-checked against the metrics table.
