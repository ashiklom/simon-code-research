# A principal with s3:GetObjectAttributes (and ListBucket) but no s3:GetObject.
# AWS requires s3:GetObject too, so GetObjectAttributes is AccessDenied there.
resource "aws_s3_bucket" "b" {
  bucket        = "probe-getobjectattributes"
  force_destroy = true
}

resource "aws_s3_object" "o" {
  bucket  = aws_s3_bucket.b.id
  key     = "data/x.txt"
  content = "hello"
}

resource "aws_iam_user" "u" {
  name = "probe-getobjectattributes"
}

resource "aws_iam_user_policy" "p" {
  user = aws_iam_user.u.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:ListBucket", "s3:GetObjectAttributes", "s3:GetObjectVersionAttributes"]
      Resource = [aws_s3_bucket.b.arn, "${aws_s3_bucket.b.arn}/*"]
    }]
  })
}

resource "aws_iam_access_key" "k" {
  user = aws_iam_user.u.name
}

output "bucket" { value = aws_s3_bucket.b.id }
output "key" {
  value     = { id = aws_iam_access_key.k.id, secret = aws_iam_access_key.k.secret }
  sensitive = true
}
