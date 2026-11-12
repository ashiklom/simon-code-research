# With the provider allowed to learn the account id, aws_s3_bucket reads tags via S3 Control,
# whose endpoint gets an "<account>." host prefix -> "000000000000.127.0.0.1:9297" (unresolvable).
resource "aws_s3_bucket" "b" {
  bucket        = "probe-s3control-tagging"
  force_destroy = true
}
