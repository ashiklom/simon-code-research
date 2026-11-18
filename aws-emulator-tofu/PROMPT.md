# Prompts

## Prompt

https://github.com/aws/aws-emulator

New experiment: aws-emulator-tofu. Create a Terraform stack using opentofu that exclusively uses the AWS emulator. Create an API --- API Gateway through cloudfront that talks to a Lambda --- that reads data from an S3 bucket: Use a basic titiler deployment with some small public COGs as the example. Add an RDS Aurora database in there too, with an API in front of it: Use tipg for this with some small public vector data, so tipg provides OGC API Features. Also create a Cognito user pool with a service that mints user-specific JWTs for each user. Each user can have tiler permissions , tipg permissions, or "admin" (all current and future API permissions). Authenticate the tiler and tipg APIs using the JWTs according to the user roles.

Two overarching goals here: (1) Demonstrate a good design for the authenticated API pattern with different users having different roles. (2) Test the ability of aws-emulator to emulate different AWS services and the ability of opentofu to deploy to these services. The report website should have a single high level summary landing page that links to dedicated pages for each of these goals: how the authenticated API works and is deployed, and how well OpenTofu + aws-emulator worked.

Once done the core objectives, keep probing the capabilities of opentofu + aws-emulator to figure out what (if anything) aws-emulator can't do that AWS can (within reason).

## Claude: question

> Research blocker: aws-emulator runs Lambda Python on an embedded RustPython interpreter. It can't load C extensions (numpy, GDAL, pydantic-core), open sockets (asyncpg), or run container-image Lambdas. Its Aurora PostgreSQL is SQLite behind a Postgres wire front with no PostGIS. So real titiler and tipg cannot run inside the emulator. How should I handle the tiler/features backends?

Options:

1. **Stand-ins + real probe (Recommended)**: Write small pure-Python 'titiler-lite' and 'tipg-lite' Lambdas with titiler/tipg-compatible URLs. They read COGs from S3 by range request and features via the RDS Data API, so the whole authenticated stack runs end-to-end in the emulator. Also deploy a real titiler/tipg (container image + Aurora PostGIS) variant as a probe and document exactly where it breaks.
2. **Real titiler/tipg, deploy-only**: Write the stack for real AWS: titiler and tipg as container-image Lambdas plus Aurora with PostGIS. Test only that OpenTofu can apply and destroy it on the emulator. No live API requests succeed, so the auth design is shown in code but not exercised.
3. **Real apps in local Docker**: Run real titiler, tipg and PostGIS as Docker containers outside the emulator. Use the emulator only for Cognito, S3 and the control plane. API Gateway and CloudFront can't route to them, so JWT checks would live in middleware, not in API Gateway.

## Answer

Stand-ins + real probe (Recommended)

## Plan review comments (first round)

On the plan text "constraints that shape the plan:"

> All of these constraints, and any additional constraints/behavior differences of aws-emulator vs. real AWS, should be clearly reported on the website in a dedicated section on differences between aws-emulator vs. real AWS.
>
> For all of the constraints below, clarify which ones are specific to aws-emulator vs. which ones would also be problems in real AWS (e.g., is the HTTP API v2 JWT no signature verification just in aws-emulator, or a general HTTP limitation? What about Cloudfront not forwarding Authorization and dropping origin — all cloudfront, or just the aws-emulator version?).

On the plan text "Lambda. Handlers run in-process on RustPython (Python) or QuickJS (Node). There are no C extensions, no sockets, no container-image Lambdas and no Python layers."

> This is a major limitation. Make sure this is clealy and loudly documented in the final report.

On the plan text "Provider configuration."

> Save these instructions in an agent-friendly markdown file somewhere, so that I can point future AI agents prototyping AWS capabilities using tofu + aws-emulator at this and save them some time.

On the plan text "tiler-lite tiles must be pixel-identical to rio-tiler reading the same COG."

> Too strict --- this can be relaxed since this is just a proof-of-concept. The only thing that has to agree is the API shape/surface for the most common cases: Same request parameters, same response (again, **most common use case**; don't need to support edge cases).

## Plan review comments (second round)

> Somewhere, add an UPDATE.md (or similar) that gives agent-friendly instructions for updating the findings as aws-emulator is developed. First check is to see if aws-emulator itself was updated at all, and if so, how. If the changes do not address any of the functionality/limitations you found, just update the date of the last check and end. If the changes do resolve some of the issues, check anything that might be affected and update your findings accordingly.
>
> This also means that you should record and report the .deb version, associated commit hash on the aws-emualor GitHub, and the timestamp of the check.
>
> The update step should run against the latest .Deb release by default, but optionally have the ability to build a .Deb of the source if the user requests.

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
