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

## Claude: questions (publishing)

1. **Site data.** air-quality-data-comparison is finished and pushed to branch ccr-10acad54-bjhr7u. The website needs its data: site/site-data.tar, 439.5 MB, holding 6,688 per-site Parquet/JSON files, 433 MB unpacked. This session's GitHub tools can't create releases or upload to them, the same blocker climate-product-compare hit. How should the site data be published?
   - *You make the release.* You run `gh release create air-quality-data-comparison` and `gh release upload air-quality-data-comparison air-quality-data-comparison/site/site-data.tar` from your machine after re-running `mise run sitedata pack-site` (the data/ store isn't persisted, so you'd need to re-extract), OR I attach the tar somewhere you can fetch it. publish.toml already lists it.
   - *Assets repo (Recommended).* I push the 6,688 small files (433 MB) to ashiklom/simon-code-research-assets under air-quality-data-comparison/, in one commit at the end. The site then reads them from raw.githubusercontent at a pinned commit, as climate-product-compare does, and the release asset is dropped from publish.toml.
   - *Hold for now.* Leave the site data unpublished. The site would build but show no data until a later session publishes it.
2. **Push main.** After the site data is settled, may I rebase the branch onto origin/main, fast-forward main and push main? That publishes the experiment to GitHub Pages.
   - *Yes, push main.* Rebase onto origin/main, fast-forward main, push. The session branch stays as required by this environment.
   - *Not yet.* Leave everything on branch ccr-10acad54-bjhr7u for you to review first.

## Answer (publishing)

1. Site data: Assets repo (Recommended)
2. Push main: Yes, push main

(The updated plan for these steps was then approved in plan mode.)

## Follow-up: S3 and new credentials (2026-11-17, shared across experiments)

This prompt covered several experiments at once (air-quality-data-comparison,
climate-product-compare, aws-emulator-tofu, l2-swath-geolocation); the same record is in each
one's PROMPT.md.

This Claude environment has some new capabilities that should allow me to update/improve some existing experiments:

1. You have additional API keys / credentials for NEON, OPENAQ, and Ameriflux in the enviroment variables. A few data portals (e.g., Copernicus ADS) have been additionally approved in terms of data usage agreements / terms for some relevant datasets.
2. You have the ability to write to S3 buckets associated with my organization by using the `read-write-cost` AWS profile (via authenticated API to Cognito). You can also read from S3 buckets with the `read-cost` profile. Both profiles let you inspect costs using the cost explorer, but since that's a paid API call, use that judiciously.
3. The `ycgs-use1-public` bucket is a publicly accessible bucket through the cloudfront URL in the corresponding environment variable.


A few experiments were previously limited by missing API keys. Resolve those issues.

Also, given that you can now write to and read from S3, use that to replace the existing assets in the assets repo. Also, materialize some larger stores used for the work in that S3 store. Analyze the data volumes involved in storing different products, then split them into cost tiers and ask me which tiers to store and which to not store to keep costs down. In a few places, also consider adding additional datasets that were previously limited by data volume (e.g., PRISM 800m). Suggest a few such enhancements.

I expect this primarily affects the air quality and climate comparisons. But look at the other experiments too and suggest improvements/enhancements if you find any.

## Claude: questions (AskUserQuestion, follow-up round 1)

1. **S3 tiers** (multi-select). Which S3 storage tiers should I materialize? Prices are S3 us-east-1 per month: Standard, or Intelligent-Tiering (IT) for idle data. Reading a whole store back out of AWS costs about $0.09/GB each time.
   - *Tier 0+1 (Recommended).* Site data that replaces the assets repo (1→~5 GB). Rebuilt site-extract Icechunk stores for AQ and climate (~35 GB), raw obs caches in the private bucket, and l2-swath granules. ~50–60 GB, about $1.3/mo.
   - *Tier 2a: PRISM 800m CONUS.* Analysis-ready CONUS store for 2018-09→2025-08 with ppt/tmin/tmax/tmean. About 200 GB: $4.6/mo Standard or $1–2.5/mo IT. A full-record version is in Tier 3.
   - *Tier 2b: CAMS + gridMET/PRISM4k.* CAMS EAC4 global surface store 2018–2025 (~40 GB), plus full-record optimized CONUS gridMET and PRISM 4 km stores (120–185 GB). $3.7–5/mo Standard or $1–3/mo IT.
   - *Tier 3: TB-scale.* PRISM 800m full record 1981→now (1.3–2.5 TB), NLDAS-2 forcing and MERRA-2 used variables (~1–1.3 TB), and GEOS-CF v1 global surface (0.5–1 TB). $45–115/mo Standard or $10–30/mo IT.
2. **Rebuild.** The original Icechunk stores were local and no longer exist. The AQ store was about 15 GB and the climate store 13 GB. How should I rebuild them in S3?
   - *Full re-run into S3 (Recommended).* Re-extract every product for all sites, including the new OpenAQ, NEON and AmeriFlux sites, straight into S3. Field products cost the same regardless of site count, and the data refreshes through Nov 2026. Takes roughly 2–3 days of background compute.
   - *New sites/products only.* Extract only what is new: OpenAQ, NEON and AmeriFlux sites, plus CAMS and PRISM 800m. Existing results stay as committed, but S3 then holds only partial stores and the old sites are not refreshed.
3. **Assets repo.** After site data moves to S3, what should happen to ashiklom/simon-code-research-assets?
   - *Leave + deprecate note (Recommended).* Add a README pointing to S3 and leave the files. The old pinned commits keep working, and nothing is deleted.
   - *Delete files in new commit.* Remove both experiments' folders in a new commit. History, and therefore old pins, still works, but the repo does not shrink.
   - *Rewrite history to drop.* Force-push with the files removed, so the repo shrinks. Old pins break.
4. **Other exps** (multi-select). Which enhancements to the other experiments should I include?
   - *l2-swath: real S3 benchmarks.* Upload the granules and virtual Icechunk stores to S3 and re-run the read benchmarks against real S3 and CloudFront, next to the simulated moto/throttle profiles. Also publish the virtual stores.
   - *aws-emulator: real-AWS checks.* Use the live org Cognito pool to spot-check the 'unverified against AWS' identity → role → S3 findings, for example off-group role refusal and reader PutObject denial. Read-only calls only.
   - *Neither.* Limit this work to air quality, climate, and the shared S3 tooling.

## Answer (follow-up round 1)

1. S3 tiers: "Use intelligent tiering for all of these.", Tier 0+1 (Recommended), Tier 2a: PRISM 800m CONUS, Tier 2b: CAMS + gridMET/PRISM4k
2. Rebuild: Full re-run into S3 (Recommended)
3. Assets repo: Leave + deprecate note (Recommended)
4. Other exps: l2-swath: real S3 benchmarks, aws-emulator: real-AWS checks

## Plan feedback (comments on the first plan draft)

On selected text:
> PRISM 800 m CONUS analysis-ready store, common window 2018-09→2025-08, ppt/tmin/tmax/tmean (all 7 variables: ~350 GB)

This is the full gridded product? Don't store this here, but do store the site extractions from this.

On selected text:
> CAMS EAC4 global surface 2018→2025 (~40 GB)

Estimate how big the complete available product record would be (in optimized — icechunk + compressed) form. Then, ask me whether to store it.

On selected text:
> PRISM 4 km

Do not store this. Do store CAMS and gridMET.

On selected text:
> Fallback if Icechunk can't set it: an in-place aws s3 cp --recursive --storage-class INTELLIGENT_TIERING after each store is final. That costs about $0.005 per 1,000 objects.

Stop and warn me if you have to execute this (or similar commands) for around/more than 100K objects ($0.50).

On selected text:
> The assets repo is marked deprecated.

Leave the assets repo documented as a last resort (there may be edge cases where I want to use it).

On selected text:
> PRISM 800 m

Delay downloading this for the site extractions till late in the plan. I may be able to point you at a better cloud-optimized copy in the interim.

## Claude: questions (AskUserQuestion, follow-up round 2)

1. **CAMS EAC4.** CAMS EAC4's complete record is 2003-01 to 2025-12: 0.75° global, 3-hourly, 67k steps × 116k cells, about 7.8e9 values per variable. Optimized with quantization, pcodec and Icechunk at an assumed 0.7–1.5 B/value, that comes to 4 used vars (pm25, pm10, o3, no2) = 22–47 GB; 12 AQ surface vars (+so2, co, 6 aerosol species) = 66–140 GB; all ~100 surface + lowest-level vars = 0.55–1.2 TB. Under Intelligent-Tiering that is about $0.004/GB/mo once idle, $0.023 in the first month. Which, if any, should I store?
   - *4 used vars, full record.* 22–47 GB. About $0.1–0.2/mo idle, $0.5–1.1/mo while hot. Fetching it means ~550 ADS requests, ~130 GB downloaded, mostly waiting in the ADS queue.
   - *12 AQ surface vars, full.* 66–140 GB. About $0.3–0.6/mo idle, $1.5–3.2/mo while hot. Adds SO2, CO and speciated aerosol for component comparisons against IMPROVE/CSN.
   - *Site extracts only.* Store no gridded CAMS, only the site extractions (well under 1 GB) in the AQ site store.
   - *All ~100 vars, full.* 0.55–1.2 TB. About $2–5/mo idle, $13–28/mo while hot. Not recommended.
2. **CAMS fcst.** The CAMS global forecast (0.4°, hourly 00Z leads 1–24, 2015-01 → now, ~4.2e10 values per variable) is also newly accessible. Should I store a gridded copy of it as well?
   - *Site extracts only (Recommended).* Extract the forecast at the sites only. A full 4-variable gridded copy would be ~120–250 GB, about $0.5–1/mo idle, and ~4,300 daily ADS requests.
   - *Store 4 vars gridded.* ~120–250 GB gridded copy of pm25, pm10, o3 and no2.

## Answer (follow-up round 2)

1. CAMS EAC4: 12 AQ surface vars, full
2. CAMS fcst: Site extracts only (Recommended)

(The revised plan was then approved in plan mode; see PLAN.md.)

## Follow-up: small S3 objects (2026-11-18)

Cost analysis shows that you are currently pushing thousands of small parquet files to S3. That inflates costs (thousands of PUT requests) and prevents many small objects from benefitting from intelligent tiering. Explain why you did that, propose some alternatives (including sending a smaller number of larger-chunked parquet files, or using a different format), and then ask me how to proceed.

## Claude: questions (AskUserQuestion, small S3 objects)

1. **Stores.** The Icechunk site-extract stores cause most of the small objects: about 272k so far. AQ MERRA-2 alone has 117k objects at ~10 % extracted, because chunks are 1 site × 1 year and every write adds new versions. How should I restructure them?
   - *Sharded + repack (Recommended).* Switch arrays to one shard per variable per ~256 sites per year, with per-site inner chunks. Repack the existing stores into single-snapshot repos and delete the old ones (~280k GETs ≈ $0.11; deletes free), then resume extraction. About 100× fewer objects, mostly IT-eligible.
   - *Build locally, upload once.* Keep extracting into local repos (~25 GB disk free) and upload a packed copy (sharded, single snapshot) at the end. Fewest PUTs, but a container restart before upload loses the local work.
   - *Keep layout, compact only.* Garbage-collect superseded versions periodically; per-site small chunks stay. Cheapest code change; object count stays high (~hundreds of thousands).
2. **Site data.** The website data is ~8k Parquet/JSON files today and would grow to ~26k with AQ hourly for all years. Which layout should it use?
   - *One file per site (Recommended).* Merge each site's daily, monthly, all-years hourly and metrics into one Parquet file, plus a few shared JSON files: about 2.5k AQ and 0.3k climate objects. No infra change; each click downloads ~1–3 MB.
   - *Few big files + range reads.* One Parquet per scale with a row group per site and a byte-range index: ~10–20 objects total. Needs you to make CloudFront return CORS on 206 responses (ycgs-aws-infra), since it currently drops it intermittently.
   - *Keep per-site files.* Leave as is (~$0.13 in PUTs per AQ publish; small objects billed at Standard, ~$0.01–0.03/month).
3. **Queue.** The work queue is still extracting PRISM into the old layout, adding small chunks while it runs. Should I pause it while I make these changes?
   - *Pause now (Recommended).* Stop the queue (resumable) and the CAMS loop stays running (its store is already sharded and IT-friendly). Resume after the layout change.
   - *Keep running.* Let PRISM and the climate products finish in the old layout and repack them afterwards.

## Answer (small S3 objects)

1. Stores: Sharded + repack (Recommended)
2. Site data: One file per site (Recommended)
3. Queue: Pause now (Recommended)

## Follow-up: repack reads (2026-11-18)

```
> reading the old stores out of S3 for the repack is about 12–18 GB of egress,
```

Can't you do this through the cloudfront URL I provided?

## Claude: question (AskUserQuestion, bulk reads)

CloudFront has a WAF rate limit ("Request blocked" 403) that a burst of small chunk requests from this container trips. The metrics steps read every site-extract store in full (~15 GB per experiment), which through CloudFront would be tens of thousands of requests. How should bulk store reads work?
- *Throttled CloudFront.* I read whole shards (~1 MB each, one request per shard) at a conservative rate under the WAF limit, caching them locally for the metrics run. Free under the CloudFront free tier; ~1–2 h per experiment and some extra code.
- *Direct S3 reads.* Simplest and fastest. S3 egress to this container is ~$0.09/GB: roughly $1.5 per experiment per full metrics run (~$3 total now), plus any reruns.
- *You relax the WAF rule.* You exempt or raise the rate limit for this traffic in ycgs-aws-infra; then I read through CloudFront at full speed. Until then I hold the read-heavy steps.

## Answer (bulk reads)

Direct S3 reads

(Two later plans, for resuming after container restarts on 2026-11-18 and 2026-11-19, were approved in plan mode without further messages; see PLAN.md.)

## Claude: questions (2026-11-19, in chat)

1. **Upload the l2-swath virtual stores?** These are the small reference stores that let anyone open the benchmark granules without downloading them. I'd upload only the CloudFront one: 920 KB in 138 objects, which costs effectively nothing (well under $0.01 to upload, about $0.00 a month). The S3 one needs AWS credentials to read, so it's less useful to share. OK to upload the CloudFront one to `s3://ycgs-use1-public/simon-code-research/l2-swath-geolocation/stores/`?
2. **PRISM 800 m:** is a cloud-optimized copy available now? If not, the fallback streams the daily 800 m files (roughly 450 GB, about 12 h). It would only sample the sites over the common window and store nothing gridded. It would run after the air-quality extractions, so not for a few days. Should I use the fallback, a copy you point me to, or skip it?

## Answer

```
<!-- reply 2 -->
> l2-swath virtual store: may I upload the CloudFront one (920 KB, 138 objects) to S3?

Yes.

<!-- reply -->
> PRISM 800 m: should I use a cloud-optimized copy you point me to, run the roughly 450 GB streaming fallback, or skip it?

Skip for now.
```
