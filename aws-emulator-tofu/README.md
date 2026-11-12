# aws-emulator-tofu

**Question.** Two parts:

1. What is a good design for authenticated APIs where users have different roles? The setting is
   CloudFront → API Gateway → Lambda, with user-specific Cognito JWTs and roles `tiler`,
   `features` and `admin` (= all current and future APIs).
2. How well can [aws-emulator](https://github.com/aws/aws-emulator) (AWS's local emulator) emulate
   such a stack, and how well can OpenTofu deploy to it? Once that was answered I kept probing
   for things the emulator can't do that AWS can.

**What was done.** The stack is a single OpenTofu configuration:

- Cognito user pool with groups as roles, plus a token-minting service;
- one shared Lambda REQUEST authorizer that maps groups to execute-api permissions; `admin` = `*/*/*/*`;
- four REST APIs behind one CloudFront distribution;
- a COG tiler reading S3 by range requests;
- an OGC API Features service on Aurora PostgreSQL via the RDS Data API.

It was deployed to aws-emulator 1.0.322 and tested end to end, then re-verified on 1.0.336 (released
during the experiment) using the update procedure below. 27 more capability probes exercise
other services.

> [!WARNING]
> **aws-emulator runs Lambda Python on RustPython, an in-process interpreter.** It has no native
> extensions, no sockets, no Python layers and no container images. **Real titiler and tipg can't
> run on it.** The tiler and features backends here are pure-Python stand-ins
> (`lambdas/tiler_lite`, `lambdas/features_lite`) with the same API surface as titiler 2.x and
> tipg 1.x for the common cases, verified against the real packages. Aurora PostgreSQL on the
> emulator is SQLite underneath, so there is no PostGIS.

## Key results

- **Auth design works as specified.** Direct API Gateway gives **60/60** role × endpoint × caller
  cases with the status AWS would return:
  - alice → tiler only; bob → features only; carol (admin) → everything, including a "future" API
    nobody was granted; dave → only `/auth/me`;
  - tampered, ID, `alg:none` and garbage tokens → 401.
- **Through CloudFront** it is 60/60 with the token in `X-Auth-Token`, but only 30/60 with
  `Authorization`, because the emulator's CloudFront drops that header.
- **Deploy cycle.** 108 resources apply in about 63 s from an empty emulator. `plan` right after
  reports no changes, and `destroy` is clean apart from one leftover RDS-managed secret.
- **Getting there needed emulator-only workarounds**, each a single switch in `infra/`:
  - provider `skip_credentials_validation` / `skip_requesting_account_id`, without which
    `aws_s3_bucket` hangs on an S3 Control host prefix;
  - no security groups;
  - `aws_rds_cluster` is unusable (the provider's `DescribeGlobalClusters` filter is rejected), so
    the cluster is created by a script and read back with the data source;
  - JWKS fetched at deploy time;
  - `X-Auth-Token` through CloudFront;
  - deployment-trigger drift from empty-vs-null attributes.
- **Probes.** See `results/probes.json` and the site for the full table. Highlights:
  - **v2 HTTP API JWT authorizers accept forged signatures**;
  - CloudFront Functions and response-headers policies are ignored, though WAF and caching work;
  - Cognito ignores pre-token-generation output and has no `/oauth2/token` (it signed ES256 until 1.0.336);
  - CloudFormation reports RDS clusters it never creates;
  - ECS is a lifecycle model only; `aws_instance` can't be managed (EC2 `DescribeTags` is a stub);
    `repository_url` from ECR (1.0.336) is rejected by Lambda's CreateFunction;
  - EventBridge schedules, Step Functions, SQS/SNS, DynamoDB streams, S3 notifications,
    KMS/Secrets Manager and ALB → Lambda work.
- **Findings.** 54 of them, each marked *emulator-only* or *also true on AWS*, are in
  [`findings.toml`](findings.toml) and on the site's differences page.

Agent-facing docs:

- [`EMULATOR-GUIDE.md`](EMULATOR-GUIDE.md): how to prototype AWS with OpenTofu + aws-emulator
  (provider block, environment, addresses, Lambda constraints, cheat sheet, drift traps).
- [`UPDATE.md`](UPDATE.md): how to re-check the findings when aws-emulator changes.
  `mise run update-check` compares the recorded `.deb` version and commit with the latest release
  and lists the findings that may be affected.

Tested build: see [`results/emulator-version.json`](results/emulator-version.json) (aws-emulator
`.deb` version, git commit, sha256, and timestamp of the last update check).

## Reproduce

```bash
cd aws-emulator-tofu
mise install && pixi install
mise run fetch               # small public COGs + Natural Earth vectors -> data/ (git-ignored)
mise run emulator:install    # latest aws-emulator .deb -> .emulator/ (no root, no Docker)
mise run all                 # unit tests, fresh emulator, deploy cycle, load, e2e matrix, probes (~30 min)
mise run site                # render the report from committed results
```

**Requirements.** Linux x86-64 with glibc ≥ 2.17, and outbound HTTPS to downloads.aws.com,
github.com and the two public data buckets (Element 84 Sentinel-2 COGs, Copernicus DEM).

## Layout

| Path | Contents |
|---|---|
| `infra/` | OpenTofu stack (`modules/`: identity, lambda_function, authenticated_api, edge, network, database) |
| `lambdas/` | authorizer (pure-Python ES256/RS256 JWT), token service, titiler-lite, tipg-lite, future-API stand-in, shared `apigw.py` |
| `tests/` | conformance tests vs real titiler/tipg (local PostGIS), authorizer/token tests, `e2e.py` matrix |
| `probes/` | capability probes: one tofu root + `check.py` each; `run.py` runs them |
| `scripts/` | emulator install/start, data fetch, vector loader, Aurora escape hatch, deploy measurement, update check, report tables |
| `results/`, `figures/` | committed outputs that the site renders |
| `report/` | Quarto site |

Site: https://ashiklom.github.io/simon-code-research/aws-emulator-tofu/
