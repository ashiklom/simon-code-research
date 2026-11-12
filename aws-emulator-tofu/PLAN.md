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
