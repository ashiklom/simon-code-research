# One provider block for both targets. With var.emulator = true every service endpoint points at
# aws-emulator (https://127.0.0.1:9297), trusting its per-run self-signed certificate and using
# its per-run credentials file; with false it is a normal AWS provider.
# See ../EMULATOR-GUIDE.md for the reasoning behind each setting.
locals {
  emulator_services = [
    "apigateway", "apigatewayv2", "cloudformation", "cloudfront", "cloudwatch", "cognitoidp", "ec2", "ecr", "iam",
    "kms", "lambda", "logs", "rds", "s3", "secretsmanager", "sts",
  ]
}

provider "aws" {
  region = var.region

  # --- aws-emulator only ---------------------------------------------------------------
  shared_credentials_files = var.emulator ? [var.emulator_credentials_file] : null
  profile                  = var.emulator ? "default" : null
  custom_ca_bundle         = var.emulator ? var.emulator_ca_bundle : null
  s3_use_path_style        = var.emulator # virtual-host S3 names fail TLS against 127.0.0.1
  skip_metadata_api_check  = var.emulator
  skip_region_validation   = var.emulator
  # Without these two the provider learns the account id (STS) and then reads S3 bucket tags via
  # S3 Control, whose endpoint gets an "<account>." host prefix -> "000000000000.127.0.0.1:9297",
  # which never resolves: `aws_s3_bucket` create hangs in a retry loop. Account-id-derived ARNs
  # (e.g. API Gateway execution_arn) are then built explicitly from aws_caller_identity.
  skip_credentials_validation = var.emulator
  skip_requesting_account_id  = var.emulator

  dynamic "endpoints" {
    for_each = var.emulator ? [1] : []
    content {
      apigateway     = var.emulator_endpoint
      apigatewayv2   = var.emulator_endpoint
      cloudformation = var.emulator_endpoint
      cloudfront     = var.emulator_endpoint
      cloudwatch     = var.emulator_endpoint
      cognitoidp     = var.emulator_endpoint
      ec2            = var.emulator_endpoint
      ecr            = var.emulator_endpoint
      iam            = var.emulator_endpoint
      kms            = var.emulator_endpoint
      lambda         = var.emulator_endpoint
      logs           = var.emulator_endpoint
      rds            = var.emulator_endpoint
      s3             = var.emulator_endpoint
      secretsmanager = var.emulator_endpoint
      sts            = var.emulator_endpoint
    }
  }

  default_tags {
    tags = { project = "aws-emulator-tofu" }
  }
}
