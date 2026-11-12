resource "aws_s3_bucket" "b" {
  bucket        = "probe-s3-limits"
  force_destroy = true
}
resource "aws_s3_bucket_versioning" "v" {
  bucket = aws_s3_bucket.b.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_lifecycle_configuration" "l" {
  bucket = aws_s3_bucket.b.id
  rule {
    id     = "expire-tmp"
    status = "Enabled"
    filter { prefix = "tmp/" }
    expiration { days = 1 }
  }
}
resource "aws_s3_object" "o" {
  bucket  = aws_s3_bucket.b.id
  key     = "hello.txt"
  content = "hello"
}
output "bucket" { value = aws_s3_bucket.b.id }
