# Plan: `aws-emulator-tofu`

## Context

The experiment has two goals:
1. Show a good design for an authenticated API: CloudFront → API Gateway → Lambda, with Cognito-issued JWTs and per-user roles (`tiler`, `features`, `admin` = all current and future APIs).
2. Test how well **aws-emulator** emulates these AWS services, and how well **OpenTofu** deploys to it. Afterwards, keep probing for things the emulator can't do that AWS can.

Research on the emulator (source at tag v1.0.322, 2026-11-10) found constraints that shape the plan:
- **Lambda.** Handlers run in-process on RustPython (Python) or QuickJS (Node). There are no C extensions, no sockets, no container-image Lambdas and no Python layers. Calls through boto3 are limited to a stand-in client list (s3, rds-data, secretsmanager, …).
- **Real titiler and tipg cannot run.** **Agreed with the user:** pure-Python stand-ins with titiler/tipg-compatible URLs, plus a "real" titiler/tipg variant deployed as a probe, documenting where it breaks.
- **Aurora PostgreSQL** is SQLite behind a PostgreSQL wire front. It has no PostGIS and a random port. The Data API has its own separate store but works from Lambda.
- **Cognito** issues ES256 JWTs (AWS issues RS256). The JWKS is served at `/<poolId>/.well-known/jwks.json`. `cognito:groups` is present. Pre-token-generation claim overrides are ignored, and there is no `/oauth2/token`.
- **REST API Gateway** enforces Lambda REQUEST/TOKEN authorizers, COGNITO_USER_POOLS authorizers and `aws_lambda_permission`.
- **HTTP API v2** JWT authorizers do **not** verify signatures. That is a fidelity finding to probe.
- **CloudFront** works through a per-distribution `127.0.0.1:<port>` listener or `/_aws/cloudfront/<id>/`. It **never forwards `Authorization`** and **drops origin response headers** (including Content-Type).
- **S3** caps storage at 64 MiB per bucket and 128 MiB in total. Use path-style addressing. Range GETs work.
- **Running the emulator.** It installs from a `.deb` (reachable here). It needs no Docker and keeps state only in memory, with fresh credentials and certificate on each start. It serves HTTPS on 127.0.0.1:9297.

### Emulator-only gaps vs. real-AWS behaviour

This is from current knowledge of AWS and will be verified during implementation. The table becomes the core of the site's "Differences" page.

| Behaviour | Only in aws-emulator? | Real AWS |
|---|---|---|
| **Lambda runs on RustPython/QuickJS: no C extensions, no sockets, no container images, no Python layers** | **Yes (MAJOR)** | Full CPython/Node runtimes, layers and container images up to 10 GB. titiler and tipg run fine. |
| Lambda gets no `AWS_ENDPOINT_URL`, and its boto3 is a stand-in for a fixed service list | Yes | Real boto3, any service, any network. |
| HTTP API v2 JWT authorizer doesn't verify signatures | Yes (a security fidelity gap) | Verifies the signature against the issuer's JWKS (found via OIDC discovery). |
| HTTP API v2 ignores `aws_lambda_permission` | Yes | Invocation fails without the permission. |
| CloudFront never forwards `Authorization` | Yes | Forwarded **if `Authorization` is in the cache policy**, which also puts it in the cache key. An origin request policy alone is not enough. This is a real-AWS gotcha in its own right. |
| CloudFront drops origin response headers (Content-Type, CORS, Cache-Control) | Yes | Passes them through. |
| CloudFront Functions / Lambda@Edge / response-headers policies not executed | Yes | Supported. |
| Aurora PostgreSQL is SQLite with no PostGIS, no PL/pgSQL, 5 s statement limit and 64 MiB per database | Yes | Real PostgreSQL. PostGIS is available. |
| RDS Data API store separate from the wire endpoint; standalone `EnableHttpEndpoint` is a stub | Yes | One database; the Data API is available on Aurora PostgreSQL. |
| Random RDS port; reader endpoint has no listener | Yes | Ports are configurable and reader endpoints work. |
| Cognito signs with ES256 | Yes | RS256. |
| `iss` depends on the host the client called | Yes | Always `https://cognito-idp.<region>.amazonaws.com/<pool>`. |
| Pre-token-generation claim/scope overrides ignored | Yes | Supported. Access-token customization (V2 trigger) needs the Essentials or Plus tier. |
| No `/oauth2/token`, hosted UI or SRP | Yes | Supported once a domain is configured. |
| Per-group custom scopes aren't native | **No, real AWS too** | Needs the pre-token trigger. This is why the design authorizes on `cognito:groups`. |
| REST authorizer cache keyed on the token, so the policy must cover all allowed resources | **No, real AWS too** | Same gotcha. |
| S3 capped at 64 MiB per bucket and 128 MiB in total; path-style only over TLS | Yes | Effectively unlimited; virtual-host style preferred. |
| Browser cross-origin requests refused by the front door | Yes | CORS is configurable. |
| State in memory only; new credentials and certificate on each restart, so tofu state goes stale | Yes (operational) | n/a |
| API Gateway 29 s integration timeout; 6 MB Lambda payload | **No, real AWS too** | Same limits. |

## Layout (`aws-emulator-tofu/`)

```
mise.toml            # opentofu, uv, pixi, quarto; tasks below
pixi.toml/.lock      # python, gdal, rio-tiler (reference oracle), boto3, httpx, pytest, matplotlib
scripts/emulator.sh  # download pinned .deb → dpkg-deb -x into .emulator/ (git-ignored); start/stop/env
scripts/fetch_data.py# small public COGs + Natural Earth vectors → data/ (git-ignored)
lambdas/
  authorizer/        # pure-Python JWT verify (ES256 + RS256), role→permission policy
  token/             # "mint" service: POST /auth/token (InitiateAuth USER_PASSWORD_AUTH), GET /auth/me
  tiler_lite/        # titiler-compatible subset over S3 range reads
  features_lite/     # tipg-compatible OGC API Features subset over RDS Data API
  common/            # tiny shared helpers, copied into each zip at package time
infra/               # root tofu module + modules/{identity, authenticated_api, tiler, features, edge}
infra-real/          # probe: real titiler & tipg as container-image Lambdas + Aurora PostGIS
probes/<name>/       # one small tofu root + check.py per capability probe; probes/run.py
tests/               # unit tests (CPython) + e2e role×endpoint matrix against the deployed stack
results/             # committed JSON outputs (e2e matrix, probe matrix, timings, drift)
figures/             # committed small PNGs (tiles fetched through the stack, maps)
report/              # Quarto site: index, auth-api, emulator-fidelity, probes, reproduce
README.md PROMPT.md PLAN.md TRANSCRIPT.md publish.toml
EMULATOR-GUIDE.md    # agent-friendly how-to: OpenTofu + aws-emulator (see below)
UPDATE.md            # agent-friendly procedure to re-check findings against new emulator releases
findings.toml        # machine-readable findings registry
```

### `EMULATOR-GUIDE.md` (agent-friendly reference)

A standalone markdown file that future AI agents can be pointed at. It will be updated as findings come in, and linked from the README and the site. It covers:
- Install and start the emulator (pinned `.deb`, extracted without root via `dpkg-deb -x`), the health check, and the env vars: `AWS_CONFIG_FILE`, `AWS_SHARED_CREDENTIALS_FILE` and `AWS_CA_BUNDLE`.
- A copy-paste provider block: `endpoints {}` for every service, `custom_ca_bundle`, credentials file, `s3_use_path_style`, `skip_*` flags, and the `emulator` on/off switch.
- How to address data planes:
  - API Gateway: `/_aws/execute-api/<id>/<stage>/…`
  - CloudFront: the `127.0.0.1:<port>` listener or `/_aws/cloudfront/<id>/…`
  - Cognito JWKS: `/<pool>/.well-known/jwks.json`
  - RDS: `EMULATOR_LISTENER_PORT_RANGE`
- What Lambda code can and can't do (pure Python only, available boto3 services, limits).
- A quick table of works / partially works / doesn't work per service, with workarounds, and the perpetual-diff resources to `ignore_changes`.
- The restart/stale-state routine: restart means `rm terraform.tfstate`, then re-apply.

The site will follow `l2-swath-geolocation`'s Quarto pattern (`report/_quarto.yml`, `mise run site`, `output = "report/_site"`).

### `UPDATE.md` (agent-friendly re-check procedure) and version tracking

**Findings registry and version record**
- `findings.toml` is a machine-readable registry. One entry per finding, with these fields:
  - `id` and `title`;
  - `emulator_only` (true/false);
  - `services`, `evidence` (e2e test ID or probe name), and `status` (`gap`, `partial` or `works`);
  - the related emulator crate paths and `issues/` file names;
  - `last_verified_version`.
- The differences page, the probe matrix and `EMULATOR-GUIDE.md` tables are generated from it or checked against it.
- `results/emulator-version.json` records what was tested: `.deb` version, release date, aws-emulator **git commit hash** (from `aws-emulator -v`), .deb SHA-256, `last_checked` UTC timestamp, and the source (`deb-latest` or `source-build@<ref>`).
- The site shows this on the index and differences pages, and the README mentions it.

**Scripts**
- `scripts/emulator.sh` installs the **latest LTS `.deb` by default**.
- `--version <v>` pins a version.
- `--from-source [--ref <commit>]` is the opt-in path. It clones `aws/aws-emulator`, runs `cargo build --release -p aws-emulator-router`, and packages the binary into a local `.deb` with `dpkg-deb --build`, using the same `/opt/aws-emulator` + `/usr/bin` layout. A source build needs a Rust toolchain and ~100 GB of disk, so `UPDATE.md` warns about this.
- `mise run update-check` (`scripts/update_check.py`):
  1. Fetches the latest `.deb`, reads the version and commit, and compares them to `results/emulator-version.json`.
  2. If they are unchanged, it bumps `last_checked` and exits.
  3. If they changed, it shallow-fetches the two commits from `aws/aws-emulator` and diffs them, restricted to the crates and `issues/` files referenced in `findings.toml`. It also checks for issue files that moved from `things-that-do-not-work/` to `things-that-now-work/`.
  4. It prints the findings that may be affected.

**`UPDATE.md` steps for an agent**
1. Run `mise run update-check`. If nothing changed, commit the `last_checked` bump and stop.
2. If the version changed but no finding is affected, update the version, commit hash and `last_checked`, note "no relevant changes", commit, and stop.
3. If findings are affected:
   - Start the new emulator.
   - Re-run `mise run deploy`, `mise run test`, and the probes tied to the affected findings, or `mise run probes` if unsure.
   - Update `findings.toml` (status and `last_verified_version`), `results/*`, `EMULATOR-GUIDE.md` and the report prose.
   - Note any new gaps found along the way.
   - Rebuild the site and commit.
4. Optional: if the user asks, build from source (`--from-source --ref <ref>`) and run the same steps, recording `source-build@<ref>`.

## Data

- **COGs.** Fetch 2–3 small subsets from public sources, e.g. a Sentinel-2 L2A TCI subset (RGB uint8) from the `sentinel-cogs` open bucket and a Copernicus DEM GLO-90 tile (float32), read with GDAL `/vsicurl/`. Re-write each as an **EPSG:3857 `TILING_SCHEME=GoogleMapsCompatible` COG** (DEFLATE, 256-px tiles), at a few MB each, staying under 64 MiB in total. Because the internal tiles line up with WebMercatorQuad, the tiler reads one tile per request.
- **Vectors.** Natural Earth 1:110m countries and populated places, as GeoJSON from the `nvkelso/natural-earth-vector` raw URLs. Load them through the RDS Data API (`batch_execute_statement`) into tables that hold the geometry as GeoJSON text, bbox columns and properties.

## Auth design (goal 1)

**Users and roles**
- Cognito user pool with groups `tiler`, `features`, `admin`, and test users created by tofu: `alice`=tiler, `bob`=features, `carol`=admin, `dave`=no group.
- Passwords come from `random_password` and are set as sensitive outputs.
- App client allows `USER_PASSWORD_AUTH`.

**Token service** (Lambda behind an unauthenticated `/auth` API)
- `POST /auth/token` calls Cognito `InitiateAuth` and returns the user-specific ID, access and refresh tokens.
- `GET /auth/me` returns the caller's roles.
- Fallback if in-process Cognito calls fail inside the Lambda: a host-side `mint_token.py` CLI. This will be documented as a finding.

**Shared Lambda REQUEST authorizer**
- Verifies the JWT against the pool's JWKS, fetched in-process with a tofu-provided JWKS env fallback. Handles ES256 and RS256 so the same code works on AWS.
- Checks `iss`, `token_use`, `client_id` and `exp`.
- Maps `cognito:groups` to permissions through a JSON permission map in an env var: `{"tiler": ["tiler/*"], "features": ["features/*"], "admin": ["*"]}`.
- Returns an IAM policy that covers **every resource the role may call**, not just the method ARN, so the authorizer cache stays correct.
- `admin` gets `arn:aws:execute-api:<region>:<acct>:*/*/*`, which covers every current and future API.

**Reusable `authenticated_api` module**
- Each backend is its own REST API (`tiler`, `features`), built by this module. The module wires the shared authorizer, the Lambda proxy integration, the stage and `aws_lambda_permission`.
- Adding a future API is one module call plus one entry in the permission map. Admin needs no change.

**CloudFront (`edge` module)**
- One distribution with path behaviours `/tiler/*`, `/features/*` and `/auth/*` to the three REST API origins (`{id}.execute-api.us-east-1.amazonaws.com`, origin_path = stage).
- An origin request policy forwards `Authorization` (correct for AWS) plus an `X-Auth-Token` fallback. The authorizer accepts either header, so the emulator's dropped-header behaviour can be both demonstrated and worked around.

**Backends**
- **tiler-lite:** `/tiler/cog/info`, `/cog/tilejson.json`, `/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?url=s3://…&rescale=&colormap_name=`.
  - Parses the TIFF IFDs with `struct`, range-GETs the tile with boto3 S3, decodes it with `zlib` and the predictor, and encodes PNG with `zlib`.
  - Overzooms by nearest neighbour.
- **features-lite:** `/features/`, `/conformance`, `/collections`, `/collections/{id}`, `/collections/{id}/items?bbox=&limit=&offset=` and `/items/{fid}`, with GeoJSON and OGC links.

## Deployment (OpenTofu → emulator)

- **Tooling.** OpenTofu and hashicorp/aws 6.x are pinned, with `.terraform.lock.hcl` committed. The `archive` provider builds the Lambda zips and the `random` provider generates passwords.
- **Provider configuration.**
  - An `endpoints {}` block for every service, set to `https://127.0.0.1:9297`.
  - `custom_ca_bundle` pointing at the emulator `ca.pem`, and `shared_credentials_files` pointing at the emulator credentials file.
  - `s3_use_path_style = true` and `skip_metadata_api_check`.
  - An `emulator` variable switches all of this off for real AWS, so the same code targets both.
- **Tasks.**
  - `mise run emulator:start`, `mise run deploy` (`tofu apply`) and `mise run load` (upload COGs to S3, load vectors through the Data API).
  - `mise run test` (unit tests plus the e2e matrix) and `mise run probes`.
  - `mise run all` for everything, then `mise run site`.

## Testing and measurement (goal 2)

- **Unit tests (CPython).** These are API-surface conformance tests for the **most common use cases only**; no pixel-exactness or edge cases.
  - tiler-lite must accept the same request parameters as real titiler (`url`, `rescale`, `colormap_name`, `bidx`) for `/cog/info`, `/cog/tilejson.json` and the WebMercatorQuad PNG tile.
  - It must also return the same response shape: matching JSON keys and types, and a 256×256 PNG.
  - The reference is real titiler, run in-process with FastAPI's TestClient in the pixi env.
  - features-lite is checked the same way on `/collections`, `/collections/{id}` and `/items` with `bbox`, `limit` and `offset`: required OGC keys, links and `numberMatched`/`numberReturned`.
  - The features reference is real tipg + PostGIS in Docker if a Docker daemon can be started here. Otherwise it is tipg's documented response shapes.
  - JWT verification is tested with ES256 and RS256 test keys.
- **E2E matrix.**
  - 4 users × endpoints {tiler, features, auth/me, future placeholder API}, via direct API Gateway and via CloudFront (`Authorization` vs `X-Auth-Token`).
  - Expected vs observed status codes are saved to `results/e2e.json`.
  - Also tested: expired, tampered and wrong-pool tokens.
  - Fetched tiles go to `figures/`.
- **Deployment metrics.** Apply success per resource, apply and destroy time, `tofu plan -detailed-exitcode` drift after apply (perpetual diffs), and whether destroy is clean. Saved to `results/deploy.json`.
- **infra-real probe.**
  - titiler/tipg container-image Lambdas (ECR push via API) and Aurora with `CREATE EXTENSION postgis`.
  - Record which steps apply and which data-plane calls fail, and how.

## Probing phase (after the core works)

Each probe is a small tofu root plus `check.py`. The results go into `results/probes.json` with the columns apply / drift / data plane / destroy / notes.

Candidate probes, trimmed as time allows:
- **API Gateway:** HTTP API JWT authorizer with a forged signature; Lambda function URLs; ALB → Lambda.
- **Lambda:** Python layers, VPC Lambda, Node.js and `provided.al2023` runtimes.
- **Event sources:** S3 → Lambda notifications, SQS/SNS → Lambda, EventBridge schedule, Step Functions execution, DynamoDB CRUD and streams.
- **Keys and secrets:** KMS encrypt/decrypt; Secrets Manager rotation.
- **IAM:** a deny policy on the Lambda role actually blocks S3.
- **CloudFront:** Functions, Lambda@Edge and WAF.
- **Domains:** Route53 plus ACM DNS validation; API Gateway custom domain.
- **Cognito:** pre-token-generation claims; SRP and hosted UI.
- **Runtime limits:** S3 size limits; RDS wire endpoint vs Data API consistency.
- **Compute:** ECS Fargate and EC2 (does anything run?).
- **Observability:** CloudWatch Logs from Lambda.

## Report (Quarto, `report/`)

- **`index.qmd`:** one-page summary of both goals with headline numbers, linking to the pages below.
  - A prominent warning callout at the top states that **emulated Lambda is RustPython/QuickJS with no native extensions, sockets, layers or container images, so real titiler/tipg can't run.**
- **`differences.qmd`:** a dedicated "aws-emulator vs real AWS" page.
  - Every constraint and behaviour difference found: the table above, extended with everything discovered in the e2e tests and probes.
  - Each row is marked *emulator-only* or *also true on AWS*, with evidence (test or probe ID) and the workaround.
  - The Lambda limitation is the first, highlighted section.
- **`auth-api.qmd`:** architecture diagram, the role → permission model and why admin is future-proof, the token flow, the authorizer policy and caching, the module pattern for adding APIs, and the AWS-vs-emulator config switch. Sample tiles and features are shown.
- **`emulator.qmd`:** how well OpenTofu + aws-emulator worked. Covers the deploy metrics, drift, the e2e matrix, the infra-real outcome, the gaps found and the workarounds used.
- **`probes.qmd`:** the probe matrix of what the emulator can't do that AWS can.
- **`reproduce.qmd`.**

`publish.toml` will have `build = "mise run site"` and `output = "report/_site"`. All outputs are small and committed, so I expect no release assets. If any turn out to be needed, I'll ask first, with file names and sizes.

## Repo bookkeeping

- `PROMPT.md` records, verbatim:
  - the original prompt;
  - my blocker question with its options, and the user's answer;
  - the user's inline plan-review comments: the differences page, loud Lambda documentation, the agent guide, and relaxed tiler tests;
  - the follow-up asking for UPDATE.md and version recording. `PLAN.md` is this plan. Each goes in its own commit.
- Add a root `README.md` line for the experiment, newest first.
- Finish with `uv run _helpers/transcript.py -o aws-emulator-tofu/TRANSCRIPT.md`.
- **Branch:** I'll work on the session's designated branch `claude/aws-emulator-opentofu-stack-nqjksf` instead of `exp/aws-emulator-tofu`, pushing regularly. Commit subjects are prefixed `aws-emulator-tofu: `.
- When done, per CLAUDE.md: fetch, rebase onto `origin/main`, fast-forward `main`, push `main`, delete the branch.

## Verification

1. `mise run emulator:start`, then `mise run deploy`: apply succeeds against the emulator.
2. `mise run load`, then `mise run test`:
   - Unit tests pass, including the API-surface conformance checks against real titiler (and tipg).
   - The e2e matrix matches expectations: alice can reach tiler only, bob features only, carol everything including the placeholder API, dave nothing, and bad tokens get 401/403.
3. `tofu plan -detailed-exitcode` and `tofu destroy` results are recorded.
4. Every row of the differences table is labelled emulator-only or also-AWS and linked to a test or probe. `EMULATOR-GUIDE.md` is followed from scratch in a fresh shell to bring up a trivial stack.
5. `mise run update-check` against the same `.deb` reports "unchanged" and only bumps `last_checked`. Simulating an older recorded commit makes it list the affected findings.
6. `uv run _helpers/build_site.py --only aws-emulator-tofu --skip-assets` builds. Then check the pages in `_site/aws-emulator-tofu/` with a Playwright screenshot.


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
