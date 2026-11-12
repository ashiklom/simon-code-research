output "region" { value = var.region }
output "account_id" { value = data.aws_caller_identity.current.account_id }
output "user_pool_id" { value = module.identity.user_pool_id }
output "client_id" { value = module.identity.client_id }
output "cogs_bucket" { value = aws_s3_bucket.cogs.id }
output "cog_keys" { value = sort([for o in aws_s3_object.cog : o.key]) }
output "db_cluster_arn" { value = module.database.cluster_arn }
output "db_secret_arn" { value = module.database.secret_arn }
output "db_name" { value = module.database.database_name }
output "db_endpoint" { value = "${module.database.endpoint}:${module.database.port}" }

output "api_ids" { value = { for k, m in module.api : k => m.rest_api_id } }

# Base URLs per service. On aws-emulator, API Gateway is reached path-style through the emulator
# endpoint; on AWS, the regional execute-api hostname.
output "api_base_urls" {
  value = { for k, m in module.api : k => (
    var.emulator
    ? "${var.emulator_endpoint}/_aws/execute-api/${m.rest_api_id}/${m.stage_name}"
    : m.invoke_url
  ) }
}

output "cloudfront_id" { value = module.edge.distribution_id }
output "cloudfront_domain" { value = module.edge.domain_name }
output "cloudfront_base_url" {
  # aws-emulator: the per-distribution listener reported as DomainName (127.0.0.1:<port>), or the
  # path form on the main endpoint.
  value = var.emulator ? "${var.emulator_endpoint}/_aws/cloudfront/${module.edge.distribution_id}" : "https://${module.edge.domain_name}"
}

output "user_passwords" {
  value     = module.identity.passwords
  sensitive = true
}
output "user_groups" { value = var.users }
output "role_permissions" { value = local.role_permissions }
