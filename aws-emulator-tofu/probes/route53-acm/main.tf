resource "aws_route53_zone" "z" { name = "aws-emulator-tofu-probe.com" }
resource "aws_acm_certificate" "c" {
  domain_name       = "api.aws-emulator-tofu-probe.com"
  validation_method = "DNS"
}
resource "aws_route53_record" "v" {
  for_each = { for o in aws_acm_certificate.c.domain_validation_options : o.domain_name => o }
  zone_id  = aws_route53_zone.z.zone_id
  name     = each.value.resource_record_name
  type     = each.value.resource_record_type
  records  = [each.value.resource_record_value]
  ttl      = 60
}
resource "aws_acm_certificate_validation" "v" {
  certificate_arn         = aws_acm_certificate.c.arn
  validation_record_fqdns = [for r in aws_route53_record.v : r.fqdn]
  timeouts { create = "2m" }
}
resource "aws_route53_record" "a" {
  zone_id = aws_route53_zone.z.zone_id
  name    = "www.aws-emulator-tofu-probe.com"
  type    = "A"
  ttl     = 60
  records = ["192.0.2.10"]
}
output "zone" { value = aws_route53_zone.z.zone_id }
output "cert" { value = aws_acm_certificate.c.arn }
