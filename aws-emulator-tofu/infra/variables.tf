variable "emulator" {
  description = "Target aws-emulator (true) or real AWS (false)."
  type        = bool
  default     = true
}

variable "emulator_endpoint" {
  description = "aws-emulator endpoint (scripts/emulator.sh env sets TF_VAR_emulator_endpoint)."
  type        = string
  default     = "https://127.0.0.1:9297"
}

variable "emulator_ca_bundle" {
  description = "Path to the emulator's per-run ca.pem."
  type        = string
  default     = null
}

variable "emulator_credentials_file" {
  description = "Path to the emulator's per-run credentials file."
  type        = string
  default     = null
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "prefix" {
  description = "Name prefix for every resource."
  type        = string
  default     = "aet"
}

variable "cogs_dir" {
  description = "Directory of COGs uploaded to the COG bucket (scripts/fetch_data.py)."
  type        = string
  default     = "../data/cogs"
}

variable "authorizer_ttl" {
  description = <<-EOT
    Authorizer result cache TTL. On AWS use 300 with identity source = Authorization header.
    On aws-emulator the default is 0 with no identity source, so the authorizer can also read the
    token from X-Auth-Token (CloudFront on the emulator never forwards Authorization).
  EOT
  type        = number
  default     = null
}

variable "users" {
  description = "Demo users and their Cognito groups (roles)."
  type        = map(list(string))
  default = {
    alice = ["tiler"]
    bob   = ["features"]
    carol = ["admin"]
    dave  = []
  }
}
