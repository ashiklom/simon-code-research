# Transcript

Model(s): claude-opus-5-5
Tool output, thinking, and system context are omitted; tool calls are summarized.

<!-- session 4ee5e97b-d28f-575d-b1d9-fc903fcb4391 -->
*Session started 2026-11-17 02:57 UTC*

## User

Look at the existing climate data evaluation experiment for inspiration. Create an air-quality-data-comparison experiment that does a similar experiment for PM2.5, PM10, and similar near surface AQ data. Use web search to propose some gridded datasets and station data for comparison. For stations, consider EPA, State department AQ sensors at embassies, CanAiry data from WRI, city/state networks, citizen science, etc. For gridded products, definitely include GEOS-CF (NASA GMAO), MERRA-2, bias corrected MERRA-based PM2.5 (I don't remember the exact product). Ask clarifying questions as appropriate.

## Claude

- **Bash**: List repo contents and README: `ls && cat README.md && git log --oneline | head -20 && ls climate-product-compare 2>/dev/null`
- **Bash**: Read climate experiment README, plan, config: `cd /home/user/simon-code-research/climate-product-compare && cat README.md PLAN.md | head -400; cat publish.toml mise.toml; find . -type f -not -path './.venv/…`
- **Read**: `~/.claude/projects/-home-user-simon-code-research/4ee5e97b-d28f-575d-b1d9-fc903fcb4391/tool-results/bsy1m4d80.txt`
- **Bash**: Read prompt history and plan headings: `cat PROMPT.md; grep -n '^#' PLAN.md; wc -l PLAN.md`
- **Read**: `climate-product-compare/PLAN.md`

Reading the existing `climate-product-compare` experiment (done), now researching candidate AQ gridded products and station networks in parallel.

- **Agent**: Research gridded AQ products (Explore)
- **Agent**: Research AQ station networks (Explore)

Meanwhile, checking which parts of the climate experiment's code are worth vendoring.

- **Bash**: Inspect climate code structure for reuse: `wc -l src/cpc/*.py src/cpc/products/*.py src/cpc/obs/*.py site/src/main.js && sed -n 1,80p src/cpc/products/base.py && grep -n '^def \|^class ' src/cpc/store.p…`
- **Bash**: Check credential env var names and resources: `env | cut -d= -f1 | grep -iE 'earthdata|cds|ads|aws|openaq|purpleair|airnow|aqs|key|token|neon|ameri' ; df -h /home/user | tail -1; nproc; free -g | head -2`

Credentials available here: Earthdata and a CDS key (likely also valid for the Atmosphere Data Store). Waiting for the two research agents.

- **Write**: `~/.claude/plans/look-at-the-existing-resilient-crown.md`

Draft plan file started; I'll fill it in once both research agents report back.

## User

<task-notification>
<task-id>a29cc18cf6f6712a0</task-id>
<tool-use-id>toolu_01QKiUSpvCk34bZ3NeCQdtn6</tool-use-id>
<output-file>/tmp/claude-0/-home-user-simon-code-research/4ee5e97b-d28f-575d-b1d9-fc903fcb4391/tasks/a29cc18cf6f6712a0.output</output-file>
<status>completed</status>
<summary>Agent "Research AQ station networks" finished</summary>
<note>A task-notification fires each time this agent stops with no live background children of its own. The user can send it another message and resume it, so the same task-id may notify more than once.</note>
<result>I checked every source live from this container except CNEMC, AirGradient, AirQo, Clarity and the API-only services, which I only probed for reachability. Item 3 turned out not to be a sensor dataset. Item 2 has a major gap you need to plan around: the embassy monitors stopped reporting in March 2025.

#### Headlines
- **"CanAiry" is WRI's CanAIRy Alert, a forecasting programme, not a sensor network.** It turns NASA's GEOS-CF forecast plus local reference and calibrated low-cost monitors into station-level forecasts of PM2.5, NO2 and O3. It started as the 2020–21 CityAQ pilot. Funding is from the Clean Air Fund; partners include NASA, UNEP, AirQo and AfriqAir.
  - Cities: Accra, Kampala, Kigali and Nairobi first, then Latin American and other cities including Guadalajara, León, Monterrey, Bogotá, Quito, São Paulo, Addis Ababa and Jakarta.
  - Its observations come from AirQo, AfriqAir and city networks, so for raw data go to AirQo or OpenAQ. Forecasts are at canairyalert.org (301 redirect to www) and on Resource Watch. I found no documented bulk download.
- **The embassy network stopped sending data on 2025-03-04** because State Department funding was cut. About 70 monitors in 50 countries were active in January 2025. In a statement to NPR, apparently around September 2026, State said it is "in the process of restoring" public reporting, with no date. I found nothing showing it has resumed.
  - The historical files are still public and need no login: `s3://files.airnowtech.org/airnow/EmbassyHistorical/&lt;City&gt;/&lt;YYYY&gt;/&lt;City&gt;_PM2.5_&lt;YYYY&gt;_&lt;MM&gt;_MTD.csv` plus `_YTD.csv`. I counted 90 city folders.
- **Easiest to pull with no credentials:** AQS bulk files, AirNow's hourly files, the OpenAQ S3 archive, Sensor.Community, SPARTAN, IMPROVE/CSN, EEA, Canada NAPS, UK AURN and the China mirror. A key is needed for the AirNow API, OpenAQ API, AQS API, PurpleAir and WAQI.

#### 1–2. US EPA AQS and AirNow

| | AQS bulk files | AQS API | AirNow files | AirNow API |
|---|---|---|---|---|
| URL | aqs.epa.gov/aqsweb/airdata/download_files.html | aqs.epa.gov/data/api | files.airnowtech.org → `s3-us-west-1.amazonaws.com/files.airnowtech.org/airnow/YYYY/YYYYMMDD/` | airnowapi.org |
| Status here | 200; zip 200 | 400 without login | 200, anonymous S3 listing works | 401 without key |
| Data | Validated regulatory data, hourly/daily/annual | Same, more flexible queries | Preliminary, real-time | Preliminary |
| Credentials | None | Email + key | None | Free key |
| Latency / period | Updated twice a year (June: full prior year; December: ozone season). Current files "As of 2026-06-25" | Weeks to months | About 1 h. Folders exist from 2012 to 2026 | Real time |

- **AQS pollutant codes:**
  - 88101: PM2.5 from FRM/FEM monitors (regulatory). Comes with an EPA data advisory for the 88101 files.
  - 88502: "acceptable" PM2.5 that is not FRM/FEM (AQI-only continuous monitors).
  - 81102: PM10.
  - 44201: O3. 42602: NO2. 42101: CO.
  - Hourly files mostly come from continuous FEM monitors (BAM, TEOM-FDMS, T640). The 24-h filter FRM samples (every 1, 3 or 6 days) appear only in the daily files.
- **AQS zipped sizes for 2025:**

| File | Rows | Size |
|---|---|---|
| hourly_88101 | 8.37 M | 67 MB |
| hourly_88502 | 1.60 M | 12.5 MB |
| hourly_81102 | 3.95 M | 32 MB |
| hourly_44201 | 8.87 M | 66 MB |
| hourly_42602 | 3.49 M | 28 MB |
| daily_88101 | 759 k | 8.4 MB |

- **AirNow hourly files:**
  - `HourlyData_YYYYMMDDHH.dat`, about 0.7 MB each. Pipe-delimited: `date|time|AQSID|site|UTCoffset|param|unit|value|agency`.
  - `HourlyAQObs_*.dat`, about 1 MB, which includes coordinates.
  - The sample file also has Canadian stations; the US-plus-Canada network is roughly 2,500+ sites.
  - AirNow data are unvalidated, so use AQS for final statistics. AirNow is mainly useful for 2026 data that AQS hasn't released yet.
- **Embassy data in OpenAQ:** OpenAQ ingested AirNow, which carried the "US Diplomatic Post" sites. I believe the embassy history is in OpenAQ but did not confirm it; check `/v3/providers` and search location names for "US Diplomatic Post".

#### 4. OpenAQ
- **API v3:** keyless calls returned 401 from here, so a free key is required (`X-API-Key` header, register at explore.openaq.org). A secondary source gives limits of about 60 requests/min and 2,000/hour; I didn't confirm that on OpenAQ's own pages.
- **S3 archive:** `s3://openaq-data-archive/records/csv.gz/locationid=N/year=YYYY/month=MM/location-N-YYYYMMDD.csv.gz`. Anonymous listing works (200, `--no-sign-request`). Files are about 1 KB per location-day. You can also query it with Athena.
- **Sources:** government networks (AirNow, EEA, CPCB, CNEMC-type feeds, Latin American agencies) plus low-cost sensors (Clarity, AirGradient, AirQo, Sensor.Community feeds and others).
- **Reference vs low-cost:** use the `isMonitor` field (true = reference "Government Monitor"), plus `provider` and `instrument`. About 75% of locations were reference-grade at the end of 2025, but 80% of new locations were sensors.
- **Licence:** varies by provider.
- **Product use:** used to bias-correct GEOS-CF (Keller et al. 2021) and as a ground source in global PM2.5 products.

#### 5. Low-cost / citizen science

| Source | Measures | Access | Notes |
|---|---|---|---|
| PurpleAir | PM1/2.5/10 (Plantower PMS5003 ×2), T, RH | api.purpleair.com (403 without key). Billed in points, about $10 per 1 M points in an undated post. Use the sensor-history endpoint; email [email] for bulk | Raw values read about 40% high. Apply Barkjohn et al. 2021 (AMT 14:4617), which includes RH, or the 2022 smoke-extended equation used on the Fire &amp; Smoke Map. QC: drop records where the A and B channels disagree |
| Sensor.Community | PM (SDS011 about 9,000 files per day, SPS30, PMS), BME280/DHT22 | archive.sensor.community/YYYY-MM-DD/ for recent days; yearly folders for 2015 onward; `csv_per_month/` (200). Live JSON at data.sensor.community (200). No key; ODbL licence | No RH correction applied. SDS011 overreads badly when RH is above ~75%; you must filter and correct yourself |
| AirGradient | PM2.5, CO2, T/RH (PMS5003T) | api.airgradient.com public "world" endpoint (200); also in OpenAQ | Applies its own correction |
| Clarity | PM2.5, NO2 | Mostly via OpenAQ | Calibrated with Clarity's own models |
| AirQo (Uganda/East Africa) | PM2.5/10 | Token-based API (airqo.mak.ac.ug/products/api); also in OpenAQ | Raw and calibrated values. Data source behind CanAIRy |

#### 6. Research-grade networks (the USCRN analogue)

| Network | Measures | Cadence | Coverage | Access |
|---|---|---|---|---|
| IMPROVE | 24-h filter PM2.5 mass + species, PM10 | Every 3rd day, 1988 onward | About 160–236 mostly rural sites in the US | FED: views.cira.colostate.edu/fed/DataFiles (200), no key |
| CSN | Speciated PM2.5 | Every 3rd or 6th day | About 130–157 urban sites | FED or AQS |
| EPA NCore | Multi-pollutant, PM2.5/10/coarse | Hourly + filter | About 80 sites | In AQS |
| SPARTAN | Filter PM2.5/PM10 mass + composition; nephelometer → hourly/daily PM2.5 | Filters about 9-day integrated; nephelometer continuous | About 20–30 sites worldwide, many in data-poor countries | `s3://spartan-cloud` (anonymous, 200, `GroupByProduct/`, `GroupBySite/`). Citation policy |
| AERONET | AOD only (context) | Sub-hourly | Hundreds of sites | aeronet.gsfc.nasa.gov (200) |

#### 7. National, regional and city networks

| Network | Access | Status here | Credentials |
|---|---|---|---|
| EEA e-reporting (E1a verified 2013+, reported by 30 Sept for the prior year; E2a unverified near-real-time; Airbase 2002–12) | Parquet download API (swagger at eeadmz1-downloads-api-appservice...). Python `airbase`, R `euroaq` | API 200; web app 403 | None |
| UK AURN (about 170 sites) | uk-air.defra.gov.uk data selector; R `openair` | 200 | None, Open Government Licence |
| Canada NAPS | data-donnees.az.ec.gc.ca/.../national-air-pollution-surveillance-naps-program (hourly continuous + integrated) | 200 | None, Open Government Licence |
| India CPCB CAAQMS (about 500+ stations) | airquality.cpcb.gov.in | 000 (unreachable) | Use OpenAQ instead |
| China CNEMC (about 1,600+ stations) | No official bulk download. Mirror at quotsoft.net/air (200); Zenodo dumps for 2014–2022 | 200 | None |
| South Africa SAAQIS | saaqis.environment.gov.za | 200 | Request-based |
| Mexico City SIMAT | aire.cdmx.gob.mx | 200 | None |
| Santiago SINCA | sinca.mma.gob.cl | 403 | Use OpenAQ |
| Bogotá RMCAB | rmcab.ambientebogota.gov.co | 302 | Web form |
| Australian state networks (NSW, VIC, QLD) | State open-data portals / OpenAQ | Not probed | Mostly open |

#### 8. Global aggregators
- **WAQI/aqicn:** token API (200), historical "data platform" back to about 2014. The terms forbid redistributing the data as cached or archived copies, forbid "official comparison, ranking, report or data analysis", and require notification for non-profit public use. That is a poor fit for a published benchmark.
- **Berkeley Earth:** real-time PM2.5 maps and a China/global station compilation (berkeleyearth.org/data, 200). No maintained bulk station feed I could find.
- **WHO Ambient Air Quality Database:** city-level annual means of PM2.5, PM10 and NO2, Excel download. V6.1 (January 2024) covers 7,182 settlements; a June 2026 update exists. Too coarse for hourly or daily evaluation, but it is a ground source used to calibrate van Donkelaar/ACAG.

#### Which products use which data (for an independence check)
Treat these as overlapping, not independent, test sets. Several of these attributions are from memory and need checking in each product's paper.
- **EPA FAQSD:** fuses CMAQ with AQS (88101 and O3).
- **ACAG/van Donkelaar V6.GL.02:** CNN-calibrated against "global ground observations". My understanding is these are the WHO database, AQS/NAPS, EEA, CNEMC and OpenAQ; the ACAG pages don't list the networks.
- **GHAP (Wei et al.):** trained on 5,000+ ground stations from these kinds of sources, mostly government networks.
- **GEOS-CF bias correction:** OpenAQ (stated above).
- **MERRA-2 CNN HAQAST (2000–2024):** the training stations aren't named in the catalogue; the README on the GES DISC page should say.

Truly independent checks are the low-cost networks (after correction), SPARTAN, AirNow for 2026 (not yet in AQS), and possibly IMPROVE/CSN filter mass (some products use AQS 88101, which includes some of these sites).

#### Main sources
- [AQS files](https://aqs.epa.gov/aqsweb/airdata/download_files.html)
- [CREA on the embassy halt](https://energyandcleanair.org/us-embassy-aq-data-halt/), [NPR/KJZZ 2026](https://www.kjzz.org/npr-top-stories/2026-09-15/air-pollution-spiked-after-the-trump-administration-stopped-embassy-monitoring)
- [WRI CanAIRy Alert](https://www.wri.org/initiatives/canairy-alert), [CanAIRy about](https://canairy.squarespace.com/about)
- [OpenAQ archive docs](https://docs.openaq.org/aws/about), [OpenAQ API key](https://docs.openaq.org/using-the-api/api-key)
- [PurpleAir API pricing](https://community.purpleair.com/t/api-pricing/4523), [Barkjohn 2021](https://amt.copernicus.org/articles/14/4617/2021/)
- [SPARTAN data](https://www.spartan-network.org/data), [FED](https://views.cira.colostate.edu/fed/DataFiles)
- [EEA download](https://aqportal.discomap.eea.europa.eu/download-data)
- [WAQI terms](https://aqicn.org/data-platform/tos), [WHO database](https://www.who.int/data/gho/data/themes/air-pollution/who-air-quality-database)
- [ACAG](https://sites.wustl.edu/acag/datasets/surface-pm2-5), [MERRA-2 CNN HAQAST](https://www.earthdata.nasa.gov/data/catalog/ges-disc-merra2-cnn-haqast-pm25-1)
- [CNEMC ESSD paper](https://essd.copernicus.org/articles/12/3067/2020/essd-12-3067-2020.pdf), [AirQo API](https://airqo.mak.ac.ug/products/api)</result>
<usage><subagent_tokens>89018</subagent_tokens><tool_uses>29</tool_uses><duration_ms>261728</duration_ms></usage>
</task-notification>

## Claude

Station research is back; still waiting on the gridded-product research before writing the plan.

## User

<task-notification>
<task-id>a7149065d60cb3c78</task-id>
<tool-use-id>toolu_01HwGbN9kzjnvDNB8AJYyohZ</tool-use-id>
<output-file>/tmp/claude-0/-home-user-simon-code-research/4ee5e97b-d28f-575d-b1d9-fc903fcb4391/tasks/a7149065d60cb3c78.output</output-file>
<status>completed</status>
<summary>Agent "Research gridded AQ products" finished</summary>
<note>A task-notification fires each time this agent stops with no live background children of its own. The user can send it another message and resume it, so the same task-id may notify more than once.</note>
<result>I found and probed records for all 7 product groups. Three findings matter most for your plan:

- **Your guess on the bias-corrected product is right.** It is `MERRA2_CNN_HAQAST_PM25` V1. Its README says it was trained on OpenAQ reference-grade monitors (over 5,000). Because US AQS/AirNow data flow into OpenAQ, it is not independent of US or global station data.
- **GEOS-CF v1 has ended.** Its OPeNDAP time axis stops at 2026-01-02. v2 data run from 2025-08-04 and v2 is now the main product.
- **GES DISC's on-premises OPeNDAP (`goldsmr4…/opendap`) returns HTTP 410 "Service Retired".** MERRA-2 access is now Earthdata Cloud only.

Probe results below are HTTP codes from this container. "000" means the request timed out; NASA hosts timed out intermittently.

#### 1. GEOS-CF (NASA GMAO Composition Forecast)

| Item | Detail |
|---|---|
| Versions | v1: 2018-01-01 to 2026-01-02. OPeNDAP `assim` collections confirmed; met replayed to GEOS-FP. v2: 2025-08-04 onward, implemented Oct 2025, announced Jan 2026. v2 adds satellite O3 assimilation and new chemistry and emissions. v1 overestimated PM2.5 by about a factor of 2; v2 is less biased. A v2 hindcast exists in `v2_hindcast/ana/` (Y2023–Y2025). Earth Engine advises not mixing v1 and v2. |
| Grid / time | 0.25° (1440×721), hourly average. 15-minute "htf" collection. Analysis daily at 09Z, then 5-day forecast, ready ~17Z. |
| Air-quality collection (aqc) | v1 `aqc_tavg_1hr_g1440x721_v1`: o3, no2, co, so2, pm25_rh35_gcc. v2 `aqc_tavg_1hr_glo_L1440x721_slv`: o3, no2, co, so2, **pm25_rh35, pm10_rh35** (mol/mol and µg/m³). |
| PM components | v1 `chm_tavg_1hr_g1440x721_v1`: pm25{bc,du,ni,oc,soa,ss,su}_rh35_gcc and pm25_rh35_gocar. v2 `chm_tavg_1hr_glo_L1440x721_slv` (52 variables): pm25{bc,du,nh4,nit,oc,soa,ss,su}_rh35. |
| Access | OPeNDAP `https://opendap.nccs.nasa.gov/dods/gmao/geos-cf/{assim,fcast}` (v1) and `.../geos-cf/v2/{ana,fcst}`: 200, except v2/fcst returned 502 at probe time. HTTPS `https://portal.nccs.nasa.gov/datashare/gmao/geos-cf/{v1,v2,v2_hindcast}/`: 200 (v2 file spec PDF is in `v2/`). Earth Engine `NASA/GEOS-CF/v2/fcst/htf` (has `PM25_RH35`). CFAPI point API needs a request to GMAO. No credentials needed for NCCS. |
| ARCO copy | No public copy. NASA VEDA has early-development Icechunk stores of v2 aqc (ana and fcst) in `s3://veda-data-store`, "for testing". Not on the AWS Open Data registry. |
| Ground obs used | None assimilated for surface PM, NO2 or O3. Independent of stations. |
| Bias-corrected station product | Keller et al. 2021 describe ML (XGBoost) bias correction at OpenAQ sites. It is station-only, not gridded, and reachable via CFAPI or on request. It is trained on OpenAQ, so not independent. |

#### 2. MERRA-2 aerosols (M2T1NXAER, `tavg1_2d_aer_Nx`)

- **Grid / time:** 0.5°×0.625°, hourly, 1980 to present (lag of about 2–3 weeks).
- **PM2.5 formula (GMAO FAQ):** `PM2.5 = DUSMASS25 + SSSMASS25 + BCSMASS + OCSMASS + SO4SMASS×(132.14/96.06)`, multiplied by 1e9 to get µg/m³. The GMAO FAQ applies no OC multiplier. The ×1.4 or ×1.6 OC factor comes from the literature, and using it may double-count if OC is already carried as organic matter; check before choosing. No nitrate. Dry mass.
- **PM10:** `DUSMASS + SSSMASS + BCSMASS + OCSMASS + SO4SMASS×1.375`.
- **Assimilation:** AOD from AVHRR, MODIS, MISR and AERONET. AERONET is ground-based but measures the column, not surface PM. No surface PM assimilated.
- **Access (Earthdata login required):**
  - S3: `s3://gesdisc-cumulus-prod-protected/MERRA2/M2T1NXAER.5.12.4/` (us-west-2; credentials from `https://data.gesdisc.earthdata.nasa.gov/s3credentials`).
  - Cloud OPeNDAP: `https://opendap.earthdata.nasa.gov/collections/C1276812830-GES_DISC/granules/...` returns 302 to the login page.
  - The old `goldsmr4…/opendap/` returns 410. `goldsmr4…/data/` timed out.
- **Giovanni time-series API:** returns 403 with body `401 "Bad or missing token"`, so it needs an Earthdata bearer token. I could not confirm whether the `M2T1NXAER_5_12_4_DUSMASS25` IDs are served. The service is single-point only.
- **Value-added product:** `M2_TMAX_PM25`, monthly PM2.5 by country.
- **ARCO copy:** None public. GES DISC is building Kerchunk/Parquet manifests and has benchmarked them on M2T1NXAER. MERRA-2 aerosols are also in Earth Engine as `NASA/GSFC/MERRA/aer/2`. I found no sign NASA POWER serves surface PM; I did not check its parameter list.
- **MERRA-2 GMI (O3 and other gases):** `https://portal.nccs.nasa.gov/datashare/merra2_gmi/` returned 200, with years Y1980–Y2025.

#### 3. Bias-corrected MERRA-2 PM2.5 (confirmed)

| Item | Detail |
|---|---|
| Name | *MERRA2_CNN_HAQAST bias corrected global hourly surface total PM2.5 mass concentration, V1*. Short name `MERRA2_CNN_HAQAST_PM25`, version 1. |
| IDs | DOI 10.5067/OCKK5HCFW5N3. CMR collection C3094710982-GES_DISC. Released 2024-07-15. |
| Authors | Pawan Gupta and Alqamah Sayeed (NASA MSFC/GSFC, HAQAST). Code: github.com/Alqamah-Sayeed/MERRA2-ML-PM2.5 |
| Variables | `MERRA2_CNN_Surface_PM25` (µg/m³) and `QFLAG` (1–4). Catalog recommends QFLAG 3–4; README recommends 2 and up. |
| Grid / time | 0.5°×0.625°, hourly (00:30–23:30 UTC). Daily files `MERRA2_HAQAST_CNN_L4_V1.YYYYMMDD.nc4`. |
| Period | Starts 2000-01-01; CMR marks it as ongoing ("ends at present"). Files in the 2026 directory run to at least 20260701. |
| Method | Ensemble of 5 CNNs. Inputs: MERRA-2 met (PS, Q500, T850, T500, T10m, QV10m, U/V10M), DUSMASS25, OCSMASS, SO2SMASS, SO4SMASS, BCSMASS, SSSMASS25, TOTEXTTAU, solar zenith angle, Sun–Earth distance. |
| Training stations | **OpenAQ reference-grade monitors, more than 5,000 (US, Europe, China, India, Australia, Chile and others).** About 19.6M samples; r 0.40 → 0.85. Not independent of OpenAQ or AirNow stations. |
| Access | HTTPS `https://acdisc.gesdisc.eosdis.nasa.gov/data/HAQAST/MERRA2_CNN_HAQAST_PM25.1/` (listing 200; downloads need Earthdata login). S3 `s3://gesdisc-cumulus-prod-protected/HAQAST/MERRA2_CNN_HAQAST_PM25.1/`. OPeNDAP via `cmr.earthdata.nasa.gov/virtual-directory/collections/C3094710982-GES_DISC`. Giovanni. |
| README | `https://docserver.gesdisc.eosdis.nasa.gov/public/project/HAQAST/Pawan_Gupta/README_MERRA2_CNN_HAQAST_PM25_V1.pdf` |

Related products:
- Sayeed et al. 2022 (*Earth and Space Science*) is an earlier US version trained on EPA AQS.
- The same group runs TCN forecasts on GEOS-FP inputs for 270 US embassies and 5,000+ OpenAQ stations. That is forecasting, not gridded.

#### 4. CAMS (ECMWF)

| Dataset (ADS ID) | Grid / time | Period | Variables | Obs assimilated |
|---|---|---|---|---|
| EAC4 `cams-global-reanalysis-eac4` | 0.75°, 3-hourly | 2003-01-01 to 2025-12-31 (ADS extent); released in yearly batches | PM1, PM2.5, PM10, aerosol species, O3, NO2, CO, SO2 | Satellite AOD, O3, CO, NO2, SO2. **No surface in situ.** |
| Global forecasts `cams-global-atmospheric-composition-forecasts` | 0.4°, hourly surface fields | 2015 to present, 5-day forecasts | Same as EAC4 | Satellite only |
| Europe forecasts / `cams-europe-air-quality-reanalyses` | 0.1°, hourly; ensemble of 11 models | Reanalyses 2013 onward: interim for year Y ready May Y+1, validated Nov Y+2 | PM2.5, PM10, components, gases | **EEA in situ stations** (not independent in Europe) |
| `cams-europe-air-quality-forecasts-optimised-at-observation-sites` | Station-level, statistically corrected | — | — | Uses station obs |

- **Access:** ADS API (`cdsapi`, ADS key plus licence acceptance). Catalogue API returned 200.
- **ARCO copy:** CAMS describes an ARCO data lake (Zarr or GeoTIFF). I found no public EAC4 Zarr URL or ADS time-series ID; `...-eac4-timeseries` returned 404. Not on dynamical.org. I could not determine the RH basis of CAMS PM; check the IFS-COMPO documentation.

#### 5. WashU ACAG (van Donkelaar / Martin)

- **Versions on the site:** V6.GL.02.04 (residual CNN) and V5.GL.05.02 (GWR), both 0.01° and 0.1°, monthly and annual, 1998–2023. V5.NA.05.02 covers North America at 0.01°, monthly, annual and biweekly, 2000–2023. **No daily product.**
- **Public AWS bucket `s3://satpmdata` (us-east-1, no credentials, listing 200):**
  - `V6GL03/` (CNNPM25, CNNPM25c0p10, region summaries), newer than the site's V6.GL.02.04.
  - `V6NA01/`: PM2.5 plus composition (BC, dust, NH4, NO3, OM) with uncertainties.
  - `V5GL06/`, `CONUSPM1V01/`, `SATNO2V4GL01/`.
  - Files are NetCDF per region and month or year.
- **Inputs:** Multi-satellite AOD and GEOS-Chem, weighted using AERONET, then **calibrated to global ground PM2.5 monitors**. The NA version also uses speciation networks. Not independent at annual or monthly scale.
- **PM basis:** I recall ACAG reports PM2.5 at 35% RH, but the ACAG page I fetched does not state it; verify.

#### 6. Daily high-resolution and US products

| Product | Grid / time / period | Access | Ground obs used |
|---|---|---|---|
| **GHAP / GlobalHighPM2.5** (Wei et al. 2023, *Nature Communications*) | 1 km daily, monthly, yearly over land, 2017 to present | Zenodo per-year records (10800980 returned 200, but its files are login-restricted; open records exist for 2021 and 2022). Earth Engine community catalog copy. | About 9,470 monitors: North America 2,729, Europe 2,064, Asia 3,613, Africa 469, South America 276, Oceania 323. Sources: OpenAQ, CNEMC, EPA, NAPS, EEA. Predictors: MAIAC AOD, GEOS-FP/GEOS-CF AOD, ERA5. |
| **CHAP** (China) | 1 km daily, 2000 to present | Zenodo | About 1,500+ CNEMC stations (from memory; not checked) |
| **Di et al. 2019** (SEDAC v1.10) | 1 km daily, CONUS, 2000–2016 | SEDAC timed out from here (SEDAC is migrating to Earthdata) | EPA AQS (search results did not name the network; my recollection, verify) |
| **EPA FAQSD** | Daily at 2010 census-tract centroids; CMAQ 12 km fused with monitors | `https://www.epa.gov/hesc/rsig-related-downloadable-data-files` (200) | AQS (NAMS/SLAMS) 24-hour data. Not independent. |
| **HRRR-Smoke** (`MASSDEN` 8 m; units changed from µg/m³ to kg/m³ on 2021-12-21) | 3 km, hourly, CONUS, near real time | `noaa-hrrr-bdp-pds` (200). dynamical.org `noaa-hrrr-analysis-virtual` Icechunk (`mass_density_8m`, 2014-10-01 onward; GRIB-chunked, not time-series-chunked). dynamical's non-virtual `latest.zarr` has no smoke variable. | Fire radiative power only. Independent. |
| **NAQFC / AQM** | About 12–13 km, hourly, CONUS, AK, HI | `s3://noaa-nws-naqfc-pds/` (200): AQMv5/6/7, AQMv7_suppl, HYSPLIT_Dust/Smoke, RAP_Smoke; latest AQMv7/CS folder 20261116 | Raw model is independent. I believe the bias-corrected PM2.5 uses AirNow (not checked). |
| **GEFS-Aerosols** | 0.25° and 0.5°, 3-hourly | `noaa-gefs-pds/gefs.YYYYMMDD/00/chem/pgrb2ap25/` (200) | None (my understanding) |
| **GEOS-FP** `tavg1_2d_aer_Nx` | 0.25°×0.3125°, hourly, near real time; same species as MERRA-2 | `opendap.nccs.nasa.gov/dods/GEOS-5/fp/0.25_deg/assim/tavg1_2d_aer_Nx` (200) | MODIS AOD only (my understanding; not checked) |

#### 7. Other candidates

- **HAQES (GMU / NASA HAQAST):** 3-hourly ensemble-mean surface PM2.5 total, OC and BC over North America. 12 km, plus county and census-tract versions. Short names `HAQES_NA_PM25_{TOT,OC,BC}[_COUNTY|_CENSUS]` at GES DISC, listed under the AWS registry entry `nasa-haqast`. Members: HRRR-Smoke, GEFS-Aerosols, NAQFC, GEOS, NAAPS, ICAP-MME.
- **ACAG V6NA01 composition fields** (see section 5).
- **CAMS Europe** for European station comparisons, keeping in mind it assimilates EEA stations.
- **LGHAP v2:** global 1 km gap-free AOD and PM2.5 (Zenodo).
- **NOAA kerchunk references** on the AWS registry (`noaa-nodd-kerchunk`) cover NOAA operational forecast datasets; I did not check whether they include the AQM or chem outputs.

#### PM2.5 definition differences

- **FRM:** 24-hour filters equilibrated at 30–40% RH and 20–23 °C. AirNow hourly data come mostly from BAM/TEOM instruments, which are FEM, not FRM.
- **GEOS-CF `pm25_rh35`:** includes particle water at 35% RH, so it is closest to FRM.
- **ACAG:** reportedly at 35% RH (unverified, see section 5).
- **MERRA-2 and GEOS-FP sums:** dry mass with no nitrate. The ×1.375 sulfate factor treats sulfate as ammonium sulfate.
- **CAMS:** RH treatment needs checking.
- **ML products (CNN-MERRA2, GHAP, Di, FAQSD):** take whatever definition their training network uses.

#### Independence summary

| Status | Products |
|---|---|
| Independent of surface PM stations | GEOS-CF (raw), MERRA-2, GEOS-FP, CAMS EAC4 and global forecasts, HRRR-Smoke, GEFS-Aerosols, raw NAQFC |
| Not independent | MERRA2-CNN (OpenAQ), GHAP (OpenAQ, EPA, EEA, CNEMC and others), ACAG (monitor-calibrated), Di 2019, FAQSD (AQS), CAMS Europe (EEA), NAQFC bias-corrected, GEOS-CF ML station product |

**Sources:**
- [GMAO GEOS-CF FAQ](https://gmao.gsfc.nasa.gov/gmao-products/geos-cf/faq_geos-cf/)
- [GEOS-CF v2 upgrade news](https://gmao.gsfc.nasa.gov/news/geos-cf-gets-a-major-upgrade-in-geos-cf-version-2/)
- [Earth Engine GEOS-CF v2 htf](https://developers.google.com/earth-engine/datasets/catalog/NASA_GEOS-CF_v2_fcst_htf)
- [NASA virtual stores report (VEDA GEOS-CF Icechunk)](https://nasa-impact.github.io/virtual-stores-feasibility-report/nasa-applications.html)
- [Knowland GEOS-CF ML bias correction abstract](https://ntrs.nasa.gov/api/citations/20220014097/downloads/Session5-1_abstract380_Knowland_eDAA.pdf)
- [MERRA-2 FAQ (PM2.5 formula)](https://gmao.gsfc.nasa.gov/gmao-products/merra-2/faq_merra-2/)
- [Earthdata forum on PM2.5 units](https://forum.earthdata.nasa.gov/viewtopic.php?p=15229)
- [MERRA2_CNN_HAQAST_PM25 on data.gov](https://catalog.data.gov/dataset/merra2_cnn_haqast-bias-corrected-global-hourly-surface-total-pm2-5-mass-concentration-v1-m)
- [MERRA2_CNN_HAQAST_PM25 README](https://docserver.gesdisc.eosdis.nasa.gov/public/project/HAQAST/Pawan_Gupta/README_MERRA2_CNN_HAQAST_PM25_V1.pdf)
- [HAQAST poster (embassy/OpenAQ forecasts)](https://haqast.org/wp-content/uploads/sites/91/2025/11/JUNHYEON_SEO_HAQAST_Poster_Print_36x47.pdf)
- [Giovanni API forum thread](https://forum.earthdata.nasa.gov/viewtopic.php?p=25242)
- [ADS EAC4](https://ads.atmosphere.copernicus.eu/datasets/cams-global-reanalysis-eac4)
- [ADS CAMS Europe reanalyses](https://ads.atmosphere.copernicus.eu/datasets/cams-europe-air-quality-reanalyses)
- [CAMS ARCO announcement](https://atmosphere.copernicus.eu/work-progress-our-data-stores-turn-arco)
- [ACAG surface PM2.5](https://sites.wustl.edu/acag/datasets/surface-pm2-5/)
- [AWS registry satpmdata](https://github.com/awslabs/open-data-registry/blob/main/datasets/satpmdata.yaml)
- [AWS registry NASA HAQAST](https://registry.opendata.aws/nasa-haqast/)
- [GHAP Zenodo](https://zenodo.org/records/10800980)
- [GHAP supplementary information](https://www.atmos.umd.edu/~zli/PDF_papers/Wei_et_al-NatComm-2023-SI.pdf)
- [SEDAC Di et al. metadata](https://sedac.ciesin.columbia.edu/downloads/metadata/aqdh-pm2-5-concentrations-contiguous-us-1-km-v1-10-2000-2016.html)
- [EPA RSIG downloadable data (FAQSD)](https://www.epa.gov/hesc/rsig-related-downloadable-data-files)
- [MesoWest HRRR Zarr variables](https://mesowest.utah.edu/html/hrrr/zarr_documentation/html/zarr_variables.html)
- [dynamical.org HRRR analysis virtual](https://dynamical.org/catalog/noaa-hrrr-analysis-virtual/)
- [GMU HAQES](https://cser.science.gmu.edu/research/products/data-tools/hazardous-air-quality-ensemble-system-haqes/)</result>
<usage><subagent_tokens>137547</subagent_tokens><tool_uses>69</tool_uses><duration_ms>846024</duration_ms></usage>
</task-notification>

## Claude

Both research passes are done. Main findings that shape the questions:

- **The bias-corrected product is `MERRA2_CNN_HAQAST_PM25` V1.** It is hourly, 0.5°, 2000–present, and trained on more than 5,000 OpenAQ reference monitors, so it isn't independent of AQS, AirNow or embassy data.
- **GEOS-CF v1 ends 2026-01-02.** v2, starting 2025-08, now carries PM2.5 and PM10 at 35% RH.
- **None of GEOS-CF, MERRA-2 or CAMS has a time-series-chunked (ARCO) copy.** Extraction has to read whole time slices of global files, so adding sites costs little extra.
- **The State Department embassy monitors stopped reporting on 2025-03-04.** Their history (about 90 cities) is public on AirNow's S3 bucket.
- **"CanAiry" is WRI's CanAIRy Alert.** It is a forecasting programme built on GEOS-CF plus local monitors, not a sensor dataset. Its observations come from AirQo, AfriqAir and city networks, which are reachable directly or through OpenAQ.

*Asked:*

> **Scope:** Geographic scope for the station comparison? US EPA AQS (~1,000+ PM2.5 reference sites) is the deepest, best-QC'd reference; embassies (~90 cities, to Mar 2025), OpenAQ reference monitors, and SPARTAN give global coverage, mostly in places with few other monitors.
> - *US core + global tier (Recommended)*: Tier 1: AQS reference sites (like USCRN in the climate experiment). Tier 2: global — embassy posts, SPARTAN, and a stratified sample of OpenAQ reference monitors (Europe, India, China, LatAm, Africa). Rankings reported separately for each.
> - *Global, equal weight*: Sample reference monitors worldwide (stratified by region/pollution level) without privileging the US; AQS is one of many sources.
> - *US only*: AQS + IMPROVE/CSN + AirNow + low-cost sensors in the US. Simpler, but drops the embassies and the global question.
>
> **Pollutants:** Which pollutants? Gridded products and stations all have PM2.5; PM10 is in GEOS-CF v2, MERRA-2 (derived), CAMS, AQS, embassies (some), OpenAQ. Gases (O3, NO2, CO) are in GEOS-CF, CAMS, MERRA-2 GMI, and AQS/OpenAQ but not in the CNN or satellite PM products.
> - *PM2.5, PM10 + PM2.5 species (Recommended)*: PM2.5 and PM10 as headline variables; also compare model PM2.5 components (sulfate, OC, BC, dust, nitrate) against IMPROVE/CSN/SPARTAN speciated filters where available. No gases.
> - *PM + O3 and NO2*: Add hourly O3 and NO2 from GEOS-CF, CAMS and MERRA-2 GMI vs AQS/OpenAQ. Roughly doubles extraction and metrics work.
> - *PM2.5 and PM10 only*: Smallest scope: total mass only, no speciation, no gases.
>
> **Products:** Which gridded products besides the must-haves (GEOS-CF v1+v2, MERRA-2 aerosols-derived PM2.5/PM10, MERRA2_CNN_HAQAST_PM25)?
> - *CAMS EAC4 + CAMS global fcst*: ECMWF reanalysis (0.75°, 3-hourly, 2003–2025) and 0.4° hourly analysis/forecast (2015–). Assimilates satellite AOD only. Via the Atmosphere Data Store (your CDS key probably works).
> - *US models: HRRR-Smoke, NAQFC, HAQES*: HRRR smoke PM (3 km), NOAA AQM/NAQFC (12 km), and the GMU/NASA HAQES ensemble (12 km, 3-hourly). CONUS only; all on AWS without credentials.
> - *Satellite/ML: ACAG V6, GHAP*: WashU ACAG (van Donkelaar) 0.01° monthly PM2.5 + NA composition (s3://satpmdata), and GHAP 1 km daily global PM2.5 (2017–, Zenodo). Both station-trained, so not independent; monthly-scale comparison for ACAG.
> - *GEOS-FP aerosols*: Near-real-time MERRA-2 sibling (tavg1_2d_aer_Nx, 0.25°), for the recent window alongside GEOS-CF v2.
>
> **Stations:** Which station/sensor sources beyond EPA AQS, AirNow (recent months not yet in AQS), and the embassy historical files?
> - *OpenAQ reference monitors*: Global government monitors (EEA, CPCB India, LatAm, Africa, Australia...). Anonymous S3 archive for data; a free OpenAQ API key is needed to tell reference monitors from low-cost sensors.
> - *Filter networks: IMPROVE, CSN, SPARTAN*: Research-grade 24 h filter mass + speciation (US rural/urban, and ~25 global SPARTAN sites). The closest analog to USCRN. Every-3rd-day sampling.
> - *Free low-cost: AirQo, Sensor.Community, AirGradient*: Citizen-science/low-cost optical sensors (incl. the AirQo data behind WRI CanAIRy). Needs RH filtering and correction; reported as a separate tier.
> - *PurpleAir (paid API key)*: Dense US low-cost network with the EPA (Barkjohn) correction. API is billed in points; needs a key from you.

## User

*Answered:*

- Geographic scope for the station comparison? US EPA AQS (~1,000+ PM2.5 reference sites) is the deepest, best-QC'd reference; embassies (~90 cities, to Mar 2025), OpenAQ reference monitors, and SPARTAN give global coverage, mostly in places with few other monitors.
  → **US core + global tier (Recommended)**
- Which gridded products besides the must-haves (GEOS-CF v1+v2, MERRA-2 aerosols-derived PM2.5/PM10, MERRA2_CNN_HAQAST_PM25)?
  → **['CAMS EAC4 + CAMS global fcst', 'US models: HRRR-Smoke, NAQFC, HAQES', 'Satellite/ML: ACAG V6, GHAP', 'GEOS-FP aerosols']**
- Which pollutants? Gridded products and stations all have PM2.5; PM10 is in GEOS-CF v2, MERRA-2 (derived), CAMS, AQS, embassies (some), OpenAQ. Gases (O3, NO2, CO) are in GEOS-CF, CAMS, MERRA-2 GMI, and AQS/OpenAQ but not in the CNN or satellite PM products.
  → **PM + O3 and NO2**
- Which station/sensor sources beyond EPA AQS, AirNow (recent months not yet in AQS), and the embassy historical files?
  → **['OpenAQ reference monitors', 'Filter networks: IMPROVE, CSN, SPARTAN', 'Free low-cost: AirQo, Sensor.Community, AirGradient']**

## Claude

Recorded: US core plus a global tier; PM2.5, PM10, PM2.5 species, O3 and NO2; all of the extra products; and the OpenAQ, filter-network and free low-cost sources. A few more decisions:

*Asked:*

> **Period:** What period should the comparison cover? Records differ: GEOS-CF v1 runs 2018-01 to 2026-01 and v2 2025-08 onward; MERRA-2 runs 1980 onward; the CNN product 2000 onward; CAMS EAC4 2003–2025; GHAP 2017 onward; ACAG ends 2023. Embassies stop 2025-03. GEOS-CF has no time-series copy, so every extra year costs global-file reads.
> - *2018 → now, common 2018–2023 (Recommended)*: Extract every product from 2018-01 (the GEOS-CF era) to its end. Rank on a common window, 2018-01..2023-12, which every product but GEOS-CF v2 covers. Add a recent window, 2025-08..2026-10, for GEOS-CF v2, GEOS-FP and CAMS forecasts vs AirNow.
> - *Long record from 2003*: Extract MERRA-2, CNN, CAMS EAC4 and ACAG from 2003, and the others from their start. Gives trend and long-term statistics, but costs far more extraction time and disk.
> - *Short pilot window*: 2023-01..2024-12 only, covering wildfire-smoke 2023 and the embassies. Fast, but rankings rest on weaker statistics.
>
> **Remote pts:** Should I also add a tier of station-remote points, comparing products only with each other (like Tier 3 in the climate experiment)? For AQ this mainly shows how much products disagree where nobody measures, e.g. Africa, South America and remote US.
> - *Yes, ~100 global points (Recommended)*: About 100 points stratified by region × pollution regime (dust, smoke, urban, clean), far from any monitor. Scored by inter-product spread and departure from the ensemble median, at monthly scale.
> - *Yes, ~50 US points only*: Remote points within CONUS only, where the US-only models (HRRR-Smoke, NAQFC, HAQES) also apply.
> - *No*: Stations only.
>
> **Credentials:** Credentials. The OpenAQ API needs a free key, which classifies locations as reference vs low-cost and gives their metadata; the bulk data come from its anonymous S3. CAMS on the Atmosphere Data Store needs the licences accepted once on the ADS website for your ECMWF account; the CDS key in the environment usually works for ADS too. How should I handle these?
> - *Read from env; I'll add them (Recommended)*: Code reads OPENAQ_API_KEY and the existing CDSAPI_KEY. Sources whose credentials are missing or rejected are skipped cleanly and retried later. I'll tell you exactly which licence pages to accept if ADS refuses.
> - *Avoid the OpenAQ key*: Classify OpenAQ locations from the S3 archive's provider and sensor fields alone (heuristic reference vs low-cost list). No key needed. CAMS still uses the CDS key.
>
> **Site data:** Publishing the site data. Last time GitHub refused to create releases from this session type, and the data went to the assets repo. What should I plan for here?
> - *Try release; assets repo fallback (Recommended)*: Ask you before uploading, try the `air-quality-data-comparison` release first. If it's refused again, push to simon-code-research-assets at the very end (single commit) and pin it, as for the climate experiment.
> - *Assets repo directly*: Skip the release attempt and plan from the start for the assets repo with a pinned commit (still asking before pushing).
> - *Commit small data only*: Keep the site small enough (daily + monthly + metrics, no hourly) to commit to this repo directly; no release, no assets repo.

## User

*Answered:*

- Credentials. The OpenAQ API needs a free key, which classifies locations as reference vs low-cost and gives their metadata; the bulk data come from its anonymous S3. CAMS on the Atmosphere Data Store needs the licences accepted once on the ADS website for your ECMWF account; the CDS key in the environment usually works for ADS too. How should I handle these?
  → **Read from env; I'll add them (Recommended)**
- Publishing the site data. Last time GitHub refused to create releases from this session type, and the data went to the assets repo. What should I plan for here?
  → **Try release; assets repo fallback (Recommended)**
- Should I also add a tier of station-remote points, comparing products only with each other (like Tier 3 in the climate experiment)? For AQ this mainly shows how much products disagree where nobody measures, e.g. Africa, South America and remote US.
  → **Yes, ~100 global points (Recommended)**
- What period should the comparison cover? Records differ: GEOS-CF v1 runs 2018-01 to 2026-01 and v2 2025-08 onward; MERRA-2 runs 1980 onward; the CNN product 2000 onward; CAMS EAC4 2003–2025; GHAP 2017 onward; ACAG ends 2023. Embassies stop 2025-03. GEOS-CF has no time-series copy, so every extra year costs global-file reads.
  → **2018 → now, common 2018–2023 (Recommended)**

## Claude

Answers recorded. Writing the full plan now.

- **Write**: `~/.claude/plans/look-at-the-existing-resilient-crown.md`
- **ToolSearch**: `select:ExitPlanMode`

<details><summary><b>Proposed plan</b></summary>

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
| **GEOS-CF v1** (replay/assim) | NCCS OPeNDAP `opendap.nccs.nasa.gov/dods/gmao/geos-cf/assim/{aqc,chm}_tavg_1hr_g1440x721_v1`. Fallback: portal HTTPS netCDF (`portal.nccs.nasa.gov/datashare/gmao/geos-cf/v1/`) with HDF5 range reads | 0.25°, 1 h, 2018-01 → 2026-01-02 | pm25_rh35_gcc, pm25 components (bc, du, ni, oc, soa, ss, su), o3, no2 | No (independent) |
| **GEOS-CF v2** (ana + `v2_hindcast`) | OPeNDAP `geos-cf/v2/ana/{aqc,chm}_tavg_1hr_glo_L1440x721_slv`. Hindcast 2023–2025 from portal HTTPS | 0.25°, 1 h, 2023-01 → now (overlaps v1 for 3 years) | pm25_rh35, **pm10_rh35**, components, o3, no2 | No (satellite O3 only) |
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

GEOS-CF is the largest job: about 8 years hourly, aqc + chm. At the global-field rate it is about 1 TB of reads, so (b) is probably better. If neither is fast enough, I'll report at the pilot checkpoint. The fallback there is to limit GEOS-CF chm species to IMPROVE/CSN/SPARTAN days.

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
  - W-v1v2: 2023-01..2025-12, GEOS-CF v1 vs v2 against the same stations.
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

</details>

## User

[Request interrupted by user for tool use]

## Claude

No response requested.

## User

Do the datasets that work with no user intervention (API keys, license/data use agreements) first. Don't wait on my approvals (if needed), so you can get as far as you can without any of my intervention first.

## Claude

- **Edit**: `~/.claude/plans/look-at-the-existing-resilient-crown.md`

<details><summary><b>Proposed plan</b></summary>

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
| **GEOS-CF v1** (replay/assim) | NCCS OPeNDAP `opendap.nccs.nasa.gov/dods/gmao/geos-cf/assim/{aqc,chm}_tavg_1hr_g1440x721_v1`. Fallback: portal HTTPS netCDF (`portal.nccs.nasa.gov/datashare/gmao/geos-cf/v1/`) with HDF5 range reads | 0.25°, 1 h, 2018-01 → 2026-01-02 | pm25_rh35_gcc, pm25 components (bc, du, ni, oc, soa, ss, su), o3, no2 | No (independent) |
| **GEOS-CF v2** (ana + `v2_hindcast`) | OPeNDAP `geos-cf/v2/ana/{aqc,chm}_tavg_1hr_glo_L1440x721_slv`. Hindcast 2023–2025 from portal HTTPS | 0.25°, 1 h, 2023-01 → now (overlaps v1 for 3 years) | pm25_rh35, **pm10_rh35**, components, o3, no2 | No (satellite O3 only) |
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

GEOS-CF is the largest job: about 8 years hourly, aqc + chm. At the global-field rate it is about 1 TB of reads, so (b) is probably better. If neither is fast enough, I'll report at the pilot checkpoint. The fallback there is to limit GEOS-CF chm species to IMPROVE/CSN/SPARTAN days.

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
  - W-v1v2: 2023-01..2025-12, GEOS-CF v1 vs v2 against the same stations.
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
| **No intervention** | AQS, AirNow, embassies, FED (IMPROVE/CSN), SPARTAN, Sensor.Community, AirGradient public API, OpenAQ S3 archive, GEOS-CF v1/v2 and GEOS-FP (NCCS), HRRR-Smoke, NAQFC, ACAG (`satpmdata`), GHAP open Zenodo years |
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

</details>

Checking that bucket now.

- **Bash**: List top level of GEOS-CF public S3 bucket: `cd /tmp && for r in us-west-2 us-east-1; do echo "== $r"; timeout 60 curl -s "https://smce-geos-cf-public.s3.$r.amazonaws.com/?list-type=2&delimiter=/" | head …`

The bucket also has `geos-cf-rpl.zarr` and `geos-cf-v2-rpl.zarr`, which look like full replay archives. Checking their metadata.

- **Bash**: List contents of GEOS-CF Zarr stores: `B=https://smce-geos-cf-public.s3.us-west-2.amazonaws.com; for z in geos-cf-rpl.zarr geos-cf-v2-rpl.zarr geos-cf-v2-ana-latest.zarr; do echo "=== $z"; curl -s "…`
- **Bash**: Inspect Zarr metadata for time and chunking: `cd /tmp && B=https://smce-geos-cf-public.s3.us-west-2.amazonaws.com; for z in geos-cf-rpl.zarr geos-cf-v2-rpl.zarr geos-cf-v2-ana-latest.zarr; do echo "=== $z"…`
- **Edit**: `~/.claude/plans/look-at-the-existing-resilient-crown.md`
- **Edit**: `~/.claude/plans/look-at-the-existing-resilient-crown.md`
- **Edit**: `~/.claude/plans/look-at-the-existing-resilient-crown.md`
- **Edit**: `~/.claude/plans/look-at-the-existing-resilient-crown.md`

<details><summary><b>Proposed plan</b></summary>

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

</details>

Plan approved. Starting setup: branch, scaffold, PROMPT.md and PLAN.md.

- **Bash**: Check git state and installed tools: `git status --short | head; git branch -a; git log --oneline -1; cat climate-product-compare/.gitignore; ls ~/.local/bin 2>/dev/null; which mise uv node python3…`
- **Bash**: Write PROMPT.md and PLAN.md and commit separately: `mkdir -p /home/user/simon-code-research/air-quality-data-comparison && cd /home/user/simon-code-research/air-quality-data-comparison && cat > PROMPT.md <<'EOF'…`

Now the code scaffold. Reading the climate modules to vendor.

- **Bash**: Read grid, config, parallel, http modules: `cd /home/user/simon-code-research/climate-product-compare/src/cpc && cat grid.py config.py parallel.py http.py`
- **Bash**: Read store, base, extract modules: `cd /home/user/simon-code-research/climate-product-compare/src/cpc && cat store.py && sed -n 80,184p products/base.py && cat extract.py`

The code is substantial, so I'll track the work with a task list.

- **ToolSearch**: `select:TaskCreate,TaskUpdate`
- **TaskCreate**: `{"subject": "Scaffold project and access smoke tests", "description": "pyproject/mise/vendored store+grid; results/access_check.md", "activeForm": "Scaffolding…`
- **TaskCreate**: `{"subject": "Ingest station observations and build site lists", "description": "AQS, AirNow, embassy, IMPROVE/CSN, SPARTAN, OpenAQ, low-cost; tiers + remote po…`
- **TaskCreate**: `{"subject": "Extract gridded products at sites", "description": "GEOS-CF v1/v2, MERRA-2, CNN, ACAG, HRRR-Smoke, NAQFC, GEOS-FP, CAMS, GMI, HAQES, GHAP", "activ…`
- **TaskCreate**: `{"subject": "Metrics, figures, site, docs", "description": "metrics, figures, static site, README, root README, TRANSCRIPT; then ask about publishing", "active…`
- **TaskUpdate**: `{"taskId": "1", "status": "in_progress"}`
- **Bash**: Install mise locally: `cd /tmp && (curl -fsSL https://mise.run | MISE_INSTALL_PATH=~/.local/bin/mise sh) 2>&1 | tail -3; ~/.local/bin/mise --version`
- **Bash**: Scaffold project files and install dependencies: `cd /home/user/simon-code-research/air-quality-data-comparison && mkdir -p src/aqc/obs src/aqc/products tests results/sites scripts && SRC=../climate-product-co…`

Dependencies installed. Smoke-testing GEOS-CF Zarr reads first.

- **Bash**: Probe GEOS-CF Zarr time range and read speed: `cat > /tmp/claude-0/-home-user-simon-code-research/4ee5e97b-d28f-575d-b1d9-fc903fcb4391/scratchpad/geoscf_probe.py <<'EOF' import time, zarr, numpy as np, pand…`

Both time axes are longer than their span in hours, which suggests duplicated or out-of-order steps. Checking.

- **Bash**: Inspect GEOS-CF Zarr time axis irregularities: `uv run python -c " import zarr, numpy as np for name in ['geos-cf-rpl.zarr','geos-cf-v2-rpl.zarr']: g = zarr.open_group(f's3://smce-geos-cf-public/{name}', mod…`

Duplicate months have been re-appended. I'll keep the last occurrence of each timestamp. Next, the compressed chunk size, which sets the cost per 50×50 tile.

- **Bash**: Check compressed chunk sizes in GEOS-CF Zarr: `B=https://smce-geos-cf-public.s3.us-west-2.amazonaws.com; for v in pm25_rh35_gcc o3 no2; do curl -s "$B/?list-type=2&prefix=geos-cf-rpl.zarr/$v/50.0.&max-keys=…`
- **Bash**: Probe reachability of all data sources: `cd /tmp; p(){ printf "%-60s %s\n" "$1" "$(curl -s -o /dev/null -w '%{http_code} %{size_download}' --max-time 40 -r 0-1000 "$2")"; } p AQS_hourly88101_2023 http…`
- **Bash**: Explore OpenAQ archive structure and sample file: `B=https://openaq-data-archive.s3.amazonaws.com; curl -s "$B/?list-type=2&delimiter=/" | grep -o '<Prefix>[^<]*</Prefix>\|<Key>[^<]*</Key>'; curl -s "$B/?list-t…`
- **Bash**: Vendor and adapt store.py: `cd /home/user/simon-code-research/air-quality-data-comparison && python3 - <<'EOF' src = open('../climate-product-compare/src/cpc/store.py').read() src = src.r…`
- **Bash**: Patch store writes and add FieldProduct base: `python3 - <<'EOF' p='src/aqc/store.py'; s=open(p).read() old=''' # write site-by-site in sorted contiguous runs (cheap, and chunk-aligned on site) for k, si in…`
- **Bash**: Write extract runner and product registry: `cat > src/aqc/extract.py <<'EOF' """Extraction / update runner: product x sites -> Icechunk group products/<name>/<freq>. Adapted from climate-product-compare/…`
- **Bash**: Write GEOS-CF product and smoke test it: `cat > src/aqc/products/geoscf.py <<'EOF' """GEOS-CF v1 and v2 replay from NASA SMCE public Zarr stores (anonymous S3, us-west-2). s3://smce-geos-cf-public/geos…`

The raw gases are mol/mol, so rounding to 2 places shows 0. Checking the converted values.

- **Bash**: Check GEOS-CF converted monthly means: `uv run python - 2>&1 <<'EOF' | grep -v UV_NATIVE import sys, pandas as pd, numpy as np, time sys.path.insert(0, "src") from aqc.products import registry sites …`

Converters receive keyword arguments named after the source variable. Fixing with a generic scaler.

- **Bash**: Add converters and rerun GEOS-CF check: `python3 - <<'EOF' p='src/aqc/products/base.py'; s=open(p).read() s=s.replace('''@dataclass class Var:''','''def scale(factor: float, offset: float = 0.0): """C…`

GEOS-CF works: about 5 s per month-chunk for three tiles, and magnitudes look right, including v1's known high PM bias. Next is the AQS site selection, starting with the annual completeness files.

- **Bash**: Download AQS metadata and annual summary: `mkdir -p /home/user/simon-code-research/air-quality-data-comparison/data/cache/aqs && cd /home/user/simon-code-research/air-quality-data-comparison/data/cache/…`
- **Bash**: Download AQS annual files and start hourly downloads: `for y in 2018 2019 2020 2021 2022 2024 2025; do curl -sfO https://aqs.epa.gov/aqsweb/airdata/annual_conc_by_monitor_$y.zip; done; ls; nohup bash -c 'for p in 8…`

While that downloads, checking the embassy, SPARTAN and IMPROVE file formats.

- **Bash**: List embassy historical folders and files: `B=https://s3-us-west-1.amazonaws.com/files.airnowtech.org; curl -s "$B/?list-type=2&prefix=airnow/EmbassyHistorical/&delimiter=/&max-keys=200" | grep -o '<Pref…`
- **Bash**: List one embassy folder: `B=https://s3-us-west-1.amazonaws.com/files.airnowtech.org; curl -s "$B/?list-type=2&prefix=airnow/EmbassyHistorical/NewDelhi/" | grep -o '<Key>[^<]*</Key>' | s…`
- **Bash**: Inspect embassy CSV format: `B=https://s3-us-west-1.amazonaws.com/files.airnowtech.org/airnow/EmbassyHistorical; curl -s "$B/NewDelhi/2023/NewDelhi_PM2.5_2023_YTD.csv" | head -4; curl -s "…`

The embassy CSVs have no coordinates, and the 2025 folder holds files through December. Checking whether reporting resumed and where to get coordinates.

- **Bash**: Check embassy 2025-26 coverage and AirNow site files: `B=https://s3-us-west-1.amazonaws.com/files.airnowtech.org; curl -s "$B/airnow/EmbassyHistorical/NewDelhi/2025/NewDelhi_PM2.5_2025_YTD.csv" | awk -F, 'NR>1{prin…`
- **Bash**: Find coordinates for embassy monitors: `B=https://s3-us-west-1.amazonaws.com/files.airnowtech.org; curl -s "$B/?list-type=2&prefix=airnow/2026/20261101/&max-keys=100" | grep -o '<Key>[^<]*</Key>' | s…`

Embassy sites appear in AirNow's site list (agency "U.S. Department of State …") with coordinates and UTC offsets, so I'll match folders by city name. Next, SPARTAN and IMPROVE.

- **Bash**: Explore SPARTAN bucket: `B=https://spartan-cloud.s3.amazonaws.com; curl -s "$B/?list-type=2&delimiter=/" | grep -o '<Prefix>[^<]*</Prefix>' ; curl -s "$B/?list-type=2&delimiter=/&prefi…`
- **Bash**: List SPARTAN product files: `B=https://spartan-cloud.s3.amazonaws.com; for p in FilterBased TimeResPM25; do curl -s "$B/?list-type=2&prefix=GroupByProduct/$p/&max-keys=60" | grep -o '<Key>…`
- **Bash**: Inspect SPARTAN file formats: `B=https://spartan-cloud.s3.amazonaws.com/GroupByProduct; curl -s "https://spartan-cloud.s3.amazonaws.com/?list-type=2&prefix=GroupByProduct/FilterBased/&delimi…`

SPARTAN has hourly and daily nephelometer-estimated PM2.5 in local time, plus multi-day filter species. For IMPROVE and CSN, AQS's own speciation files are simpler than FED. Checking their size.

- **Bash**: Check AQS speciation file size and download progress: `for f in daily_SPEC_2023.zip daily_81102_2023.zip; do curl -sI https://aqs.epa.gov/aqsweb/airdata/$f | grep -i content-length; done; cat /home/user/simon-code-…`

Downloads run at roughly 40 MB/min, so about 50 minutes for everything. Meanwhile, writing AQS site selection from the annual completeness files.

- **Bash**: Explore AQS annual summary contents: `cd /home/user/simon-code-research/air-quality-data-comparison && uv run python - 2>&1 <<'EOF' | grep -v UV_NATIVE import pandas as pd, zipfile, glob dfs=[] for…`
- **Bash**: Write AQS module and test site selection: `cat > src/aqc/obs/aqs.py <<'EOF' """US EPA AQS pre-generated files (https://aqs.epa.gov/aqsweb/airdata/download_files.html). Validated regulatory data, no key.…`

1,309 AQS sites after thinning. Next: embassy and SPARTAN ingest, a shared observation writer, and the combined site table, so the long GEOS-CF extraction can start early.

- **Bash**: Inspect AirNow site location file for DOS sites: `B=https://s3-us-west-1.amazonaws.com/files.airnowtech.org; curl -s "$B/airnow/2026/20261101/Monitoring_Site_Locations_V2.dat" | head -2; curl -s "$B/airnow/202…`
- **Bash**: Write embassy module and build its site list: `cat > src/aqc/obs/embassy.py <<'EOF' """US Department of State embassy/consulate PM2.5 monitors (AirNow "EmbassyHistorical" files). s3://files.airnowtech.org/a…`
- **Bash**: Fix location lookup and rebuild embassy sites: `python3 - <<'EOF' p='src/aqc/obs/embassy.py'; s=open(p).read() s=s.replace(''' for d in pd.date_range(end=pd.Timestamp.now().normalize(), periods=10, freq="-1D…`

85 embassy sites matched; the 3 unmatched are duplicates of other folders. Now SPARTAN, using `timezonefinder` to convert local time to UTC.

- **Bash**: Write SPARTAN module and test it: ``uv add timezonefinder 2>&1 | tail -1 && cat > src/aqc/obs/spartan.py <<'EOF' """SPARTAN global PM2.5 network (https://www.spartan-network.org), public S3 ``spa…``

19 SPARTAN sites have data from 2018 on. Now the site-table builder, the observation writer and a CLI.

- **Bash**: Write regions, sites and observation writer modules: `cat > src/aqc/regions.py <<'EOF' """Coarse world regions from lat/lon (for stratified summaries; boxes, not borders).""" from __future__ import annotations imp…`
- **Bash**: Write CLI and build embassy/SPARTAN site tables: `cat > src/aqc/cli.py <<'EOF' """Command line: aqc sites | obs | extract | update | status | metrics | figures | sitedata.""" from __future__ import annotations…`

Building the AQS site table, then a short end-to-end extraction test before launching GEOS-CF in full.

- **Bash**: Build AQS site table and find pilot candidates: `uv run aqc sites --networks aqs 2>&1 | grep -v UV_NATIVE | tail -2 && uv run python - <<'EOF' 2>&1 | grep -v UV_NATIVE import sys; sys.path.insert(0,"src") imp…`
- **Bash**: Set pilot sites and test extraction end-to-end: `python3 - <<'EOF' p='src/aqc/sites.py'; s=open(p).read() i=s.index('PILOT = ['); s=s[:i]+'''PILOT = [ # 18 sites: 10 AQS (West smoke, East, rural), 5 embassies…`
- **Bash**: Fix start parsing and rerun pilot test: `sed -i 's/ t_first = max(config.START, product.start, t_start or config.START)/ t_first = max(config.START, product.start, pd.Timestamp(t_start) if t_start is …`

The pipeline works end to end. Launching full GEOS-CF v1 + v2 extraction for all 1,413 current sites in the background. That's the largest read job; sites added later get their own pass.

- **Bash**: Launch full GEOS-CF extraction in background: `rm -rf data/store && mkdir -p data/logs && ICECHUNK_LOG=error nohup uv run aqc extract geoscf_v1 geoscf_v2 --sites all > data/logs/geoscf.log 2>&1 & sleep 90; …`
- **Agent**: MERRA-2 family + GEOS-FP readers (fork)
- **Agent**: US regional model readers (fork)
- **Agent**: CAMS, ACAG, GHAP readers (fork)

Three agents are writing the product readers. Meanwhile I'll commit the scaffold and continue with observations.

- **Bash**: Commit scaffold and push branch: `cd /home/user/simon-code-research && git add air-quality-data-comparison/{.gitignore,mise.toml,pyproject.toml,uv.lock,src/aqc/__init__.py,src/aqc/config.py,src…`

While AQS downloads finish, inspecting AQS speciation files for IMPROVE/CSN filter species.

- **Bash**: Inspect AQS speciation parameters: `cd /home/user/simon-code-research/air-quality-data-comparison/data/cache/aqs && curl -sfO https://aqs.epa.gov/aqsweb/airdata/daily_SPEC_2023.zip && unzip -o -q…`
- **Bash**: Download AQS speciation files 2018-2025: `for y in 2018 2019 2020 2021 2022 2024 2025; do curl -sf --retry 3 -O https://aqs.epa.gov/aqsweb/airdata/daily_SPEC_$y.zip; done; ls -la daily_SPEC*; cat dl.log`
- **Bash**: Write speciation module and add filter sites: `cd /home/user/simon-code-research/air-quality-data-comparison && cat > src/aqc/obs/speciation.py <<'EOF' """IMPROVE and CSN 24-h filter PM2.5 speciation from A…`

The site table now has 1,519 sites, including 106 new filter-only sites. Next, low-cost sensors: checking how Sensor.Community's archive is organized for bulk access.

- **Bash**: Explore Sensor.Community archive layout: `curl -s https://archive.sensor.community/csv_per_month/ | grep -o 'href="[^"]*"' | head -5; curl -s https://archive.sensor.community/csv_per_month/2023-07/ | g…`
- **Bash**: Check archive top level for parquet: `curl -s https://archive.sensor.community/ | grep -o 'href="[^"]*"' | grep -v '20[12][0-9]-[0-9]' ; curl -s https://archive.sensor.community/2023-07-01/ | grep …`
- **Bash**: Check Sensor.Community yearly folders: `curl -s https://archive.sensor.community/2023/ | grep -o 'href="[^"]*"' | head -5; curl -s https://archive.sensor.community/2023/2023-07-01/ | grep -o 'href="[…`
- **Bash**: Fetch Sensor.Community live sensor list: `mkdir -p data/cache/sensorcommunity && curl -s --max-time 120 -o data/cache/sensorcommunity/data.json https://data.sensor.community/static/v2/data.json; ls -la…`
- **Bash**: Write low-cost module and test node selection: `cat > src/aqc/obs/lowcost.py <<'EOF' """Low-cost sensors: Sensor.Community (archive.sensor.community, ODbL; no key). Locations come from the live list (data.se…`
- **Bash**: Add European nodes, build low-cost sites, start fetch: `python3 - <<'EOF' p='src/aqc/obs/lowcost.py'; s=open(p).read() s=s.replace('def sites(reference: pd.DataFrame, n_sparse: int = 45, n_coloc: int = 35, log=print…`

AQS downloads are done and GEOS-CF v1 is about 40 % through. Starting observation ingest for AQS, embassies, SPARTAN and speciation in the background.

- **Bash**: Start reference observation ingest: `ICECHUNK_LOG=error nohup uv run aqc obs --networks embassy,spartan,speciation,aqs > data/logs/obs_ref.log 2>&1 & sleep 120; grep -v UV_NATIVE /home/user/simon-…`
- **Bash**: Check ingest logs and system load: `tail -5 data/logs/obs_ref.log; tail -3 data/logs/obs_lowcost.log; uptime; free -g | head -2`

The machine is under heavy load: load average 22 and only 2 GB of memory free. Checking which processes are responsible.

- **Bash**: List top memory processes: `ps -eo pid,rss,pcpu,etime,args --sort=-rss | head -15 | cut -c1-200`

The NAQFC full extraction is using 6 GB on a 15 GB machine. Asking that agent to cut its memory use.

- **SendMessage**: ``{"to": "a1e763e8bfbf6466c", "summary": "naqfc using 6 GB RSS, reduce", "message": "Heads-up from the main session: your `aqc extract naqfc --sites all` process…``

While waiting, writing the remote-point sampler. The pollution classes will come from the ACAG annual-mean PM2.5 map, which also masks ocean. Finding a coarse annual file.

- **Bash**: Find ACAG 0.1-degree annual files: `B=https://satpmdata.s3.amazonaws.com; curl -s "$B/?list-type=2&prefix=V6GL03/&delimiter=/" | grep -o '<Prefix>[^<]*</Prefix>'; curl -s "$B/?list-type=2&prefix=…`
- **Bash**: List ACAG 0.1-degree annual 2021 files: `B=https://satpmdata.s3.amazonaws.com; curl -s "$B/?list-type=2&prefix=V6GL03/CNNPM25c0p10/Annual/" | grep -o '<Key>[^<]*2021[^<]*</Key>' | sed 's/<[^>]*>//g'`
- **Bash**: Write remote-point sampler and generate points: `cat > src/aqc/remote.py <<'EOF' """Station-remote points (Tier 4): ~100 land points far from any known monitor. * Pollution map: ACAG V6.GL.03 annual-mean PM2.…`

The ACAG map has values over the ocean too (181k "land" cells), so I need a real land mask. Adding `global-land-mask`, which works offline.

- **Bash**: Add land mask and resample remote points: `uv add global-land-mask 2>&1 | tail -1 && python3 - <<'EOF' p='src/aqc/remote.py'; s=open(p).read() s=s.replace(''' df = df[(df.lat >= -56) & (df.lat <= 70)] '…`

One of the "Middle East" points is actually in Sudan; the region boxes overlap around the Red Sea. Fixing the boxes and recomputing regions when the tables load.

- **Bash**: Fix region boxes and check site counts: `python3 - <<'EOF' p='src/aqc/regions.py'; s=open(p).read() s=s.replace(''' ("Europe", 35, 72, -25, 40), ("Middle East", 12, 42, 34, 63), ("Africa", -36, 37.5, …`

SPARTAN's time axis runs to 2167, so at least one row has a bad date. Clipping all observation times to the present and re-ingesting SPARTAN.

- **Bash**: Clip obs times and re-ingest SPARTAN: `python3 - <<'EOF' p='src/aqc/obs/ingest.py'; s=open(p).read() s=s.replace(''' frames = {k: v.dropna(subset=["value"]) for k, v in frames.items() if len(v)}''',…`

Reference observations are ingesting. Next, the analysis layer. Reading the climate experiment's analysis and metrics code to adapt.

- **Bash**: Read climate analysis and metrics code: `cd /home/user/simon-code-research/climate-product-compare/src/cpc && sed -n 1,172p analysis.py && sed -n 60,135p metrics.py && sed -n 153,281p metrics.py`
- **Bash**: Write analysis module: `cd /home/user/simon-code-research/air-quality-data-comparison && cat > src/aqc/analysis.py <<'EOF' """Loading, interpolation and time aggregation for compariso…`
- **Bash**: Write metrics module and check progress: `cat > src/aqc/metrics.py <<'EOF' """Skill metrics: products vs observations (Tiers 1-3) and products vs each other (Tier 4). Rows: site x product x var x scale…`

SPEC and embassy observations are in, and AQS is ingesting at about 40 s per year-file. Testing the metrics on an embassy site against the partly extracted GEOS-CF v1.

- **Bash**: Test metrics on embassy and IMPROVE sites: `ICECHUNK_LOG=error uv run python - 2>&1 <<'EOF' | grep -v UV_NATIVE import sys, time; sys.path.insert(0,"src") import pandas as pd from aqc import sites, metri…`

Something was killed for lack of memory. Checking what's still running.

- **Bash**: Check surviving processes and log tails: `ps -eo pid,rss,pcpu,etime,args --sort=-rss | grep -v grep | grep 'aqc\|python' | head -15 | cut -c1-180; free -g | head -2; cd /home/user/simon-code-research/a…`

The MERRA-2 run appears to be the process the OOM killer took. Too many full extractions are running at once, so I'm asking all three agents to run only one at a time.

- **SendMessage**: `{"to": "acd5b20829716d9d6", "summary": "OOM: merra2 likely killed; limit concurrency", "message": "Main session: the kernel just OOM-killed a process (machine …`
- **SendMessage**: `{"to": "a1395b88f3eeb28ee", "summary": "OOM on machine; one run at a time", "message": "Main session: the kernel just OOM-killed a process (15 GB machine, ~10 …`
- **SendMessage**: `{"to": "a1e763e8bfbf6466c", "summary": "OOM on machine; one run at a time", "message": "Main session: the kernel just OOM-killed a process (15 GB machine, ~10 …`
- **Bash**: Fix fractional-offset timestamps and re-test: `sed -i 's/"time": t.dt.round("h"), "value": v}/"time": t.dt.ceil("h"), "value": v}/' src/aqc/obs/embassy.py src/aqc/obs/spartan.py && grep -n 'ceil("h")' src/a…`
- **Bash**: Check disk usage of store and caches: `df -h / | tail -1; du -sh data/store/* data/cache 2>/dev/null | sort -h | tail -12`
- **Bash**: Add periodic compaction to runner and loop: `python3 - <<'EOF' p='src/aqc/extract.py'; s=open(p).read() old=''' session = repo.writable_session("main") w = store.GroupWriter(session, path, product.freq, h…`
- **Bash**: Add retry to field product block reads: `python3 - <<'EOF' p='src/aqc/products/base.py'; s=open(p).read() old=''' def one(key): try: return self.read_block(key, st) except FileNotFoundError: return No…`

The low-cost fetch failed on a missing archive day (2023-07-14 returns 404). Making missing days return an empty listing and restarting the fetch.

- **Bash**: Handle missing archive days and restart low-cost fetch: `python3 - <<'EOF' p='src/aqc/obs/lowcost.py'; s=open(p).read() old='''def _day_listing(day: pd.Timestamp) -> set[str]: txt = get(''' new='''def _day_listing(da…`

While those run, adding the `metrics` command: site-parallel with two worker processes to stay within memory, plus the remote-point comparisons.

- **Bash**: Add metrics CLI command and test on pilot: `python3 - <<'EOF' p='src/aqc/cli.py'; s=open(p).read() s=s.replace('''def cmd_status(a):''','''def _metrics_one(args): site, products, root = args from . impor…`

The pilot metrics run hung. The likely cause is forking after Icechunk's runtime threads have started, which the vendored `parallel.py` warns about. Switching the pool to `spawn`.

- **Bash**: Use spawn context for metrics pool and retest: `pkill -f "aqc metrics" ; python3 - <<'EOF' p='src/aqc/cli.py'; s=open(p).read() s=s.replace(''' with ProcessPoolExecutor(a.workers) as ex:''',''' import multip…`

Fixed: 18 sites now take 10 s. Next is the website. Reading the climate site's export code and front end to adapt.

- **Bash**: Read climate site export and front-end config: `cd /home/user/simon-code-research/climate-product-compare && cat src/cpc/export_site.py | sed -n 1,165p; cat site/package.json site/vite.config.js site/index.h…`
- **Bash**: Read climate site main.js (first part): `cd /home/user/simon-code-research/climate-product-compare/site && cat src/main.js | head -300`
- **Bash**: Read rest of climate main.js: `cd /home/user/simon-code-research/climate-product-compare/site && sed -n 300,466p src/main.js; wc -c src/style.css`

Before writing chart code for the site and figures, loading the dataviz guidance.

- **Skill**: `dataviz`
- **Bash**: Write site export and copy site scaffolding: `cd /home/user/simon-code-research/air-quality-data-comparison && cat > src/aqc/export_site.py <<'EOF' """Export per-site data for the static website (site/publ…`

Running the palette validator on the reused colors, as the skill requires.

- **Bash**: Validate site palette light and dark: `cd /tmp/claude-0/bundled-skills/2.1.326/dc9e0db593449be77b4c84d05242f0aa/dataviz && node scripts/validate_palette.js "#2a78d6,#eb6834,#1baf7a,#eda100,#e87ba4,#…`

The palette passes in both modes. The light-mode contrast WARN for three hues is covered by the legend and the metrics tables. Writing the site front end.

- **Bash**: Write site index and main.js, install npm deps: `cd /home/user/simon-code-research/air-quality-data-comparison/site && cat > index.html <<'EOF' <!doctype html> <html lang="en"> <head> <meta charset="utf-8" />…`
- **Bash**: Check all background job logs: `cd /home/user/simon-code-research/air-quality-data-comparison && for f in data/logs/*.log; do echo "== $f: $(grep -v UV_NATIVE $f | grep -v '^\s*$' | tail -1 |…`

The AQS ingest log hasn't moved since 04:24, which is about when the OOM kill happened. Checking whether it's still alive.

- **Bash**: Check whether obs ingest processes are alive: `ps -eo pid,rss,pcpu,etime,args | grep 'aqc obs' | grep -v grep | cut -c1-150; ls -la /home/user/simon-code-research/air-quality-data-comparison/data/store/ | g…`

The AQS ingest was the process the OOM killer took. Reworking it to be lighter: one variable at a time, the pyarrow CSV engine, categorical site ids and float32 values. Then restarting it.

- **Bash**: Make AQS ingest memory-light and restart it: `python3 - <<'EOF' p='src/aqc/obs/aqs.py'; s=open(p).read() old=''' d = read_zip_csv(f"hourly_{param}_{year}", usecols=cols, dtype={"State Code": str, "County C…`

The pyarrow engine parses `Date GMT` as a date. Forcing it and `Time GMT` to strings, then restarting.

- **Bash**: Fix date dtype and restart AQS ingest: `pkill -f "aqc obs --networks aqs"; sleep 2; sed -i 's/ dtype={"State Code": str, "County Code": str, "Site Num": str})\n d\["site_id"\] = site_id(d)\n d = d\[d…`
- **Bash**: Write figures module and render the site map: `cat > src/aqc/figures.py <<'EOF' """Static figures for the README (results/figures/*.png), from the merged metrics table. Colours follow the site's validated p…`
- **Read**: `air-quality-data-comparison/results/figures/sites_map.png`

The map looks right. I'll reorder the legend to tiers 1–4 later. Committing progress.

- **Bash**: Fix legend order and check git status: `python3 - <<'EOF' p='src/aqc/figures.py'; s=open(p).read() s=s.replace(''' ax.legend(loc="lower left", frameon=False, fontsize=8)''',''' h, lab = ax.get_legend…`
- **Bash**: Commit progress and push: `cd /home/user/simon-code-research && git add air-quality-data-comparison/ && git status --short | grep -v '^A\|^M' | head; git commit -qm "air-quality-data-com…`

Committed and pushed. Most remaining work waits on the long extractions, so I'll use a monitor rather than polling.

- **ToolSearch**: `select:Monitor`
- **TaskUpdate**: `{"taskId": "1", "status": "completed"}`
- **TaskUpdate**: `{"taskId": "2", "status": "in_progress"}`
- **Monitor**: `{"description": "AQS + low-cost obs ingest completion/failures", "timeout_ms": 1800000, "command": "cd /home/user/simon-code-research/air-quality-data-comparis…`

While waiting, writing unit tests for the stencil, LST daily means, MDA8, monthly completeness, species mapping and regions.

- **Bash**: Write and run unit tests: `cd /home/user/simon-code-research/air-quality-data-comparison && cat > tests/test_analysis.py <<'EOF' import numpy as np import pandas as pd from aqc import an…`

All 7 tests pass. Adding the `mise` tasks and `publish.toml` while the jobs run.

- **Bash**: Add mise tasks: `cat >> mise.toml <<'EOF' [tasks.sites] description = "Build site tables (results/sites/*.csv): AQS, IMPROVE/CSN, embassies, SPARTAN, Sensor.Community, remote p…`

Everything left now depends on the running jobs: AQS and low-cost ingest, GEOS-CF, ACAG, HRRR-Smoke, the MERRA-2 queue and the NAQFC/HAQES queue. I'll continue as they finish.

- **Bash**: Commit and push pending changes: `cd /home/user/simon-code-research && git add air-quality-data-comparison/ && git commit -qm "air-quality-data-comparison: mise tasks, unit tests, figure legend…`

Committed and pushed. The tree is clean, and the background ingest and extraction jobs are still running.

## User

<task-notification>
<task-id>a1395b88f3eeb28ee</task-id>
<output-file>/tmp/claude-0/-home-user-simon-code-research/4ee5e97b-d28f-575d-b1d9-fc903fcb4391/tasks/a1395b88f3eeb28ee.output</output-file>
<status>completed</status>
<summary>Agent "CAMS, ACAG, GHAP readers" finished</summary>
<note>A task-notification fires each time this agent stops with no live background children of its own. The user can send it another message and resume it, so the same task-id may notify more than once.</note>
<result>That notification is from the earlier GHAP launcher, which I stopped on purpose after your memory warning. The work it was meant to start is already queued. One background chain now runs my jobs strictly one at a time: ACAG (running), then GHAP monthly (`ghap_m`), then GHAP daily (`ghap`). My report above stands.</result>
<usage><subagent_tokens>334872</subagent_tokens><tool_uses>30</tool_uses><duration_ms>1971973</duration_ms></usage>
</task-notification>

## Claude

No change from the CAMS/ACAG/GHAP agent's earlier report. ACAG is extracting now; GHAP monthly and then GHAP daily follow, one at a time. I'm waiting on the other running jobs.

## User

<task-notification>
<task-id>acd5b20829716d9d6</task-id>
<output-file>/tmp/claude-0/-home-user-simon-code-research/4ee5e97b-d28f-575d-b1d9-fc903fcb4391/tasks/acd5b20829716d9d6.output</output-file>
<status>completed</status>
<summary>Agent "MERRA-2 family + GEOS-FP readers" finished</summary>
<note>A task-notification fires each time this agent stops with no live background children of its own. The user can send it another message and resume it, so the same task-id may notify more than once.</note>
<result>Implemented four registered readers plus a fast remote-HDF5 helper. Three full extractions are queued in the main store; `merra2_gmi_gas` works but is too slow for a full pass, so it isn't queued. Nothing committed to git.

**Modules (all under `src/aqc/products/`)**
- `h5remote.py`: a helper that reads the chunk index once with h5py, fetches each variable's chunks in a few merged range requests in parallel, and decodes them locally (shuffle + deflate). Plain h5py over fsspec took 88 s for one MERRA-2 variable-day; this reads all 7 in about 11 s, with exact agreement to h5py.
  - It also supports reading a single level (`level=(axis, index)`).
- `merra2.py`: `MERRA2` (`merra2`) and `MERRA2CNN` (`merra2_cnn`). Days are read in parallel and written one block per month.
- `merra2gmi.py`: `MERRA2GMI` (`merra2_gmi`) and `MERRA2GMIGas` (`merra2_gmi_gas`).
- `geosfp.py`: `GEOSFPAer` (`geosfp_aer`).
- I only added lines to `registry.py`.

**Access paths that work**
- **MERRA-2 and CNN:** Earthdata HTTPS (`data.gesdisc.earthdata.nasa.gov`) with the bearer token, redirected to a signed CloudFront URL. Directory listings there return 404, so file URLs come from CMR, one query per month (M2T1NXAER/5.12.4 and C3094710982-GES_DISC). The acdisc listing does work but took 90 s.
- **GMI and GEOS-FP:** NCCS portal over HTTPS, no credentials.
- **GEOS-FP:** the portal only has 3-hourly `tavg3_2d_aer_Nx`. The hourly `tavg1` collection is OPeNDAP-only, uncompressed, and no cheaper.

**Variables and conversions** (kg m⁻³ ×1e9 to µg m⁻³; mol/mol ×1e9 to ppb)

| Product | Variables |
|---|---|
| `merra2` | `pm25`, `pm10` (formula below); components `pm25_du`, `pm10_du`, `pm25_ss`, `pm10_ss`, `pm25_bc`, `pm25_oc` (raw OC), `pm25_so4` |
| `merra2_cnn` | `pm25`, and `qflag` (static 2-D, repeated over time) |
| `merra2_gmi` | `pm25` (GMI "total reconstructed PM2.5", includes nitrate and ammonium), `pm25_no3`, `pm25_nh4` |
| `merra2_gmi_gas` | `o3`, `no2`: lowest model level (index 71) of the daily-mean 3-D `tavg24_3d_dac_Nv`. GMI publishes no hourly surface gases, so only daily means |
| `geosfp_aer` | same as `merra2`, plus `pm25_no3`, stored separately and not added to `pm25` |

- `pm25` = DU25 + SS25 + BC + 1.4·OC + SO4·132.14/96.06; `pm10` uses full-size dust and sea salt.

**Time stamps**
- **MERRA-2, CNN and GMI hourly:** files are stamped HH:30, so values are stamped at HH+1:00.
- **GMI daily:** the date label is 00 UTC with `day_end_offset_h` = 24.
- **GEOS-FP:** each file HH:30 covers HH−1:30 to HH+1:30, so values are stamped at 03, 06, …; frequency is `3h`.

**Pilot results and cost** (18 pilot sites; magnitudes plausible in every case: Delhi and Kanpur 45–68 µg m⁻³, Beijing 33–51, US sites 5–20 in early July 2023)

| Product | Available end | Measured | Full pass, all sites |
|---|---|---|---|
| `merra2_cnn` | 2026-07-02 | ~70 s per month while running | ~2 h |
| `merra2` | 2026-10-02 | 8 s/day with 6 day-workers; now 2 workers | ~9–11 h (~67 MB read per day) |
| `merra2_gmi` | 2025-12-01 | 5 s/day | ~4 h |
| `geosfp_aer` | about 2026-11-16 24:00 | 13 s/day | ~1.7 h |
| `merra2_gmi_gas` | 2025-11-30 | 52 s/day (chunk index of a 1.5 GB file) | ~40 h, not launched |

**Full extractions launched**
- After the OOM warning I killed my two parallel jobs. Everything now runs through one sequential queue: `data/logs/merra_queue.sh`. Its order is in `merra_queue.txt`, finished products go to `merra_queue.done`, and the run log is `merra_queue.log`.
- Order: `merra2_cnn` (running, about 970 MB RSS, commits look right), then `merra2`, `geosfp_aer`, `merra2_gmi`. Each logs to `data/logs/&lt;name&gt;.log`.
- Readers now return float32 and use 2 day-workers to stay under about 1.5 GB.
- The queue marks a product done even if it is OOM-killed. Check the `rc=` value in `merra_queue.log` and rerun if needed; the runner resumes.

**Issues and requested framework changes**
- **`extract.run` triggers a full pass per start-time group.** After the restart, 2 sites new in the site table started from 2018 while the other 1,669 resumed from 2018-03. For whole-field products every group re-reads every global file, so those 2 sites cost a full extra pass (~1 h for CNN; it would be ~10 h for `merra2`).
  - Fix: for `FieldProduct` subclasses, collapse all groups into one starting at the earliest t0. Re-fetching is idempotent.
  - Also finalize the site list before the long products run; every later site addition costs another full pass.
- **`merra2_gmi_gas`:** decide whether to run it for the common window only (~31 h), a sampled subset of days, or drop it.
- **Cleanup:** `data/store-test-merra` is deleted. My products write no raw cache; the 2.4 GB in `data/cache` belongs to other agents.
- **Credentials:** none failed. Earthdata login worked first time.</result>
<usage><subagent_tokens>341645</subagent_tokens><tool_uses>37</tool_uses><duration_ms>2025605</duration_ms></usage>
</task-notification>

## Claude

Making whole-field products fetch all pending sites in one pass from the earliest start. Re-writing data a site already has is harmless. I'll skip `merra2_gmi_gas`: it only offers daily means at about 40 h per pass, and I'll note that in the README.

- **Bash**: Collapse field-product passes in extract runner: `cd /home/user/simon-code-research/air-quality-data-comparison && python3 - <<'EOF' p='src/aqc/extract.py'; s=open(p).read() old=''' n_sites = sum(len(v) for v …`
- **Bash**: Unregister the MERRA-2 GMI gas product: `sed -i 's|^ "merra2_gmi_gas": "merra2gmi:MERRA2GMIGas",| # "merra2_gmi_gas": "merra2gmi:MERRA2GMIGas", # daily-mean lowest-level O3/NO2; ~40 h per pass, not ru…`
- **Bash**: Commit runner change and push: `cd /home/user/simon-code-research && git add air-quality-data-comparison/ && git commit -qm "air-quality-data-comparison: one pass per field product; drop GMI …`

The runner now makes one pass per whole-field product, and `merra2_gmi_gas` is no longer registered. Both changes are committed and pushed.

Three queues are running one job at a time:
- **MERRA-2:** CNN, then MERRA-2, GEOS-FP aerosols, MERRA-2 GMI. About 18 h in total, mostly the ~10 h MERRA-2 pass.
- **US models:** after HRRR-Smoke finishes, NAQFC raw, NAQFC bias-corrected, then HAQES. About 6 h.
- **ACAG and GHAP:** ACAG, then GHAP monthly, then GHAP daily. About 5 h.

GEOS-CF v1/v2 and the AQS observation ingest are also still running. I'm waiting for them.

## User

<task-notification>
<task-id>bjjhxl4by</task-id>
<summary>Monitor event: "AQS + low-cost obs ingest completion/failures"</summary>
<event>04:47:41 [obs] AQS/1h: 801 sites, 2018-01-01 06:00:00 .. 2026-01-01 10:00:00, vars ['pm25']</event>
</task-notification>

## Claude

AQS hourly PM2.5 is in: 801 sites, 2018 through 2025. PM10, O3 and NO2 are next.

## User

<task-notification>
<task-id>bjjhxl4by</task-id>
<summary>Monitor event: "AQS + low-cost obs ingest completion/failures"</summary>
<event>04:49:12 [obs] AQS/1h: 341 sites, 2018-01-01 05:00:00 .. 2026-01-01 10:00:00, vars ['pm10']</event>
</task-notification>

## Claude

AQS hourly PM10 is in: 341 sites. O3 and NO2 are still ingesting.

## User

<task-notification>
<task-id>bjjhxl4by</task-id>
<summary>Monitor event: "AQS + low-cost obs ingest completion/failures"</summary>
<event>04:53:37 [obs] AQS/1h: 952 sites, 2018-01-01 06:00:00 .. 2026-01-01 10:00:00, vars ['o3']</event>
</task-notification>

## Claude

O3 is in: 952 sites. NO2 and daily FRM PM2.5 are next.

## User

<task-notification>
<task-id>bjjhxl4by</task-id>
<summary>Monitor event: "AQS + low-cost obs ingest completion/failures"</summary>
<event>04:55:05 [obs] AQS/1h: 322 sites, 2018-01-01 06:00:00 .. 2026-01-01 10:00:00, vars ['no2']</event>
</task-notification>

## Claude

NO2 is in: 322 sites. Only the daily 24-hour filter PM2.5 is left.

## User

<task-notification>
<task-id>bjjhxl4by</task-id>
<summary>Monitor event: "AQS + low-cost obs ingest completion/failures"</summary>
<event>04:55:20 [obs] AQS/1d: 451 sites, 2018-01-01 00:00:00 .. 2025-12-31 00:00:00, vars ['pm25_frm']</event>
</task-notification>

## Claude

AQS ingest is complete. Checking the metrics against AQS at the pilot sites, then adding AirNow for 2026, which AQS hasn't released yet.

- **Bash**: Run pilot metrics with AQS obs: `cd /home/user/simon-code-research/air-quality-data-comparison && ICECHUNK_LOG=error uv run aqc metrics geoscf_v1 hrrr_smoke acag --sites pilot --tag test 2>&1 …`
- **Bash**: Write AirNow ingest and start it: `cat > src/aqc/obs/airnow.py <<'EOF' """AirNow hourly files (preliminary, unvalidated) for the recent window not yet in AQS. https://s3-us-west-1.amazonaws.com/…`

While AirNow downloads, wiring it into the observations: AQS takes precedence and AirNow fills hours after AQS ends. I'm also adding the smoke-day window.

- **Bash**: Merge AirNow into AQS obs and add smoke window: `python3 - <<'EOF' p='src/aqc/metrics.py'; s=open(p).read() old=''' if net: h = A.obs_series(net, site.site_id, "1h", root) if h is not None and not h.empty:'''…`

The smoke window works: on smoke days GEOS-CF v1 PM2.5 r rises to 0.75 and CSI-35 to 0.79. Checking extraction progress.

- **Bash**: Check extraction progress: `for f in geoscf acag hrrr_smoke merra2_cnn naqfc obs_lowcost obs_airnow; do echo "== $f: $(grep -v UV_NATIVE data/logs/$f.log | grep -v '^\s*$' | tail -1 | cut…`
- **Bash**: Stop old CNN run and check queue: `pkill -f "aqc extract merra2_cnn"; sleep 20; tail -3 data/logs/merra_queue.log; ps -eo etime,args | grep "aqc extract" | grep -v grep | grep python | cut -c1-1…`

The queue has moved on to MERRA-2 with the new runner. Chaining two jobs behind the current GEOS-CF process: a GEOS-CF pass for the 258 sites added since launch, then a single-pass `merra2_cnn`.

- **Bash**: Chain GEOS-CF extra pass and CNN rerun: `cat > data/logs/chain_main.sh <<'EOF' #!/usr/bin/env bash cd /home/user/simon-code-research/air-quality-data-comparison while pgrep -f "aqc extract geoscf_v1 g…`

Writing `scripts/summarize.py`. It makes the small committed result tables: medians by tier, region and network, plus GEOS-CF v1 vs v2 and the sensor-vs-monitor scores.

- **Bash**: Write summary script: `cat > scripts/summarize.py <<'EOF' """Small committed result tables from data/results/metrics_all.parquet. results/summary_by_tier.csv medians over sites: tier…`

While the long jobs run, test-building the website on the pilot sites from the partial data.

- **Bash**: Export pilot site data and build site: `ICECHUNK_LOG=error uv run python - 2>&1 <<'EOF' | grep -v UV_NATIVE | tail -5 import sys; sys.path.insert(0,"src") import pandas as pd from aqc import sites, e…`
- **Bash**: Headless browser smoke test of the site: `cd /home/user/simon-code-research/air-quality-data-comparison && (cd _site && python3 -m http.server 8765 >/dev/null 2>&1 &) ; sleep 1; cat > /tmp/claude-0/-ho…`
- **Read**: `/tmp/claude-0/-home-user-simon-code-research/4ee5e97b-d28f-575d-b1d9-fc903fcb4391/scratchpad/site_panel.png`
- **Read**: `/tmp/claude-0/-home-user-simon-code-research/4ee5e97b-d28f-575d-b1d9-fc903fcb4391/scratchpad/site_summary.png`

The site works: map, panel, hourly zoom and summary all render with no console errors. Committing, then waiting on the extractions.

- **Bash**: Commit and push progress: `pkill -f "http.server 8765"; cd /home/user/simon-code-research && git add air-quality-data-comparison/ && git commit -qm "air-quality-data-comparison: AirNow r…`
- **Monitor**: `{"description": "extraction completions/failures across product logs", "timeout_ms": 1800000, "command": "cd /home/user/simon-code-research/air-quality-data-co…`

All changes are committed and pushed. I'm now waiting on the extraction queues and the observation ingests; a monitor reports completions or failures from the logs.

## User

<task-notification>
<task-id>bocp14cjg</task-id>
<summary>Monitor event: "extraction completions/failures across product logs"</summary>
<event>05:04:00 [obs] AirNow/1h: 1109 sites, 2025-07-01 01:00:00 .. 2026-11-17 03:00:00, vars ['no2', 'o3', 'pm10', 'pm25']</event>
</task-notification>

## Claude

AirNow ingest finished: 1,109 sites from 2025-07 to 2026-11-17, with PM2.5, PM10, O3 and NO2. That covers the recent window at the US sites.

## User

<task-notification>
<task-id>bocp14cjg</task-id>
<summary>Monitor event: "extraction completions/failures across product logs"</summary>
<event>05:04:03 [acag] done: 1519 site(s), 17.5 MB decoded, 2919 s</event>
</task-notification>

## Claude

ACAG is extracted for 1,519 sites. Its queue continues with GHAP monthly, then GHAP daily. The 152 sites added after ACAG started still need an ACAG pass; I'll run that during the final catch-up update.

## User

<task-notification>
<task-id>bocp14cjg</task-id>
<summary>Monitor event: "extraction completions/failures across product logs"</summary>
<event>05:04:37 [hrrr_smoke] done: 1299 site(s), 1.0 GB decoded, 3027 s</event>
</task-notification>

## Claude

HRRR-Smoke is done for its 1,299 CONUS sites. The US queue now runs NAQFC raw, then NAQFC bias-corrected, then HAQES.

## User

<task-notification>
<task-id>bocp14cjg</task-id>
<summary>Monitor event: "extraction completions/failures across product logs"</summary>
<event>05:06:53 [geoscf_v1] done: 1413 site(s), 5.9 GB decoded, 3423 s</event>
</task-notification>

## Claude

- **TaskUpdate**: `{"taskId": "2", "status": "completed"}`
- **TaskUpdate**: `{"taskId": "3", "status": "in_progress"}`

GEOS-CF v1 is done for 1,413 sites (2018 to 2026-01-02, in about 57 minutes). GEOS-CF v2 is running now. After it, the chained jobs add GEOS-CF for the 258 newer sites, then re-run the CNN product.

## User

<task-notification>
<task-id>bjjhxl4by</task-id>
<summary>Monitor event: "AQS + low-cost obs ingest completion/failures"</summary>
<event>[Monitor expired after 30m with 5 events delivered. Re-arm it if you still need the watch.]</event>
</task-notification>

## Claude

The AQS-only monitor expired after delivering all its events. The broader log monitor still covers the low-cost ingest, so I don't need to re-arm it.

## User

<task-notification>
<task-id>bocp14cjg</task-id>
<summary>Monitor event: "extraction completions/failures across product logs"</summary>
<event>05:15:05 [ghap_m] done: 1671 site(s), 1.5 MB decoded, 599 s</event>
</task-notification>

## Claude

GHAP monthly is done for all 1,671 sites. GHAP daily is next in that queue and should take about 4–5 hours.

## User

<task-notification>
<task-id>bocp14cjg</task-id>
<summary>Monitor event: "extraction completions/failures across product logs"</summary>
<event>05:19:33 [ghap] done: 1671 site(s), 757.2 KB decoded, 258 s</event>
</task-notification>

## Claude

That GHAP "done" covers only one month: the queue runs GHAP daily one month per invocation, so these lines will repeat about 60 times. I'm continuing to wait on the queues.

## User

<task-notification>
<task-id>bocp14cjg</task-id>
<summary>Monitor event: "extraction completions/failures across product logs"</summary>
<event>05:23:41 [ghap] done: 1671 site(s), 731.1 KB decoded, 238 s</event>
</task-notification>

## Claude

Monthly GHAP "done" lines would fill this thread. Replacing the monitor with one that skips them.

- **ToolSearch**: `select:TaskStop`
- **TaskStop**: `{"task_id": "bocp14cjg"}`
- **Monitor**: `{"description": "product extraction completions/failures (excl. per-month GHAP)", "timeout_ms": 1800000, "command": "cd /home/user/simon-code-research/air-qual…`

The filtered monitor is running, and I'll hold the README until the results are in.

## User

<task-notification>
<task-id>bbg8f2gf0</task-id>
<summary>Monitor event: "product extraction completions/failures (excl. per-month GHAP)"</summary>
<event>05:28:03 {"product": "ghap", "available_end": "2022-12-31 00:00:00", "t_end": "2018-03-31 00:00:00", "sites_to_fetch": 1671, "spans": {"2018-03-01 00:00:00": 1671}, "seconds": 253.94307255744934, "decoded_bytes": 828816}</event>
</task-notification>

## Claude

That event came from the summary line, whose `available_end` (2022-12-31) matches my pattern for the last GHAP months, so it would repeat every month. Tightening the filter.

- **TaskStop**: `{"task_id": "bbg8f2gf0"}`
- **Monitor**: `{"description": "product extraction completions/failures (excl. per-month GHAP)", "timeout_ms": 1800000, "command": "cd /home/user/simon-code-research/air-qual…`

The monitor now reports only real completions and failures. Waiting on the queues.

## User

<task-notification>
<task-id>b8qquhxxc</task-id>
<summary>Monitor event: "product extraction completions/failures (excl. per-month GHAP)"</summary>
<event>05:31:49 [geoscf_v2] done: 1413 site(s), 3.0 GB decoded, 1486 s</event>
</task-notification>

## Claude

GEOS-CF v2 is done for 1,413 sites. The chain now extracts GEOS-CF for the 258 newer sites, then re-runs the MERRA-2 CNN product.

## User

<task-notification>
<task-id>b8qquhxxc</task-id>
<summary>Monitor event: "product extraction completions/failures (excl. per-month GHAP)"</summary>
<event>05:32:25 start geoscf extra</event>
</task-notification>

## Claude

The GEOS-CF pass for the 258 additional sites has started.

## User

<task-notification>
<task-id>b8qquhxxc</task-id>
<summary>Monitor event: "product extraction completions/failures (excl. per-month GHAP)"</summary>
<event>[Monitor expired after 30m with 2 events delivered. Re-arm it if you still need the watch.]</event>
</task-notification>

## Claude

- **Bash**: Check progress of all jobs: `cd /home/user/simon-code-research/air-quality-data-comparison && for f in geoscf merra2 naqfc obs_lowcost ghap chain_main us_queue merra_queue; do echo "== $f:…`

Two concerns:
- **MERRA-2 is slow:** about 8 minutes per month, which projects to roughly 14 hours.
- **The low-cost log is still empty** after about 1.5 hours.

Checking the low-cost process.

- **Bash**: Inspect low-cost ingest process: `ps -eo pid,rss,pcpu,etime,args | grep "obs --networks lowcost" | grep -v grep | cut -c1-120; cat /home/user/simon-code-research/air-quality-data-comparison/dat…`
- **Bash**: Fix low-cost listing memory and restart: `python3 - <<'EOF' p='src/aqc/obs/lowcost.py'; s=open(p).read() old=''' with ThreadPoolExecutor(8) as ex: for d, L in zip(days, ex.map(_day_listing, days)): lis…`

The low-cost fetch is running again at 444 MB. Checking whether MERRA-2 is limited by CPU or by the network.

- **Bash**: Check CPU load and MERRA-2 worker settings: `uptime; top -bn1 | head -15 | tail -9; grep -n "workers\|block_workers\|day_workers" /home/user/simon-code-research/air-quality-data-comparison/src/aqc/product…`
- **Monitor**: `{"description": "product extraction completions/failures (excl. per-month GHAP)", "timeout_ms": 1800000, "command": "cd /home/user/simon-code-research/air-qual…`
- **Bash**: Commit low-cost fix and push: `cd /home/user/simon-code-research && git add air-quality-data-comparison/ && git commit -qm "air-quality-data-comparison: keep only selected sensors' file name…`

The low-cost fix is committed and pushed. Extractions continue; the monitor will report completions.

## User

<task-notification>
<task-id>bj202t92n</task-id>
<summary>Monitor event: "product extraction completions/failures (excl. per-month GHAP)"</summary>
<event>06:19:46 [geoscf_v1] done: 258 site(s), 1.1 GB decoded, 2826 s</event>
</task-notification>

## Claude

GEOS-CF v1 now covers all 1,671 sites. The v2 pass for the 258 newer sites runs next, then the CNN re-run.

## User

<task-notification>
<task-id>bj202t92n</task-id>
<summary>Monitor event: "product extraction completions/failures (excl. per-month GHAP)"</summary>
<event>06:29:55 [naqfc] done: 1426 site(s), 2.5 GB decoded, 5097 s</event>
</task-notification>

## Claude

NAQFC raw is done for 1,426 sites. The US queue moves on to NAQFC bias-corrected, then HAQES.

## User

<task-notification>
<task-id>bj202t92n</task-id>
<summary>Monitor event: "product extraction completions/failures (excl. per-month GHAP)"</summary>
<event>[Monitor expired after 30m with 2 events delivered. Re-arm it if you still need the watch.]</event>
</task-notification>

## Claude

- **Monitor**: `{"description": "product extraction completions/failures (excl. per-month GHAP)", "timeout_ms": 1800000, "command": "cd /home/user/simon-code-research/air-qual…`

I re-armed the extraction monitor. Waiting on the MERRA-2, GHAP, NAQFC-bc/HAQES and GEOS-CF v2/CNN jobs, and the low-cost fetch.

## User

<task-notification>
<task-id>bx213gucq</task-id>
<summary>Monitor event: "product extraction completions/failures (excl. per-month GHAP)"</summary>
<event>06:34:35 [obs] SensorCommunity/1h: 60 sites, 2023-01-01 01:00:00 .. 2024-12-31 21:00:00, vars ['pm25_raw', 'pm25', 'pm10', 'rh']</event>
</task-notification>

## Claude

Sensor.Community ingest is done: 60 nodes, 2023–2024, with raw and humidity-corrected PM2.5, PM10 and RH. Every observation network is now in the store.

## User

<task-notification>
<task-id>bx213gucq</task-id>
<summary>Monitor event: "product extraction completions/failures (excl. per-month GHAP)"</summary>
<event>06:39:52 [geoscf_v2] done: 258 site(s), 557.2 MB decoded, 1194 s</event>
</task-notification>

## Claude

GEOS-CF v1 and v2 are now complete for all 1,671 sites. The MERRA-2 CNN re-run starts next in that chain.

## User

<task-notification>
<task-id>bx213gucq</task-id>
<summary>Monitor event: "product extraction completions/failures (excl. per-month GHAP)"</summary>
<event>06:39:52 start merra2_cnn</event>
</task-notification>

## Claude

While CNN runs, starting an interim metrics pass over the finished products (GEOS-CF v1/v2, ACAG, NAQFC, GHAP-monthly) to begin drafting results.

- **Bash**: Start interim metrics run: `cd /home/user/simon-code-research/air-quality-data-comparison && ICECHUNK_LOG=error nohup uv run aqc metrics geoscf_v1 geoscf_v2 acag naqfc ghap_m hrrr_smoke -…`

The interim metrics are running in the background.

## User

<task-notification>
<task-id>bx213gucq</task-id>
<summary>Monitor event: "product extraction completions/failures (excl. per-month GHAP)"</summary>
<event>[Monitor expired after 30m with 3 events delivered. Re-arm it if you still need the watch.]</event>
</task-notification>

## Claude

- **Bash**: Check interim metrics and extraction progress: `cd /home/user/simon-code-research/air-quality-data-comparison && grep -v UV_N data/logs/metrics_interim.log | tail -2; for f in merra2 merra2_cnn naqfc_bc ghap…`

MERRA-2 has sped up to about 5.4 minutes per month, so roughly 8 hours left. The interim metrics are about a third done. Re-arming the monitor, now covering the metrics run too.

- **Monitor**: `{"description": "extraction + metrics completions/failures", "timeout_ms": 1800000, "command": "cd /home/user/simon-code-research/air-quality-data-comparison; …`

The monitor is re-armed to cover the extractions and the interim metrics run, and I'm waiting on them.

## User

<task-notification>
<task-id>bmbeunus0</task-id>
<summary>Monitor event: "extraction + metrics completions/failures"</summary>
<event>07:19:36 metrics: 127208 rows, 0 site errors -&gt; /home/user/simon-code-research/air-quality-data-comparison/data/results/metrics_interim.parquet</event>
</task-notification>

## Claude

- **Bash**: Inspect interim metrics results: `uv run python - 2>&1 <<'EOF' | grep -v UV_N import pandas as pd pd.set_option("display.width", 200) m = pd.read_parquet("data/results/metrics_interim.parquet")…`
- **Bash**: Inspect low-cost sensor metrics: `uv run python - 2>&1 <<'EOF' | grep -v UV_N import pandas as pd pd.set_option("display.width", 200) m = pd.read_parquet("data/results/metrics_interim.parquet")…`
- **Bash**: Use RH-filtered raw sensor PM and mark ACAG per-site: `python3 - <<'EOF' p='src/aqc/metrics.py'; s=open(p).read() old=''' if h is not None and not h.empty: out["hourly"] = h''' new=''' if h is not None and not h.em…`

Running the ACAG catch-up for the 152 sites added after its first pass.

- **Bash**: Run ACAG catch-up and commit: `ICECHUNK_LOG=error nohup uv run aqc extract acag --sites all >> data/logs/acag.log 2>&1 & sleep 5; cd /home/user/simon-code-research && git add air-quality-dat…`

The ACAG catch-up is running, and the low-cost scoring change is committed. I'm waiting on the long MERRA-2 pass and the other queues.

## User

<task-notification>
<task-id>bmbeunus0</task-id>
<summary>Monitor event: "extraction + metrics completions/failures"</summary>
<event>[Monitor expired after 30m with 1 event delivered. Re-arm it if you still need the watch.]</event>
</task-notification>

## Claude

- **Monitor**: `{"description": "extraction completions/failures", "timeout_ms": 1800000, "command": "cd /home/user/simon-code-research/air-quality-data-comparison; tail -n0 -…`

The extraction monitor is re-armed, and I'm waiting on the remaining runs.

## User

<task-notification>
<task-id>bcv6eysqu</task-id>
<summary>Monitor event: "extraction completions/failures"</summary>
<event>07:37:39 [acag] done: 152 site(s), 1.8 MB decoded, 1015 s</event>
</task-notification>

## Claude

ACAG now covers all 1,671 sites, including the remote points and low-cost sensors. Still running: MERRA-2 (then GEOS-FP aerosols and GMI), the MERRA-2 CNN re-run, NAQFC bias-corrected (then HAQES), and GHAP daily.

## User

<task-notification>
<task-id>bcv6eysqu</task-id>
<summary>Monitor event: "extraction completions/failures"</summary>
<event>07:51:39 [naqfc_bc] done: 1426 site(s), 2.5 GB decoded, 4894 s</event>
</task-notification>

## Claude

NAQFC bias-corrected is done for 1,426 sites. HAQES is next in the US queue.

## User

<task-notification>
<task-id>bcv6eysqu</task-id>
<summary>Monitor event: "extraction completions/failures"</summary>
<event>[Monitor expired after 30m with 2 events delivered. Re-arm it if you still need the watch.]</event>
</task-notification>

## Claude

- **Bash**: Check progress of remaining extractions: `cd /home/user/simon-code-research/air-quality-data-comparison && for f in merra2 merra2_cnn haqes ghap; do echo "== $f: $(grep -v UV_NATIVE data/logs/$f.log 2>…`

HAQES failed with "NetCDF: Unknown file format". A download probably returned an HTML page or truncated file instead of netCDF. Looking at the log and reader.

- **Bash**: Inspect HAQES failure log and reader: `grep -v UV_N data/logs/haqes.log | grep -v "^\s*$" | tail -25 | cut -c1-200; grep -n "def read_block\|def _open\|def _get\|netcdf\|xr.open\|scipy\|h5netcdf\|en…`
- **Bash**: Read HAQES fetch code: `sed -n 30,110p src/aqc/products/haqes.py; grep -n "committed" data/logs/haqes.log | tail -2`

Making HAQES check the file signature, retry a bad download three times, and treat a persistently bad file as a missing day instead of aborting. Then restarting it; it resumes from where it stopped.

- **Bash**: Make HAQES robust to bad downloads, restart: `python3 - <<'EOF' p='src/aqc/products/haqes.py'; s=open(p).read() old=''' try: b = _get(url) except FileNotFoundError: return var, None with netCDF4.Dataset("m…`
- **Monitor**: `{"description": "extraction completions/failures", "timeout_ms": 1800000, "command": "cd /home/user/simon-code-research/air-quality-data-comparison; tail -n0 -…`
- **Bash**: Commit HAQES fix: `cd /home/user/simon-code-research && git add air-quality-data-comparison/ && git commit -qm "air-quality-data-comparison: HAQES retries truncated downloads Co-…`

I patched HAQES and restarted it. The fix is committed and pushed. I'm still waiting on HAQES, MERRA-2, the CNN re-run and GHAP daily.

## User

<task-notification>
<task-id>bg8bkxfgs</task-id>
<summary>Monitor event: "extraction completions/failures"</summary>
<event>[haqes] https://data.gesdisc.earthdata.nasa.gov/data/HAQAST/HAQES_NA_PM25_BC.1/2022/HAQES_NA_v1.0_3h_PM25_BC.20220104.nc: not a netCDF file after 3 tries, day skipped
[haqes] https://data.gesdisc.earthdata.nasa.gov/data/HAQAST/HAQES_NA_PM25_OC.1/2022/HAQES_NA_v1.0_3h_PM25_OC.20220104.nc: not a netCDF file after 3 tries, day skipped
[haqes] https://data.gesdisc.earthdata.nasa.gov/data/HAQAST/HAQES_NA_PM25_OC.1/2022/HAQES_NA_v1.0_3h_PM25_OC.20220103.nc: not a netCDF file after 3 tries, day skipped
[haqes] https://data.gesdisc.earthdata.nasa.gov/data/HAQAST/HAQES_NA_PM25_BC.1/2022/HAQES_NA_v1.0_3h_PM25_BC.20220102.nc: not a netCDF file after 3 tries, day skipped</event>
</task-notification>

## Claude

HAQES is now skipping early-2022 files repeatedly, so something systematic is happening. Looking at what the server returns for one of them.

- **Bash**: Inspect HAQES failing file content: `cd /home/user/simon-code-research/air-quality-data-comparison && uv run python - 2>&1 <<'EOF' | grep -v UV_N import sys; sys.path.insert(0,"src") from aqc.prod…`
- **Bash**: Read HAQES error page text: `uv run python - 2>&1 <<'EOF' | grep -v UV_N import sys; sys.path.insert(0,"src") from aqc.products.haqes import _get import re b = _get("https://data.gesdisc.e…`
- **Bash**: Treat GES DISC 404 page as missing and restart HAQES: `pkill -f "aqc extract haqes"; python3 - <<'EOF' p='src/aqc/products/haqes.py'; s=open(p).read() old=''' if b[:3] == b"CDF" or b[:4] == b"\\x89HDF": break''' ne…`
- **Bash**: Commit HAQES 404 fix: `cd /home/user/simon-code-research && git add air-quality-data-comparison/ && git commit -qm "air-quality-data-comparison: HAQES treats GES DISC 404 page as a m…`

HAQES has restarted with the fix, which is committed and pushed. Missing OC/BC days are now skipped silently, and total PM2.5 is unaffected.

## User

<task-notification>
<task-id>bg8bkxfgs</task-id>
<summary>Monitor event: "extraction completions/failures"</summary>
<event>Traceback (most recent call last):
Traceback (most recent call last):
08:14:19 [ghap] FAILED: RetryError(MaxRetryError("HTTPSConnectionPool(host='zenodo.org', port=443): Max retries exceeded with url: /api/records/21873781/files/GHAP_PM2.5_D1K_202008_V2.zip/content (Caused by ResponseError('too many 503 error responses'))"))</event>
</task-notification>

## Claude

GHAP daily hit repeated Zenodo 503 errors on August 2020. Checking whether the queue retries that month or moves on and leaves a gap.

- **Bash**: Inspect GHAP queue script and state: `cat /tmp/claude-0/-home-user-simon-code-research/4ee5e97b-d28f-575d-b1d9-fc903fcb4391/scratchpad/run_queue.sh 2>/dev/null | head -40; ps -eo etime,args | grep …`

No gap: the next monthly run (`--end 2020-09-30`) resumes from each site's last saved time, mid-August 2020, so the failed span is fetched again. Nothing to fix.

## User

<task-notification>
<task-id>bg8bkxfgs</task-id>
<summary>Monitor event: "extraction completions/failures"</summary>
<event>08:17:59 [haqes] done: 1413 site(s), 921.1 MB decoded, 874 s</event>
</task-notification>

## Claude

HAQES is done. All four US-domain products are now extracted. To use the freed CPU, I'll start GEOS-FP aerosols now instead of waiting behind MERRA-2, if the queue script lets me.

- **Bash**: Inspect MERRA queue script and resources: `cat /home/user/simon-code-research/air-quality-data-comparison/data/logs/merra_queue.sh; cat /home/user/simon-code-research/air-quality-data-comparison/data/lo…`

The queue skips anything listed in `merra_queue.done`, so I'll mark GEOS-FP aerosols done there and run it directly in parallel.

- **Bash**: Run GEOS-FP aerosols in parallel: `cd /home/user/simon-code-research/air-quality-data-comparison && echo geosfp_aer >> data/logs/merra_queue.done && ICECHUNK_LOG=error nohup uv run aqc extract g…`

GEOS-FP aerosols now runs alongside MERRA-2. Also still running: the MERRA-2 CNN re-run and GHAP daily. MERRA-2 GMI stays queued after MERRA-2.

## User

<task-notification>
<task-id>bg8bkxfgs</task-id>
<summary>Monitor event: "extraction completions/failures"</summary>
<event>[Monitor expired after 30m with 9 events delivered. Re-arm it if you still need the watch.]</event>
</task-notification>

## Claude

- **Monitor**: `{"description": "extraction completions/failures", "timeout_ms": 1800000, "command": "cd /home/user/simon-code-research/air-quality-data-comparison; tail -n0 -…`

While extractions run, drafting the README's methods, data-source and limitations sections. I'll fill in the numbers once the final metrics exist.

- **Bash**: Collect product titles and sources: `cd /home/user/simon-code-research/air-quality-data-comparison && grep -n "source = \|title = \|start = " src/aqc/products/*.py | grep -v "^.*base.py" | cut -c1…`

The README draft waits on final numbers. Everything left now waits on MERRA-2 (about 6 hours), GHAP daily, the CNN re-run and GEOS-FP aerosols.

## User

<task-notification>
<task-id>b1fqkhjpw</task-id>
<summary>Monitor event: "extraction completions/failures"</summary>
<event>08:40:20 [merra2_cnn] done: 1671 site(s), 3.6 GB decoded, 7219 s</event>
</task-notification>

## Claude

The CNN product is done for all 1,671 sites. Starting MERRA-2 GMI now in parallel rather than after MERRA-2, using the same queue trick.

- **Bash**: Start MERRA-2 GMI in parallel: `echo merra2_gmi >> data/logs/merra_queue.done && ICECHUNK_LOG=error nohup uv run aqc extract merra2_gmi --sites all >> data/logs/merra2_gmi.log 2>&1 & sleep 2;…`

MERRA-2 GMI is running. Still extracting: MERRA-2, GEOS-FP aerosols, MERRA-2 GMI and GHAP daily.

## User

<task-notification>
<task-id>b1fqkhjpw</task-id>
<summary>Monitor event: "extraction completions/failures"</summary>
<event>[Monitor expired after 30m with 2 events delivered. Re-arm it if you still need the watch.]</event>
</task-notification>

## Claude

- **Bash**: Check remaining extraction progress: `for f in merra2 geosfp_aer merra2_gmi ghap; do echo "== $f: $(grep -v UV_NATIVE data/logs/$f.log 2>/dev/null | grep -E 'committed|done:|FAILED' | tail -1 | cut…`
- **Bash**: Stop GMI and requeue after MERRA-2: `pkill -f "aqc extract merra2_gmi"; sed -i '/^merra2_gmi$/d' data/logs/merra_queue.done; cat data/logs/merra_queue.done`
- **Monitor**: `{"description": "extraction completions/failures", "timeout_ms": 1800000, "command": "cd /home/user/simon-code-research/air-quality-data-comparison; tail -n0 -…`

MERRA-2 GMI is back in the queue behind MERRA-2. GEOS-FP aerosols, GHAP daily and MERRA-2 keep running, and the re-armed monitor reports any completion or failure.

## User

<task-notification>
<task-id>b7rf58vnu</task-id>
<summary>Monitor event: "extraction completions/failures"</summary>
<event>[Monitor expired after 30m with no events delivered. Re-arm it if you still need the watch — and widen the filter if silence was unexpected.]</event>
</task-notification>

## Claude

Rather than re-arming 30-minute monitors, a background wait will notify me when GEOS-FP aerosols finishes.

- **Bash**: Wait for GEOS-FP aerosol extraction to finish: `cd /home/user/simon-code-research/air-quality-data-comparison; while pgrep -f "aqc extract geosfp_aer" >/dev/null; do sleep 60; done; grep -v UV_N data/logs/ge…`

I'll get a notification when GEOS-FP aerosols finishes.

## User

<task-notification>
<task-id>b1zr7w37u</task-id>
<tool-use-id>toolu_01MqSmF1DCykiiFrNXhJzLuH</tool-use-id>
<output-file>/tmp/claude-0/-home-user-simon-code-research/4ee5e97b-d28f-575d-b1d9-fc903fcb4391/tasks/b1zr7w37u.output</output-file>
<status>completed</status>
<summary>Background command "Wait for GEOS-FP aerosol extraction to finish" completed (exit code 0)</summary>
</task-notification>

*[Earlier context was compacted]*

## Claude

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; cat /tmp/claude-0/-home-user-simon-code-research/4ee5e97b-d28f-575d-b1d9-fc903fcb4391/tasks/b1zr…`
- **Bash**: `uptime; free -g | head -2; cat /home/user/simon-code-research/air-quality-data-comparison/data/logs/merra_queue.sh`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; pgrep -af merra_queue; pgrep -af run_queue; tail -3 data/logs/merra_queue.log; grep -n "end" src…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; echo merra2_gmi >> data/logs/merra_queue.done; (ICECHUNK_LOG=error nohup uv run aqc extract merr…`
- **Bash**: `cd /home/user/simon-code-research; cat climate-product-compare/publish.toml; wc -l climate-product-compare/README.md; sed -n 1,80p climate-product-compare/READ…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; grep -n "DATA\|import.meta.env\|data/" site/src/main.js | head -20; ls site; cat site/vite.confi…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; cat > publish.toml <<'EOF' # Builds the static site from committed code plus the site-data relea…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; while pgrep -f "aqc extract (merra2|ghap)" >/dev/null; do sleep 120; done; for f in merra2 merra…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; sed -n 80,200p ../climate-product-compare/README.md; cat results/access_check.md 2>/dev/null | h…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; grep -n "^def \|^ def \|^[A-Z_]* = " src/aqc/analysis.py src/aqc/metrics.py | head -60; sed -n 1…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; sed -n 40,100p src/aqc/analysis.py; sed -n 131,200p src/aqc/metrics.py`

Writing a timestamp lag check for the hourly products, as the plan's verification asks. It's cheap and can run while the extractions finish.

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; grep -n "PILOT" -A6 src/aqc/sites.py | head -20; head -3 results/sites/aqs.csv`
- **Write**: `air-quality-data-comparison/scripts/lagcheck.py`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; time ICECHUNK_LOG=error uv run python scripts/lagcheck.py 3 2>&1 | grep -v UV_N | tail -30`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; ICECHUNK_LOG=error uv run python -c " from aqc import analysis as A for p in ['geoscf_v1','hrrr_…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; python3 - <<'EOF' p='scripts/lagcheck.py'; s=open(p).read() s=s.replace('''def anom(s: pd.Series…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; grep -n "_time\|30\|minutes" src/aqc/products/geoscf.py | head; ICECHUNK_LOG=error uv run python…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; git add scripts/lagcheck.py && git commit -qm "air-quality-data-comparison: add hourly timestamp…`

Waiting for MERRA-2, MERRA-2 GMI and GHAP to finish. A notification will arrive when they do.

- **Bash**: `cd /home/user/simon-code-research; git status --short | head`

That's the 3-site test output, which will be regenerated with 40 sites, so I'll remove it rather than commit it.

- **Bash**: `cd /home/user/simon-code-research; rm air-quality-data-comparison/results/lagcheck.csv; git status --short | head -3`

I deleted the stray file, so the working tree is clean and all code is already pushed. The experiment isn't finished yet. The remaining work is the full metrics run, figures, the website, the README and the transcript.

Extraction status:
- **Finished:** GEOS-FP aerosols, for all 1,671 sites.
- **MERRA-2:** has reached 2022-03, with about 5 h left.
- **MERRA-2 GMI:** I started it alongside MERRA-2 to save time, limited to the 2018–2023 comparison window.
- **GHAP:** has reached 2022-07. Only 2018–2022 is published openly.

While these run I added `publish.toml` and a timestamp check for the hourly products (`scripts/lagcheck.py`), and pushed both. It correlates each hourly product with monitor data at offsets of −3 to +3 h; with correct timestamps it should peak at 0. A 3-site test ran cleanly. GEOS-CF's timestamps match the source metadata, but its hourly ozone peaked 1 h late in that test, which may be the model's own daily cycle rather than a timestamp error. I'll rerun it on 40 sites once MERRA-2 is done.

I'll get a notification when the extractions finish and will pick up from there.

## User

<task-notification>
<task-id>bgghvjitt</task-id>
<tool-use-id>toolu_01D2wfavCsxQPhzKz27Lky1h</tool-use-id>
<output-file>/tmp/claude-0/-home-user-simon-code-research/4ee5e97b-d28f-575d-b1d9-fc903fcb4391/tasks/bgghvjitt.output</output-file>
<status>killed</status>
<summary>Background command "cd /home/user/simon-code-research/air-quality-data-comparison; while pgrep -f "aqc extract (merra2|ghap)" &gt;/dev/null; do sleep 120; done; for f in merra2 merra2_gmi ghap; do grep -v UV_N data/logs/$f.log | grep -E "done:|FAILED|Error" | tail -2; done" was stopped after reaching its background time limit</summary>
<note>If the work in progress still needs it, start it again with `run_in_background` and a longer `timeout`. If it already had the longest `timeout` allowed, do not restart it. Either way, report that it was stopped.</note>
</task-notification>

## Claude

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; date; pgrep -af "aqc extract" | grep -v "uv run"; for f in merra2 merra2_gmi ghap; do echo == $f…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; grep -v UV_N data/logs/merra2_gmi.log | tail -25; tail -3 /tmp/claude-0/-home-user-simon-code-re…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; grep -v UV_N data/logs/merra2_gmi.log | grep committed | tail -2; sed -n 40,80p src/aqc/products…`

GHAP finished. MERRA-2 GMI failed at 2019-08 on a zlib error, repeated across 4 immediate retries. I'll add a backoff and skip the day if the file stays undecodable, then resume.

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; python3 - <<'EOF' p='src/aqc/products/merra2gmi.py'; s=open(p).read() old=''' except FileNotFoun…`

Fixing the import placement I just broke.

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; python3 - <<'EOF' p='src/aqc/products/merra2gmi.py'; s=open(p).read() s=s.replace('from __future…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; sed -i 's/^import zlib\n\nimport re/X/' src/aqc/products/merra2gmi.py; python3 - <<'EOF' p='src/…`

MERRA-2 GMI resumed from 2019-08. Meanwhile I'll check `aqc status` to see which products need a catch-up update to the current date.

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; ICECHUNK_LOG=error uv run aqc status 2>&1 | grep -v UV_N`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; ICECHUNK_LOG=error uv run aqc update haqes naqfc naqfc_bc hrrr_smoke geoscf_v2 merra2_cnn --site…`

HRRR-Smoke needs a full pass for the 114 CONUS sites added later. Checking how long the original pass took:

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; grep -v UV_N data/logs/hrrr_smoke*.log | grep -E "done:" | tail -3; ls data/logs | head -40`

About an hour. I'll chain the AirNow observation refresh with the US-model catch-up in the background.

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; cat > data/logs/catchup.sh <<'EOF' #!/bin/bash cd /home/user/simon-code-research/air-quality-dat…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; while pgrep -f "catchup.sh|aqc extract merra2 " >/dev/null; do sleep 120; done; tail -2 data/log…`

While those run, I'm drafting the parts of the README that don't depend on results.

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; for f in results/sites/*.csv; do echo "$f $(($(wc -l <$f)-1))"; done; python3 -c " import pandas…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; sed -n 115,132p src/aqc/export_site.py; ICECHUNK_LOG=error uv run python -c " from aqc.products …`

The catch-up update (AirNow, NAQFC, HAQES, HRRR-Smoke) and the MERRA-2 and MERRA-2 GMI extractions are running. I'll be notified when they finish, then run the full metrics and build the site.

## User

<task-notification>
<task-id>bdsa1t7q8</task-id>
<tool-use-id>toolu_0187AsP8wA1xNXE9o7vdeh7w</tool-use-id>
<output-file>/tmp/claude-0/-home-user-simon-code-research/4ee5e97b-d28f-575d-b1d9-fc903fcb4391/tasks/bdsa1t7q8.output</output-file>
<status>killed</status>
<summary>Background command "cd /home/user/simon-code-research/air-quality-data-comparison; while pgrep -f "catchup.sh|aqc extract merra2 " &gt;/dev/null; do sleep 120; done; tail -2 data/logs/catchup.log; grep -v UV_N data/logs/merra2.log | grep -E "committed|done:|FAILED" | tail -1; grep -v UV_N data/logs/merra2_gmi.log | grep -E "committed|FAILED" | tail -1" was stopped after reaching its background time limit</summary>
<note>If the work in progress still needs it, start it again with `run_in_background` and a longer `timeout`. If it already had the longest `timeout` allowed, do not restart it. Either way, report that it was stopped.</note>
</task-notification>

## Claude

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; date; pgrep -af "aqc (extract|update|obs)" | grep -v "uv run"; tail -3 data/logs/catchup.log | c…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; grep -v UV_N data/logs/metrics_interim.log | head -3; grep -v UV_N data/logs/metrics_interim.log…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; (ICECHUNK_LOG=error nohup uv run aqc metrics --sites all --workers 2 --tag interim2 > data/logs/…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; while pgrep -f "tag interim2" >/dev/null; do sleep 60; done; grep -v UV_N data/logs/metrics_inte…`

The interim metrics pass is running on all 13 extracted products. I'll be notified when it finishes; MERRA-2 and MERRA-2 GMI are still extracting.

## User

<task-notification>
<task-id>bhof4pqjr</task-id>
<tool-use-id>toolu_01P7MQt6fQobTY9hSEDzXFXt</tool-use-id>
<output-file>/tmp/claude-0/-home-user-simon-code-research/4ee5e97b-d28f-575d-b1d9-fc903fcb4391/tasks/bhof4pqjr.output</output-file>
<status>completed</status>
<summary>Background command "cd /home/user/simon-code-research/air-quality-data-comparison; while pgrep -f "tag interim2" &gt;/dev/null; do sleep 60; done; grep -v UV_N data/logs/metrics_interim2.log | tail -2" completed (exit code 0)</summary>
</task-notification>

## Claude

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; date; cat /tmp/claude-0/-home-user-simon-code-research/4ee5e97b-d28f-575d-b1d9-fc903fcb4391/task…`

Interim metrics are done: 232,780 rows with no site errors. Looking at the headline tables:

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; ICECHUNK_LOG=error uv run python - <<'EOF' 2>&1 | grep -v UV_N import pandas as pd pd.set_option…`

MERRA-2 has only 191 Tier-1 sites against 774 for the other products, so something is dropping it. Checking one affected site:

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; ICECHUNK_LOG=error uv run python - <<'EOF' 2>&1 | grep -v UV_N import pandas as pd m=pd.read_par…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; ICECHUNK_LOG=error uv run python - <<'EOF' 2>&1 | grep -v UV_N import pandas as pd pd.set_option…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; sed -n 203,310p src/aqc/metrics.py`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; python3 - <<'EOF' p='src/aqc/metrics.py'; s=open(p).read() old=''' if obs["frm"] is not None and…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; ICECHUNK_LOG=error uv run python - <<'EOF' 2>&1 | grep -v UV_N import pandas as pd from aqc impo…`

HRRR-Smoke correlates at r ≈ 0 with total PM2.5 on Fresno's smoke days, which is suspicious. The plan noted a units change on 2021-12-21, so checking by year:

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; ICECHUNK_LOG=error uv run python - <<'EOF' 2>&1 | grep -v UV_N import pandas as pd, numpy as np …`

After the 2021-12-21 units switch, HRRR-Smoke never exceeds about 13 µg m⁻³ at Fresno, against 158 before it. Checking a known extreme event, the Canadian smoke over New York on 2023-06-07:

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; ICECHUNK_LOG=error uv run python - <<'EOF' 2>&1 | grep -v UV_N import pandas as pd, numpy as np …`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; git add src/aqc/metrics.py && git commit -qm "air-quality-data-comparison: score HRRR-Smoke agai…`

MERRA-2 has about 2.5 h left and GMI about 1.5 h. Meanwhile I'll test summarize and figures on the interim metrics.

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; cp data/results/metrics_interim2.parquet data/results/metrics_all.parquet; ICECHUNK_LOG=error uv…`
- **Read**: `air-quality-data-comparison/results/figures/heatmap_tier1_common.png`
- **Read**: `air-quality-data-comparison/results/figures/species_full.png`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; sed -n 26,75p src/aqc/metrics.py; grep -n "so4\|SO4" src/aqc/products/merra2.py src/aqc/products…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; while pgrep -f "aqc extract merra2" >/dev/null; do sleep 120; done; for f in merra2 merra2_gmi; …`

While that runs, gathering the remaining numbers for the README draft:

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; cat results/sensor_vs_monitor.csv | head -20; ICECHUNK_LOG=error uv run python - <<'EOF' 2>&1 | …`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; ICECHUNK_LOG=error uv run python - <<'EOF' 2>&1 | grep -v UV_N import pandas as pd pd.set_option…`

The interim numbers are enough to draft the README. The plan also asked for medians by AQS location setting, which `summarize.py` doesn't produce yet, so I'm adding that table:

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; python3 - <<'EOF' p='scripts/summarize.py'; s=open(p).read() s=s.replace(''' results/sensor_vs_m…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; git add scripts/summarize.py && git commit -qm "air-quality-data-comparison: summarize Tier 1 by…`

Next, a script that builds the README's key-results tables from the metrics, so the numbers stay reproducible:

- **Write**: `air-quality-data-comparison/scripts/key_tables.py`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; ICECHUNK_LOG=error uv run python scripts/key_tables.py 2>&1 | grep -v UV_N`

The tables work. The MERRA-2, MERRA-2 GMI and HRRR-Smoke rows will fill in after the final run; the other products' numbers shouldn't change. Drafting the README now:

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; du -sh data/store/* 2>/dev/null | sort -h | tail -30; sed -n '/## Reproduc/,/^## [A-Z]/p' ../cli…`
- **Bash**: `cd /home/user/simon-code-research; grep -n "^## \|^### " climate-product-compare/README.md; sed -n '/^## How to reproduce/,/^## Publishing/p' climate-product-c…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; cat mise.toml; grep -rn "os.environ\|getenv" src/aqc | cut -c1-160`

The `obs` task leaves out AirNow, and the metrics task doesn't run the new scripts. Fixing both in mise.toml:

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; grep -n "airnow" src/aqc/cli.py | head -5; python3 - <<'EOF' p='mise.toml'; s=open(p).read() s=s…`

Earlier I ran `aqc obs airnow` positionally, but the command takes `--networks`. Checking whether that refresh actually ran:

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; grep -v UV_N data/logs/obs_airnow.log | tail -4`

That refresh failed, but the AirNow data already runs to 2026-11-17 03:00, past the end of the recent window (2026-10-31), so nothing is lost. Committing the task fixes and the key-tables script:

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; git add mise.toml scripts/key_tables.py && git commit -qm "air-quality-data-comparison: key-resu…`

These are interim outputs that the final run will regenerate in seconds, so I'll remove them rather than commit numbers that are about to change:

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; git checkout results/figures/sites_map.png; git clean -fq results/; git status --short; for f in…`

Neither extraction has committed since about 15:55. Checking whether they're stuck:

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; date; for f in merra2 merra2_gmi; do grep -v UV_N data/logs/$f.log | tail -3 | cut -c1-250; done…`

Not stuck: it's only 15:58, so both committed within the last few minutes. Writing the README draft while they continue.

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; sed -n '/^## Publishing the site data/,$p' ../climate-product-compare/README.md | head -40; cat …`
- **Write**: `air-quality-data-comparison/README.md`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; python3 - <<'EOF' p='README.md'; s=open(p).read() s=s.replace("Hourly PM2.5 (FEM, or a reconstru…`

The README draft is committed with placeholders for the final numbers. I'm waiting on MERRA-2 (at 2025-06) and MERRA-2 GMI (at 2022-06); a background waiter will notify me when both finish.

## User

<task-notification>
<task-id>bdkuwy3oj</task-id>
<tool-use-id>toolu_01UN2x3rmJV8zH8v6GmjLqmh</tool-use-id>
<output-file>/tmp/claude-0/-home-user-simon-code-research/4ee5e97b-d28f-575d-b1d9-fc903fcb4391/tasks/bdkuwy3oj.output</output-file>
<status>killed</status>
<summary>Background command "cd /home/user/simon-code-research/air-quality-data-comparison; while pgrep -f "aqc extract merra2" &gt;/dev/null; do sleep 120; done; for f in merra2 merra2_gmi; do grep -v UV_N data/logs/$f.log | grep -E "done:|FAILED" | tail -1; done" was stopped after reaching its background time limit</summary>
<note>If the work in progress still needs it, start it again with `run_in_background` and a longer `timeout`. If it already had the longest `timeout` allowed, do not restart it. Either way, report that it was stopped.</note>
</task-notification>

## Claude

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; date; pgrep -af "aqc extract" | grep -v "uv run"; for f in merra2 merra2_gmi; do grep -v UV_N da…`

MERRA-2 GMI finished, with 8 corrupt days skipped. MERRA-2 is at 2026-06 with about 5 months left, roughly 40 minutes. Waiting for it:

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; while pgrep -f "aqc extract merra2" >/dev/null; do sleep 60; done; grep -v UV_N data/logs/merra2…`

MERRA-2 is the last extraction still running; I'll run the final metrics when it finishes.

## User

<task-notification>
<task-id>b59sxqrbw</task-id>
<tool-use-id>toolu_012fh1bVVshp5owVfS3dSzJJ</tool-use-id>
<output-file>/tmp/claude-0/-home-user-simon-code-research/4ee5e97b-d28f-575d-b1d9-fc903fcb4391/tasks/b59sxqrbw.output</output-file>
<status>completed</status>
<summary>Background command "cd /home/user/simon-code-research/air-quality-data-comparison; while pgrep -f "aqc extract merra2" &gt;/dev/null; do sleep 60; done; grep -v UV_N data/logs/merra2.log | grep -E "done:|FAILED" | tail -1; tail -2 data/logs/merra_queue.log" completed (exit code 0)</summary>
</task-notification>

## Claude

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; date; cat /tmp/claude-0/-home-user-simon-code-research/4ee5e97b-d28f-575d-b1d9-fc903fcb4391/task…`

All extractions are done. Next: stop the compaction loop, compact every repository once, then run the final metrics.

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; pkill -f compact_loop.sh; sleep 1; pgrep -af compact; cat scripts/compact_loop.sh | head -20`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; du -sh data/store; for r in data/store/products-*.icechunk data/store/obs-*.icechunk; do n=$(bas…`

Nothing more to reclaim; the store is 15 GB. MERRA-2 is the largest at 5.8 GB (9 variables, about 1.3 bytes per value). Starting the final metrics run with 3 workers now that the CPU is free:

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; ICECHUNK_LOG=error uv run aqc metrics --sites all --workers 3 --tag all > data/logs/metrics_all.…`

While that runs, the 40-site lag check:

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; time ICECHUNK_LOG=error uv run python scripts/lagcheck.py 40 2>&1 | grep -v UV_N`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; python3 -c " import pandas as pd; d=pd.read_csv('results/lagcheck.csv'); print(d.pivot_table(ind…`

O3, the variable with the sharpest daily cycle, peaks at lag 0 for GEOS-CF v1, NAQFC and NAQFC bias-corrected. GEOS-CF v2 is tied between −1 and 0. Hourly PM2.5 anomalies correlate weakly (r ≈ 0.1–0.2), with flat peaks within ±1 h. HAQES peaks at +1 h, as expected for 3-hourly instantaneous values compared with hourly means ending at the same time. So no timestamp errors. Waiting for the metrics run.

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; git status --short; git add results/lagcheck.csv && git commit -qm "air-quality-data-comparison:…`

I committed and pushed the lag-check results (`results/lagcheck.csv`), and the working tree is clean.

All extractions are now done, and the final metrics run over all 1,671 sites is underway. It should take about 40 minutes. After that I'll regenerate the summaries, figures and site data, build the site, and fill in the README's placeholders.

## User

<task-notification>
<task-id>bi66f62v3</task-id>
<tool-use-id>toolu_01Q58f1GoeRGFkHUKAHrecPJ</tool-use-id>
<output-file>/tmp/claude-0/-home-user-simon-code-research/4ee5e97b-d28f-575d-b1d9-fc903fcb4391/tasks/bi66f62v3.output</output-file>
<status>completed</status>
<summary>Background command "cd /home/user/simon-code-research/air-quality-data-comparison; ICECHUNK_LOG=error uv run aqc metrics --sites all --workers 3 --tag all &gt; data/logs/metrics_all.log 2&gt;&amp;1; grep -v UV_N data/logs/metrics_all.log | tail -2" completed (exit code 0)</summary>
</task-notification>

## Claude

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; cat /tmp/claude-0/-home-user-simon-code-research/4ee5e97b-d28f-575d-b1d9-fc903fcb4391/tasks/bi66…`

The final metrics have 267,652 rows and no site errors. The MERRA-2, GMI and HRRR-Smoke rows are now filled in. Pulling the remaining facts for the README:

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; ICECHUNK_LOG=error uv run python - <<'EOF' 2>&1 | grep -v UV_N import pandas as pd pd.set_option…`

Now the figures and site data:

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; ICECHUNK_LOG=error uv run aqc figures 2>&1 | grep -v UV_N | tail -2; time (ICECHUNK_LOG=error uv…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; grep -v UV_N data/logs/sitedata.log | tail -3; ls site/public/data/site | wc -l; du -sh site/pub…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; pkill -f "aqc sitedata"; sleep 2; (ICECHUNK_LOG=error nohup uv run aqc sitedata --sites all > da…`

That failure is the copy I stopped; the restarted export is running. Meanwhile I'll check the final figures.

- **Read**: `air-quality-data-comparison/results/figures/heatmap_tier1_common.png`
- **Read**: `air-quality-data-comparison/results/figures/heatmap_tier4_common.png`

Both figures look right. Filling in the README placeholders now:

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; grep -n "PLACEHOLDER\|2026-0x" README.md`

Before writing the key results, checking which sites make up "Europe" in Tier 2, since every product reads low there:

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; python3 -c " import pandas as pd for f in ['embassy','spartan']: d=pd.read_csv(f'results/sites/{…`

Algiers is labelled Europe, a mistake in the box-based regions. Looking at `regions.py`:

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; cat src/aqc/regions.py`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; python3 - <<'EOF' p='src/aqc/regions.py'; s=open(p).read() s=s.replace(''' ("Europe", 35, 72, -2…`

Only Algiers and one remote point (REM:042) change. The committed site CSVs also store a region column, so I'm updating those too, then regenerating the summaries and tests:

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; ICECHUNK_LOG=error uv run python - <<'EOF' 2>&1 | grep -v UV_N import pandas as pd, glob from aq…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; pkill -f "aqc sitedata"; sleep 2; (ICECHUNK_LOG=error nohup uv run aqc sitedata --sites all > da…`

Regional Tier-2 numbers after the fix:

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; ICECHUNK_LOG=error uv run python - <<'EOF' 2>&1 | grep -v UV_N import pandas as pd pd.set_option…`

Writing the key results and remaining README sections now:

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; ICECHUNK_LOG=error uv run python - <<'EOF' 2>&1 | grep -v UV_N # total stored values per product…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; ICECHUNK_LOG=error uv run python - <<'EOF' 2>&1 | grep -v UV_N import zarr, os, subprocess from …`

GHAP shows 13 bytes per value against about 1.2 for everything else. Checking where the space goes:

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; du -sh data/store/products-ghap.icechunk/*; ls data/store/products-ghap.icechunk/snapshots | wc …`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; du -sh data/store/*/overwritten | sort -h | tail -5; ls data/store/products-ghap.icechunk/overwr…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; for r in data/store/products-*.icechunk; do n=$(basename $r .icechunk); echo "$n $(du -sb $r/chu…`

Writing the README sections:

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; cat > /tmp/claude-0/-home-user-simon-code-research/4ee5e97b-d28f-575d-b1d9-fc903fcb4391/scratchp…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; python3 - <<'EOF' p='README.md'; s=open(p).read() rep=[("(MERRA-2 +62 %, GEOS-FP +31 %)","(MERRA…`
- **Bash**: `date; cd /home/user/simon-code-research/air-quality-data-comparison; ls site/public/data/site | wc -l`

The export is on track. Writing the Storage and Publishing sections:

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; cat > /tmp/claude-0/-home-user-simon-code-research/4ee5e97b-d28f-575d-b1d9-fc903fcb4391/scratchp…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; python3 - <<'EOF' sp='/tmp/claude-0/-home-user-simon-code-research/4ee5e97b-d28f-575d-b1d9-fc903…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; git add README.md && git commit -qm "air-quality-data-comparison: README key results, storage, p…`

Those are the final results; committing them:

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; du -sh results; git add results && git commit -qm "air-quality-data-comparison: final metric sum…`

Adding the root README line while the export runs:

- **Bash**: `cd /home/user/simon-code-research; python3 - <<'EOF' p='README.md'; s=open(p).read() line="- [air-quality-data-comparison](air-quality-data-comparison/): 15 gr…`

Count check: 13 product streams were extracted (11 products, since NAQFC and GHAP each have two), not 15. Fixing both READMEs:

- **Bash**: `cd /home/user/simon-code-research; sed -i 's/^- \[air-quality-data-comparison\](air-quality-data-comparison\/): 15 gridded air-quality products/- [air-quality-…`

Waiting for the site-data export to finish:

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; while pgrep -f "aqc sitedata" >/dev/null; do sleep 60; done; grep -v UV_N data/logs/sitedata.log…`

The README and root README line are committed. The site-data export is still running, about 50 minutes in all; then I'll pack and build the site and run the headless check.

## User

<task-notification>
<task-id>bd1tm6xbn</task-id>
<tool-use-id>toolu_017HDsMTjxu3dZ8VHyXM5Zq2</tool-use-id>
<output-file>/tmp/claude-0/-home-user-simon-code-research/4ee5e97b-d28f-575d-b1d9-fc903fcb4391/tasks/bd1tm6xbn.output</output-file>
<status>completed</status>
<summary>Background command "cd /home/user/simon-code-research/air-quality-data-comparison; while pgrep -f "aqc sitedata" &gt;/dev/null; do sleep 60; done; grep -v UV_N data/logs/sitedata.log | tail -2; du -sh site/public/data; find site/public/data -type f | wc -l" completed (exit code 0)</summary>
</task-notification>

## Claude

- **Bash**: `cat /tmp/claude-0/-home-user-simon-code-research/4ee5e97b-d28f-575d-b1d9-fc903fcb4391/tasks/bd1tm6xbn.output; cd /home/user/simon-code-research/air-quality-dat…`

The site data is 433 MB in 6,688 files (the "10031" in the log counts directories too). Building the site and running the headless check:

- **Bash**: `mise run site 2>&1 | tail -4; ls ../air-quality-data-comparison/_site | head; ls /tmp/claude-0/-home-user-simon-code-research/4ee5e97b-d28f-575d-b1d9-fc903fcb4…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; head -30 /tmp/claude-0/-home-user-simon-code-research/4ee5e97b-d28f-575d-b1d9-fc903fcb4391/scrat…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison/_site && (python3 -m http.server 8765 >/dev/null 2>&1 &) ; sleep 1; SP=/tmp/claude-0/-home-user-s…`
- **Read**: `/tmp/claude-0/-home-user-simon-code-research/4ee5e97b-d28f-575d-b1d9-fc903fcb4391/scratchpad/site_panel.png`
- **Read**: `/tmp/claude-0/-home-user-simon-code-research/4ee5e97b-d28f-575d-b1d9-fc903fcb4391/scratchpad/site_summary.png`

No console errors, and the site panel and summary render correctly. Two labels in the site still mention CAMS, which wasn't extracted. Fixing them:

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; grep -n "CAMS" site/src/main.js site/index.html | cut -c1-220`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; sed -i 's/O3 daily = MDA8 (CAMS 3-hourly: daily max of instants)\./O3 daily = MDA8./; s/(UTC, en…`

Checking the About page text for claims that are now out of date:

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; sed -n '/id="about"/,/<\/section>/p' site/index.html | sed 's/<[^>]*>//g' | grep -v '^\s*$' | he…`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; grep -n -i "about" site/index.html site/src/main.js | head; wc -l site/index.html`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; sed -n 45,80p site/index.html | sed 's/<[^>]*>//g' | grep -v '^\s*$'`
- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; sed -n 316,336p site/src/main.js`

The Tier 3 description is stale: the primary value is raw SDS011 PM2.5 with humid hours dropped, and the κ correction is only kept for reference. Fixing that, and setting Tier 4 to the exact 92:

- **Bash**: `cd /home/user/simon-code-research/air-quality-data-comparison; python3 - <<'EOF' p='site/src/main.js'; s=open(p).read() a='2023–2024, hours with RH > 75 % drop…`

Now the repo-level build check:

- **Bash**: `cd /home/user/simon-code-research; pkill -f "http.server 8765"; uv run _helpers/build_site.py --only air-quality-data-comparison --skip-assets 2>&1 | tail -6; …`

The build passes, and this experiment adds 440 MB to the Pages site. Committing the site text fixes:

- **Bash**: `cd /home/user/simon-code-research; git status --short; git add air-quality-data-comparison/site/src/main.js && git commit -qm "air-quality-data-comparison: sit…`

Generating the transcript:

- **Bash**: `cd /home/user/simon-code-research; uv run _helpers/transcript.py -o air-quality-data-comparison/TRANSCRIPT.md 2>&1 | tail -3; wc -c air-quality-data-comparison…`
