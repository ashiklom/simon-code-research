# Authenticated geospatial APIs on CloudFront -> API Gateway (REST) -> Lambda.
#
#   /auth/token   (public)  token service: mints user-specific Cognito JWTs
#   /auth/me      (any authenticated user)
#   /tiler/...    titiler-lite (COGs in S3)              role "tiler"   or admin
#   /features/... tipg-lite   (Aurora via RDS Data API)  role "features" or admin
#   /reports/...  a "future" API no role grants yet       admin only
#
# Roles are Cognito groups. One shared Lambda REQUEST authorizer maps groups to permissions
# (`local.role_permissions`); every API is rooted at /<service>/ so a permission is a path prefix
# and "admin" = "*" covers every current and future API without changes.
locals {
  name = var.prefix

  # role (Cognito group) -> permissions (service path prefixes). Add a role or grant here.
  role_permissions = {
    tiler    = ["tiler"]
    features = ["features"]
    admin    = ["*"]
  }
  base_permissions = ["auth/me"] # every authenticated user

  issuers = concat(
    ["https://cognito-idp.${var.region}.amazonaws.com/${module.identity.user_pool_id}"],
    # aws-emulator puts the host the client called into `iss` (e.g. https://127.0.0.1:9297/<pool>).
    var.emulator ? ["${var.emulator_endpoint}/${module.identity.user_pool_id}"] : [],
  )

  authorizer_ttl             = coalesce(var.authorizer_ttl, var.emulator ? 0 : 300)
  authorizer_identity_source = local.authorizer_ttl > 0 ? "method.request.header.Authorization" : ""
}

data "aws_caller_identity" "current" {}

# --- identity ---------------------------------------------------------------------------------
module "identity" {
  source = "./modules/identity"
  name   = local.name
  users  = var.users
  groups = keys(local.role_permissions)
}

# --- data -------------------------------------------------------------------------------------
resource "aws_s3_bucket" "cogs" {
  bucket        = "${local.name}-cogs-${data.aws_caller_identity.current.account_id}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "cogs" {
  bucket                  = aws_s3_bucket.cogs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "cogs" {
  bucket = aws_s3_bucket.cogs.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

data "aws_iam_policy_document" "cogs_tls_only" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    resources = [aws_s3_bucket.cogs.arn, "${aws_s3_bucket.cogs.arn}/*"]
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "cogs" {
  bucket = aws_s3_bucket.cogs.id
  policy = data.aws_iam_policy_document.cogs_tls_only.json
}

resource "aws_s3_object" "cog" {
  for_each = fileset(var.cogs_dir, "*.tif")
  bucket   = aws_s3_bucket.cogs.id
  key      = each.value
  source   = "${var.cogs_dir}/${each.value}"
  # Not `etag`: large files are uploaded multipart, whose ETag is not the MD5 (same on AWS).
  source_hash = filemd5("${var.cogs_dir}/${each.value}")
}

module "network" {
  source = "./modules/network"
  name   = local.name
}

module "database" {
  source     = "./modules/database"
  name       = local.name
  subnet_ids = module.network.private_subnet_ids
  vpc_id     = module.network.vpc_id
  # aws-emulator: new security groups lack AWS's default egress rule, so the provider's
  # "revoke default egress" step fails (InvalidPermission.NotFound). See findings.toml.
  create_security_group = !var.emulator
  via_script            = var.emulator
}

# aws-emulator: a Lambda's own HTTP request to the Cognito JWKS URL is dispatched to Cognito's
# signed API front, not its anonymous JWKS route (400). So in emulator mode the JWKS is fetched
# at deploy time and passed in JWKS_JSON (fallback). On AWS the authorizer fetches JWKS_URL itself,
# which also picks up key rotation without a redeploy.
data "http" "jwks" {
  count           = var.emulator ? 1 : 0
  url             = "${var.emulator_endpoint}/${module.identity.user_pool_id}/.well-known/jwks.json"
  ca_cert_pem     = file(var.emulator_ca_bundle)
  request_headers = { Accept = "application/json" }
}

# --- functions --------------------------------------------------------------------------------
module "fn_authorizer" {
  source  = "./modules/lambda_function"
  name    = "${local.name}-authorizer"
  src_dir = "${path.module}/../lambdas/authorizer"
  environment = {
    JWKS_URL           = "https://cognito-idp.${var.region}.amazonaws.com/${module.identity.user_pool_id}/.well-known/jwks.json"
    ALLOWED_ISSUERS    = jsonencode(local.issuers)
    ALLOWED_CLIENT_IDS = jsonencode([module.identity.client_id])
    ROLE_PERMISSIONS   = jsonencode(local.role_permissions)
    BASE_PERMISSIONS   = jsonencode(local.base_permissions)
    JWKS_JSON          = var.emulator ? data.http.jwks[0].response_body : ""
  }
}

module "fn_token" {
  source      = "./modules/lambda_function"
  name        = "${local.name}-token"
  src_dir     = "${path.module}/../lambdas/token"
  environment = { CLIENT_ID = module.identity.client_id }
}

module "fn_tiler" {
  source      = "./modules/lambda_function"
  name        = "${local.name}-tiler"
  src_dir     = "${path.module}/../lambdas/tiler_lite"
  memory_size = 1024
  environment = { ALLOWED_BUCKETS = aws_s3_bucket.cogs.id }
  policy_statements = [{
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.cogs.arn}/*"]
  }]
}

module "fn_features" {
  source  = "./modules/lambda_function"
  name    = "${local.name}-features"
  src_dir = "${path.module}/../lambdas/features_lite"
  environment = {
    DB_CLUSTER_ARN = module.database.cluster_arn
    DB_SECRET_ARN  = module.database.secret_arn
    DB_NAME        = module.database.database_name
  }
  policy_statements = [
    { actions = ["rds-data:ExecuteStatement", "rds-data:BatchExecuteStatement"], resources = [module.database.cluster_arn] },
    { actions = ["secretsmanager:GetSecretValue"], resources = [module.database.secret_arn] },
  ]
}

module "fn_reports" {
  source  = "./modules/lambda_function"
  name    = "${local.name}-reports"
  src_dir = "${path.module}/../lambdas/hello"
}

# --- APIs (one REST API per service, all sharing the authorizer) --------------------------------
locals {
  apis = {
    auth     = { fn = module.fn_token, public_paths = ["token"] }
    tiler    = { fn = module.fn_tiler, public_paths = [] }
    features = { fn = module.fn_features, public_paths = [] }
    reports  = { fn = module.fn_reports, public_paths = [] }
  }
}

module "api" {
  source   = "./modules/authenticated_api"
  for_each = local.apis

  name                       = "${local.name}-${each.key}"
  service                    = each.key
  public_paths               = each.value.public_paths
  function_name              = each.value.fn.function_name
  function_invoke_arn        = each.value.fn.invoke_arn
  authorizer_function_name   = module.fn_authorizer.function_name
  authorizer_invoke_arn      = module.fn_authorizer.invoke_arn
  authorizer_ttl             = local.authorizer_ttl
  authorizer_identity_source = local.authorizer_identity_source
  region                     = var.region
  account_id                 = data.aws_caller_identity.current.account_id
}

# --- edge ---------------------------------------------------------------------------------------
module "edge" {
  source = "./modules/edge"
  name   = local.name
  region = var.region
  apis   = { for k, m in module.api : k => { id = m.rest_api_id, stage = m.stage_name } }
  # default behaviour -> the auth API
  default_api = "auth"
}
