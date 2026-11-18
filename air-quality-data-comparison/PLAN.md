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

## Publishing (decided at the end: assets repo, then main)

Steps 1–6 and 8 are done and pushed to `ccr-10acad54-bjhr7u`. The final metrics have 267,652 rows; `site/public/data` holds 433 MB in 6,688 files (`site/site-data.tar` 439.5 MB). The site build and the headless check pass. This session cannot create releases, so you chose the **assets repo**, followed by **pushing main**.

1. **Attach and clone the assets repo.**
   - Attach `ashiklom/simon-code-research-assets` with push access (`add_repo`, access `push`).
   - Clone it with `--filter=blob:none --sparse` into `/home/user/simon-code-research-assets`, checking out only `air-quality-data-comparison/`, so the climate experiment's 576 MB is not downloaded.
2. **Add the files to the assets repo.**
   - `air-quality-data-comparison/README.md` says what the files are: the per-site Parquet/JSON for the air-quality site, read by `site/src/main.js` via `VITE_DATA_BASE`, produced by `mise run sitedata`.
   - `air-quality-data-comparison/data/` is a copy of `site/public/data`.
3. **Push in batches.**
   - Write `scripts/publish_site_data.sh` in the experiment, vendored from `climate-product-compare/scripts/publish_site_data.sh` with the folder name changed.
   - It commits the metadata JSON first, then site directories in batches of about 150 (~10 MB each), pushes after each batch, and finally pins the commit SHA.
   - This departs from CLAUDE.md's "one commit at the very end": one commit would be a single ~433 MB push through the proxy, which risks being cut off. The batches are all pushed in one go now, at the end, and nothing is stacked later. To update in future, rewrite and force-push this experiment's commits.
4. **Pin the site to that commit.**
   - New `site/.env.production`, with `VITE_DATA_BASE=https://raw.githubusercontent.com/ashiklom/simon-code-research-assets/<sha>/air-quality-data-comparison/data`.
   - `publish.toml`: drop the `[[assets]]` release entry and add a comment like climate's.
   - `mise.toml`: the `site` task stops unpacking the tar (keep `pack-site` as optional); the `all` task stays.
   - README "Publishing the site data": describe the assets repo, the pin and how to update, as in climate-product-compare. "Requirements" has no release step.
5. **Verify.**
   - `uv run _helpers/build_site.py --only air-quality-data-comparison --skip-assets` passes. The `_site` output should be small, with no `data/` copied, since `site/public/data` is moved aside for the build check.
   - Serve `_site` locally and run the Playwright check (pick Fresno, load the 2023 hourly data, switch to New Delhi monthly, open Summary). Data now loads from raw.githubusercontent at the pinned SHA, with no console errors.
   - Spot-check one URL with `curl -I` for 200 and CORS.
6. **Merge to main.**
   - Commit the experiment changes on the session branch and push.
   - `git fetch origin main`, rebase onto `origin/main`, fast-forward `main` and push `main`.
   - The session branch stays (the environment requires it), so it is not deleted.
   - Update TRANSCRIPT.md last, then push both branches.

Not done, and raised in the final message:
- **CAMS:** accept the ADS licences.
- **OpenAQ / AirGradient:** set `OPENAQ_API_KEY`.
- **AirQo:** provide a token.

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
