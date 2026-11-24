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

## Follow-up (2026-11-19)

status?

## Follow-up (2026-11-20)

status?

## Follow-up (2026-11-24)

Status?

## Claude: question (AskUserQuestion, keep alive)

The long jobs (air-quality extractions, CAMS global store) seem to run only while this session has a background task: both outages began within a minute of my 2-hour watcher expiring (Nov 19 23:05, Nov 20 15:41), and the container was then reclaimed until your next message. About 4 days were lost this time. What remains is ~2–3 days of AQ extraction and ~179 CAMS blocks (several days, ADS-bound). How should I keep them going?
- *Re-arm watcher (Recommended).* Each time the 2-hour watcher ends I check the logs, restart anything dead, and arm a new one, until the queue and CAMS store finish. Costs one short turn every 2 h (~12 a day) but keeps the container alive.
- *Only when I check in.* I stop re-arming. Jobs make progress only while you are interacting; I restart them whenever you ask for a status.
- *Trim the remaining work.* Re-arm the watcher, but first cut scope to finish sooner (e.g. stop the CAMS global store at the current record and drop some AQ products). I'd propose specifics.

## Answer (keep alive)

Re-arm watcher (Recommended)

## Follow-up (2026-11-24, later; meant for another session)

aws-sso has been refreshed. tell me what benchmarks (if any) you still might want to run with aws-sso access and ask me whether to proceed. if you are done with all benchmarks, destroy the new stacks but keep the code.

## Claude: question

There's no AWS SSO access in this container (only the three Cognito profiles) and this session never deployed any stacks, so there's nothing to tear down. If you did give this session broader access, these aws-emulator-tofu findings are still unchecked on real AWS: the identity-pool fallback role, an Aurora master username with an underscore, and API Gateway/Lambda/CloudFront behaviour. Did you mean to send this to another session?

## Answer

ignore the aws-sso message. that was another session.
