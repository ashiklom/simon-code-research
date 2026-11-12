# OpenTofu + aws-emulator: a field guide for agents

How to prototype AWS infrastructure with OpenTofu against
[aws-emulator](https://github.com/aws/aws-emulator) without losing hours to the traps below.
Everything here was verified with **aws-emulator 1.0.336** (commit `f515581569`; first worked out on
1.0.322, see `results/history/`), **OpenTofu 1.13.9**
and **hashicorp/aws 6.73** (see `results/emulator-version.json`). Re-check it against newer emulator
releases with [UPDATE.md](UPDATE.md). Evidence for each claim is in `findings.toml` (ids in brackets)
and the probes under `probes/`.

## TL;DR checklist

1. Install the `.deb` without root (`dpkg-deb -x`) and start it: `scripts/emulator.sh install && scripts/emulator.sh start`.
2. `eval "$(scripts/emulator.sh env)"` in every shell. It also **unsets `AWS_ACCESS_KEY_ID` and friends**,
   which would otherwise beat the emulator's credentials file. You'd get `AccessDenied: Sign the request
   with the emulator credentials`.
3. In the provider set `skip_credentials_validation = true` **and** `skip_requesting_account_id = true`,
   or every `aws_s3_bucket` hangs forever [tofu-s3control-host-prefix].
4. Set `s3_use_path_style = true` [s3-virtual-host-tls].
5. Lambda code must be **pure Python (or JS), stdlib only**. No numpy, GDAL, pydantic-core,
   cryptography, asyncpg, sockets or layers [lambda-rustpython].
6. Don't use `aws_rds_cluster` (provisioned or Serverless v2) or `aws_security_group`. Both fail with
   the current provider; workarounds are below.
7. Address data planes path-style: `https://127.0.0.1:9297/_aws/execute-api/<api-id>/<stage>/…`.
8. Restarting the emulator wipes everything. Delete tofu state at the same time.

## 1. Install and run

```bash
# latest LTS .deb, unpacked into .emulator/ (no root, no Docker)
curl -fsSLO https://downloads.aws.com/aws-emulator/packages/aws-emulator/LTS/latest/aws-emulator_amd64.deb
dpkg-deb -x aws-emulator_amd64.deb .emulator/root
.emulator/root/opt/aws-emulator/bin/aws-emulator -v       # Version / Release date / Commit
# specific version: .../LTS/aws-emulator_<X.Y.Z>-<R>_amd64.deb  (versions.json lists X.Y.Z.R)

EMULATOR_LISTENER_PORT_RANGE=19300-19499 \
  .emulator/root/opt/aws-emulator/bin/aws-emulator -p 9297 -t off --idle-timeout 21600 &
curl --cacert ~/.aws/emulator/9297/ca.pem https://127.0.0.1:9297/__admin/health   # -> ok
```

`scripts/emulator.sh` wraps all of this: `install [--version X | --from-source --ref R]`,
`start`, `stop`, `restart`, `env`, `version-json`.

- Docker is not needed. Lambda code runs inside the emulator process.
- The emulator writes `ca.pem`, `config` and `emulator_credentials` to `~/.aws/emulator/<port>/`.
  **The keys and the certificate are regenerated on every start.**
- `EMULATOR_LISTENER_PORT_RANGE` controls the extra ports opened per resource: RDS cluster
  endpoints, CloudFront distributions and ALBs.
- The emulator plays one account, `000000000000`, and defaults to `us-east-1`.

## 2. Environment

```bash
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN   # env keys beat the credentials file
export AWS_CONFIG_FILE=~/.aws/emulator/9297/config
export AWS_SHARED_CREDENTIALS_FILE=~/.aws/emulator/9297/emulator_credentials
export AWS_CA_BUNDLE=~/.aws/emulator/9297/ca.pem
export AWS_ENDPOINT_URL=https://127.0.0.1:9297     # boto3, AWS CLI, and the tofu AWS provider
export AWS_REGION=us-east-1
```

Gotchas:

- **Python `requests`.** It prefers the `REQUESTS_CA_BUNDLE` env var over `Session.verify`, so set
  `REQUESTS_CA_BUNDLE=$AWS_CA_BUNDLE` (in-process) when calling emulator data planes.
- **Proxies.** If an HTTPS proxy is configured, make sure `127.0.0.1` is in `NO_PROXY`.
- **TLS names.** The certificate covers only `localhost`, `127.0.0.1` and `::1`. Any
  `*.amazonaws.com`-style hostname fails TLS even if you map it in `/etc/hosts`.

## 3. Provider configuration

Copy-paste: a single provider block that targets either the emulator or AWS. This is
`infra/providers.tf` with comments.

```hcl
variable "emulator" { type = bool, default = true }
variable "emulator_endpoint" { type = string, default = "https://127.0.0.1:9297" }
variable "emulator_ca_bundle" { type = string, default = null }        # ~/.aws/emulator/9297/ca.pem
variable "emulator_credentials_file" { type = string, default = null } # .../emulator_credentials

provider "aws" {
  region                      = "us-east-1"
  shared_credentials_files    = var.emulator ? [var.emulator_credentials_file] : null
  profile                     = var.emulator ? "default" : null
  custom_ca_bundle            = var.emulator ? var.emulator_ca_bundle : null
  s3_use_path_style           = var.emulator
  skip_metadata_api_check     = var.emulator
  skip_region_validation      = var.emulator
  skip_credentials_validation = var.emulator   # these two: see S3 Control trap below
  skip_requesting_account_id  = var.emulator
  dynamic "endpoints" {
    for_each = var.emulator ? [1] : []
    content {
      apigateway = var.emulator_endpoint   # ... one line per service you use:
      # apigatewayv2 cloudformation cloudfront cloudwatch cognitoidp ec2 ecr iam kms lambda logs
      # rds s3 secretsmanager sts  (all = var.emulator_endpoint)
    }
  }
}
```

**Env-only alternative.** The probes use this (`probes/_common/provider.tf`). With the environment
from §2 (`AWS_ENDPOINT_URL`, `AWS_CA_BUNDLE`, `AWS_SHARED_CREDENTIALS_FILE`), the provider needs only:

```hcl
provider "aws" {
  region                      = "us-east-1"
  s3_use_path_style           = true
  skip_metadata_api_check     = true
  skip_credentials_validation = true
  skip_requesting_account_id  = true
}
```

That worked for every service exercised here (Lambda, API Gateway v1/v2, CloudFront, WAFv2,
Cognito, S3, SQS, SNS, EventBridge, Step Functions, DynamoDB, KMS, Secrets Manager, Route 53, ACM,
ELBv2, ECS, EC2, ECR, RDS, CloudFormation, SSM).

### The S3 Control trap (why the two `skip_*` flags)

hashicorp/aws 6.x reads `aws_s3_bucket` tags through S3 Control `ListTagsForResource`. The SDK
prefixes the account id onto the endpoint host, giving `000000000000.127.0.0.1:9297`. That never
resolves, and the provider retries for ever: `aws_s3_bucket.x: Still creating... [10m0s elapsed]`.
When the provider doesn't know the account id, it falls back to `GetBucketTagging`.

The side effect: provider-computed ARNs that embed the account id come out with an empty account.
`aws_api_gateway_rest_api.execution_arn` is one. Build them yourself:

```hcl
data "aws_caller_identity" "me" {}     # still works: it calls STS directly
locals { execution_arn = "arn:aws:execute-api:${var.region}:${data.aws_caller_identity.me.account_id}:${aws_api_gateway_rest_api.a.id}" }
```

## 4. Addressing the data planes

| Thing | On AWS | On aws-emulator |
|---|---|---|
| REST API (v1) | `https://<id>.execute-api.<r>.amazonaws.com/<stage>/…` | `https://127.0.0.1:9297/_aws/execute-api/<id>/<stage>/…` (not SigV4-checked) |
| HTTP API (v2) | `api_endpoint` | `api_endpoint` is already `https://127.0.0.1:9297/_aws/execute-api/<id>` |
| CloudFront | `https://<d>.cloudfront.net` | `domain_name` = `127.0.0.1:<port>` (HTTP and HTTPS), or `https://127.0.0.1:9297/_aws/cloudfront/<dist-id>/…` |
| CloudFront → API Gateway origin | origin `domain_name = "<id>.execute-api.<r>.amazonaws.com"` | the same value works: the edge resolves it in-process |
| Lambda function URL | `https://<id>.lambda-url.<r>.on.aws/` | `function_url` = `https://127.0.0.1:9297/_aws/lambda-url/<id>/` since 1.0.336 (before: send to the emulator port with `Host: <id>.lambda-url.<r>.on.aws`) |
| ECR image for Lambda | `image_uri = "${repository_url}:tag"` | since 1.0.336 `repository_url` is `127.0.0.1:9297/<repo>`, which Lambda rejects; use `<acct>.dkr.ecr.<r>.amazonaws.com/<repo>:tag` (image functions still don't *run*) |
| ALB | `dns_name` | `dns_name` is a `127.0.0.1:<port>` listener (HTTP); Lambda targets work |
| Cognito JWKS | `https://cognito-idp.<r>.amazonaws.com/<pool>/.well-known/jwks.json` | `https://127.0.0.1:9297/<pool>/.well-known/jwks.json` (anonymous GET) |
| RDS cluster | `<cluster>.cluster-….rds.amazonaws.com:5432` | `127.0.0.1:<port from listener range>`, TLS with the emulator cert, `sslmode=require` |
| S3 | virtual-host | path style only: `https://127.0.0.1:9297/<bucket>/<key>`; presigned URLs work |

## 5. What Lambda code can do (read this before writing any)

> **The biggest difference from AWS.** Python handlers run on **RustPython 0.6 inside the emulator
> process**. They report `sys.implementation.name == "rustpython"` and version 3.14.0-alpha even for
> `python3.12`. Node.js handlers run on QuickJS.

| Works | Doesn't |
|---|---|
| pure-Python stdlib: `json`, `struct`, `zlib`, `array`, `hashlib`, `base64`, `re`, `math`, `datetime`, big ints | any compiled extension (`.so` files in the zip are skipped): numpy, rasterio/GDAL, pydantic-core, cryptography, orjson, … |
| `boto3` **stand-in** for: s3, rds-data, secretsmanager, dynamodb, sqs, events, logs, cloudwatch, apigateway, stepfunctions, sesv2, opensearch, xray, appconfig(data) | `boto3.client("cognito-idp")` and anything not in that list; paginators |
| `urllib.request` to **AWS-shaped hostnames** (delivered in-process, signed as the execution role). Example: an unsigned Cognito `InitiateAuth` to `https://cognito-idp.us-east-1.amazonaws.com/` | sockets, `asyncio`, any non-AWS host, `127.0.0.1`. A GET of the Cognito JWKS URL returns 400 |
| execution-role IAM is **enforced**, including explicit deny | Python layers (not mounted), `PackageType=Image` (Invoke → `InvalidRuntimeException`), java/ruby/provided.al2023 runtimes |
| `print()` → CloudWatch Logs (`logs:FilterLogEvents` shows it) | real `/tmp`, subprocesses |
| up to 512 MiB per run, 30 s wait ceiling, ~6 MB responses, 50 MiB direct zip / 250 MiB unzipped | |

Consequences for design:

- Talk to Aurora through the **RDS Data API**, not a driver.
- Verify JWTs in pure Python. Cognito signs RS256 like AWS since 1.0.336 (ES256 before), so supporting both is cheap insurance.
- Vendor shared code into each zip instead of using layers.
- To test the real titiler/tipg/FastAPI app, run it outside the emulator (TestClient against local
  PostGIS works well) and keep the Lambda handler thin.

## 6. Service cheat sheet

| Service | Works as on AWS | Differs / doesn't work | Workaround |
|---|---|---|---|
| **API Gateway REST** | Lambda proxy, REQUEST/TOKEN authorizers with policy evaluation (wildcard ARNs), `aws_lambda_permission` enforced, gateway responses, MOCK + CORS headers, binary media types | browsers on another site are refused by the front door (403) [front-door-cross-origin]; computed attrs come back `[]`/`{}`/`""` instead of null [apigw-computed-attr-drift] | hash only configured inputs in deployment `triggers` (normalise `authorizer_id` null/""); path-style URLs |
| **API Gateway HTTP (v2)** | routing, Lambda proxy (payload 2.0), `$default` stage | **JWT authorizer doesn't verify signatures** [apigwv2-jwt-no-signature-check]; Lambda permission not checked [apigwv2-no-lambda-permission-check] | never rely on emulator results for v2 JWT security |
| **CloudFront** | origin routing per path behaviour, cache policies and caching (`x-cache: Hit`), origin request policy header/query forwarding, **WAFv2 web ACL rules** | **`Authorization` never forwarded** [cloudfront-authorization-dropped]; **origin response headers dropped** (Content-Type kept since 1.0.336) [cloudfront-drops-origin-headers]; CloudFront Functions, Lambda@Edge, response-headers policies not run [cloudfront-no-functions]; http not redirected [cloudfront-viewer-protocol] | send bearer tokens in a custom header (e.g. `X-Auth-Token`) and accept it in your authorizer |
| **Cognito** | user pools, groups, app clients, users with permanent passwords via `aws_cognito_user.password`, USER_PASSWORD_AUTH, REFRESH_TOKEN_AUTH, `cognito:groups` in access tokens | `iss` = host you called [cognito-iss-host]; pre-token trigger output ignored [cognito-pretoken-ignored]; no custom attrs in ID token, custom attrs read back without `custom:` (drift) [cognito-custom-attr-prefix]; no `/oauth2/*` or hosted UI [cognito-no-oauth-endpoints]; no SRP [cognito-no-srp] | allow both issuers; authorize on groups |
| **RDS / Aurora** | cluster/instance/subnet group APIs, managed master secret, Serverless v2 config, **Data API** CRUD | `aws_rds_cluster` unusable: DescribeGlobalClusters filter rejected [rds-describeglobalclusters-filter]; engine is SQLite: **no PostGIS**, no PL/pgSQL, 5 s / 64 MiB limits [rds-sqlite-no-postgis]; Data API and wire endpoint are **separate databases** [rds-dataapi-separate-store]; secret survives deletion [rds-managed-secret-outlives-cluster] | create the cluster with `terraform_data` + boto3 script, read it with `data "aws_rds_cluster"` (see `infra/modules/database`); store geometry as GeoJSON text + bbox columns |
| **CloudFormation / Cloud Control** | stacks apply and report outputs | **RDS clusters reported CREATE_COMPLETE but never created** [cfn-rds-not-materialized] | don't use it as an escape hatch for RDS |
| **S3** | buckets, policies (incl. `aws:SecureTransport` deny), SSE, versioning, lifecycle, notifications → Lambda, Range GET, presigned URLs | 64 MiB/bucket and 128 MiB total [s3-capacity-limits]; virtual-host addressing fails TLS [s3-virtual-host-tls] | small test data; path style. Use `source_hash`, not `etag`, for big objects (multipart ETag; same on AWS) |
| **EC2 / VPC** | VPCs, subnets, AZ data source, instances (lifecycle only) | `aws_security_group` fails (the provider's revoke of the default egress rule, protocol -1 with ports 0/0, answers NotFound) [ec2-sg-default-egress]; `aws_instance` fails (empty Placement AZ rejected, then `DescribeTags` is a stub) [ec2-runinstances-empty-az, ec2-describetags-stub] | skip SGs and instances on the emulator |
| **ECS** | clusters, task definitions, RunTask lifecycle | containers don't run [no-container-or-vm-execution] | use Lambda for code that must run |
| **SQS, SNS, EventBridge, Step Functions, DynamoDB (+streams), KMS, Secrets Manager, Route 53, ACM, ELBv2, IAM** | event delivery, scheduled rules, executions, encryption, ALB→Lambda; ACM DNS validation via Route 53 issues certificates since 1.0.336; reserved TLDs (`.example`) are refused as on AWS | DynamoDB on-demand tables read back `max_*_request_units = -1` (drift) [dynamodb-ondemand-throughput-drift] | `ignore_changes` |

## 7. Drift traps

`tofu plan` right after `apply` should say "No changes". Things that broke that here:

- API Gateway deployment triggers hashing whole resources (`jsonencode([aws_api_gateway_method.x, ...])`).
  The emulator returns `provider_arns = []`, `response_parameters = {}` and `authorizer_id = ""`
  (AWS: null), so the hash changes after the first refresh. Hash ids and configured values instead,
  as in `infra/modules/authenticated_api`.
- `aws_s3_object` with `etag = filemd5()` for files uploaded multipart (this happens on AWS too).
  Use `source_hash`.
- `aws_dynamodb_table` (PAY_PER_REQUEST): `max_read/write_request_units = -1 -> null` every plan.
- `aws_cognito_user` with custom attributes: read back as `department` not `custom:department`.

## 8. Lifecycle

- **Destroy** works for the whole 108-resource stack. The only leftover is the RDS-managed secret.
- **Restart = new account.** The emulator keeps state only in memory, and keys and certificate change.
  Restart → `rm terraform.tfstate*` → `apply` (`mise run emulator:restart` does both).
  Don't try `tofu refresh` against a restarted emulator.
- A fresh `apply` of the full stack takes about 60 s, mostly Lambda creation (about 5 s each)
  and the Aurora cluster script.

## 9. Debugging

- `TF_LOG=DEBUG tofu apply 2>log` then `grep "retrying request" log` finds hangs.
  `grep "HTTP Request Sent" log | grep -o 'http.url=[^ ]*'` shows what the provider called.
- Lambda `print()` output is in CloudWatch Logs:
  `aws logs filter-log-events --log-group-name /aws/lambda/<fn>`.
- The emulator source has an `issues/things-that-do-not-work/` directory, but it lags the code.
  Several "Invoke answers 501" issues are already fixed, so prefer probing over reading issues.
- Read the emulator source (`services/service-com-amazonaws-<svc>-*/src`) when behaviour surprises
  you: the doc comments are detailed.
