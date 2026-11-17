# Prompts and Q&A

## Prompt

Look at the existing climate data evaluation experiment for inspiration. Create an air-quality-data-comparison experiment that does a similar experiment for PM2.5, PM10, and similar near surface AQ data. Use web search to propose some gridded datasets and station data for comparison. For stations, consider EPA, State department AQ sensors at embassies, CanAiry data from WRI, city/state networks, citizen science, etc. For gridded products, definitely include GEOS-CF (NASA GMAO), MERRA-2, bias corrected MERRA-based PM2.5 (I don't remember the exact product). Ask clarifying questions as appropriate.

## Claude: questions (round 1)

1. **Scope.** Geographic scope for the station comparison? US EPA AQS (~1,000+ PM2.5 reference sites) is the deepest, best-QC'd reference; embassies (~90 cities, to Mar 2025), OpenAQ reference monitors, and SPARTAN give global coverage, mostly in places with few other monitors.
   - *US core + global tier (Recommended).* Tier 1: AQS reference sites (like USCRN in the climate experiment). Tier 2: global — embassy posts, SPARTAN, and a stratified sample of OpenAQ reference monitors (Europe, India, China, LatAm, Africa). Rankings reported separately for each.
   - *Global, equal weight.* Sample reference monitors worldwide (stratified by region/pollution level) without privileging the US; AQS is one of many sources.
   - *US only.* AQS + IMPROVE/CSN + AirNow + low-cost sensors in the US. Simpler, but drops the embassies and the global question.
2. **Pollutants.** Which pollutants? Gridded products and stations all have PM2.5; PM10 is in GEOS-CF v2, MERRA-2 (derived), CAMS, AQS, embassies (some), OpenAQ. Gases (O3, NO2, CO) are in GEOS-CF, CAMS, MERRA-2 GMI, and AQS/OpenAQ but not in the CNN or satellite PM products.
   - *PM2.5, PM10 + PM2.5 species (Recommended).* PM2.5 and PM10 as headline variables; also compare model PM2.5 components (sulfate, OC, BC, dust, nitrate) against IMPROVE/CSN/SPARTAN speciated filters where available. No gases.
   - *PM + O3 and NO2.* Add hourly O3 and NO2 from GEOS-CF, CAMS and MERRA-2 GMI vs AQS/OpenAQ. Roughly doubles extraction and metrics work.
   - *PM2.5 and PM10 only.* Smallest scope: total mass only, no speciation, no gases.
3. **Products** (multi-select). Which gridded products besides the must-haves (GEOS-CF v1+v2, MERRA-2 aerosols-derived PM2.5/PM10, MERRA2_CNN_HAQAST_PM25)?
   - *CAMS EAC4 + CAMS global fcst.* ECMWF reanalysis (0.75°, 3-hourly, 2003–2025) and 0.4° hourly analysis/forecast (2015–). Assimilates satellite AOD only. Via the Atmosphere Data Store (your CDS key probably works).
   - *US models: HRRR-Smoke, NAQFC, HAQES.* HRRR smoke PM (3 km), NOAA AQM/NAQFC (12 km), and the GMU/NASA HAQES ensemble (12 km, 3-hourly). CONUS only; all on AWS without credentials.
   - *Satellite/ML: ACAG V6, GHAP.* WashU ACAG (van Donkelaar) 0.01° monthly PM2.5 + NA composition (s3://satpmdata), and GHAP 1 km daily global PM2.5 (2017–, Zenodo). Both station-trained, so not independent; monthly-scale comparison for ACAG.
   - *GEOS-FP aerosols.* Near-real-time MERRA-2 sibling (tavg1_2d_aer_Nx, 0.25°), for the recent window alongside GEOS-CF v2.
4. **Stations** (multi-select). Which station/sensor sources beyond EPA AQS, AirNow (recent months not yet in AQS), and the embassy historical files?
   - *OpenAQ reference monitors.* Global government monitors (EEA, CPCB India, LatAm, Africa, Australia...). Anonymous S3 archive for data; a free OpenAQ API key is needed to tell reference monitors from low-cost sensors.
   - *Filter networks: IMPROVE, CSN, SPARTAN.* Research-grade 24 h filter mass + speciation (US rural/urban, and ~25 global SPARTAN sites). The closest analog to USCRN. Every-3rd-day sampling.
   - *Free low-cost: AirQo, Sensor.Community, AirGradient.* Citizen-science/low-cost optical sensors (incl. the AirQo data behind WRI CanAIRy). Needs RH filtering and correction; reported as a separate tier.
   - *PurpleAir (paid API key).* Dense US low-cost network with the EPA (Barkjohn) correction. API is billed in points; needs a key from you.

## Answer (round 1)

1. Scope: US core + global tier (Recommended)
2. Pollutants: PM + O3 and NO2
3. Products: CAMS EAC4 + CAMS global fcst, US models: HRRR-Smoke, NAQFC, HAQES, Satellite/ML: ACAG V6, GHAP, GEOS-FP aerosols
4. Stations: OpenAQ reference monitors, Filter networks: IMPROVE, CSN, SPARTAN, Free low-cost: AirQo, Sensor.Community, AirGradient

## Claude: questions (round 2)

1. **Period.** What period should the comparison cover? Records differ: GEOS-CF v1 runs 2018-01 to 2026-01 and v2 2025-08 onward; MERRA-2 runs 1980 onward; the CNN product 2000 onward; CAMS EAC4 2003–2025; GHAP 2017 onward; ACAG ends 2023. Embassies stop 2025-03. GEOS-CF has no time-series copy, so every extra year costs global-file reads.
   - *2018 → now, common 2018–2023 (Recommended).* Extract every product from 2018-01 (the GEOS-CF era) to its end. Rank on a common window, 2018-01..2023-12, which every product but GEOS-CF v2 covers. Add a recent window, 2025-08..2026-10, for GEOS-CF v2, GEOS-FP and CAMS forecasts vs AirNow.
   - *Long record from 2003.* Extract MERRA-2, CNN, CAMS EAC4 and ACAG from 2003, and the others from their start. Gives trend and long-term statistics, but costs far more extraction time and disk.
   - *Short pilot window.* 2023-01..2024-12 only, covering wildfire-smoke 2023 and the embassies. Fast, but rankings rest on weaker statistics.
2. **Remote pts.** Should I also add a tier of station-remote points, comparing products only with each other (like Tier 3 in the climate experiment)? For AQ this mainly shows how much products disagree where nobody measures, e.g. Africa, South America and remote US.
   - *Yes, ~100 global points (Recommended).* About 100 points stratified by region × pollution regime (dust, smoke, urban, clean), far from any monitor. Scored by inter-product spread and departure from the ensemble median, at monthly scale.
   - *Yes, ~50 US points only.* Remote points within CONUS only, where the US-only models (HRRR-Smoke, NAQFC, HAQES) also apply.
   - *No.* Stations only.
3. **Credentials.** The OpenAQ API needs a free key, which classifies locations as reference vs low-cost and gives their metadata; the bulk data come from its anonymous S3. CAMS on the Atmosphere Data Store needs the licences accepted once on the ADS website for your ECMWF account; the CDS key in the environment usually works for ADS too. How should I handle these?
   - *Read from env; I'll add them (Recommended).* Code reads OPENAQ_API_KEY and the existing CDSAPI_KEY. Sources whose credentials are missing or rejected are skipped cleanly and retried later. I'll tell you exactly which licence pages to accept if ADS refuses.
   - *Avoid the OpenAQ key.* Classify OpenAQ locations from the S3 archive's provider and sensor fields alone (heuristic reference vs low-cost list). No key needed. CAMS still uses the CDS key.
4. **Site data.** Publishing the site data. Last time GitHub refused to create releases from this session type, and the data went to the assets repo. What should I plan for here?
   - *Try release; assets repo fallback (Recommended).* Ask you before uploading, try the `air-quality-data-comparison` release first. If it's refused again, push to simon-code-research-assets at the very end (single commit) and pin it, as for the climate experiment.
   - *Assets repo directly.* Skip the release attempt and plan from the start for the assets repo with a pinned commit (still asking before pushing).
   - *Commit small data only.* Keep the site small enough (daily + monthly + metrics, no hourly) to commit to this repo directly; no release, no assets repo.

## Answer (round 2)

1. Period: 2018 → now, common 2018–2023 (Recommended)
2. Remote pts: Yes, ~100 global points (Recommended)
3. Credentials: Read from env; I'll add them (Recommended)
4. Site data: Try release; assets repo fallback (Recommended)

## Follow-up 2

Do the datasets that work with no user intervention (API keys, license/data use agreements) first. Don't wait on my approvals (if needed), so you can get as far as you can without any of my intervention first.

## Follow-up 3

(Sent as feedback when the plan was submitted for approval, and again as a message.)

For GEOS-CF, also try the Zarr stores here: s3://smce-geos-cf-public/geos-cf-v2-fcst-latest.zarr/ (and other data you find in that bucket). If that's not enough or only has a small subset or doesn't work at all, do the original plan
