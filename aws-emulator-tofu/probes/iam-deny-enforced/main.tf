resource "aws_s3_bucket" "b" {
  bucket        = "probe-iam-deny"
  force_destroy = true
}
resource "aws_s3_object" "ok" {
  bucket  = aws_s3_bucket.b.id
  key     = "public/ok.txt"
  content = "ok"
}
resource "aws_s3_object" "secret" {
  bucket  = aws_s3_bucket.b.id
  key     = "private/secret.txt"
  content = "secret"
}
resource "aws_iam_role" "r" {
  name               = "probe-iam-deny"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}
resource "aws_iam_role_policy" "p" {
  role = aws_iam_role.r.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = "s3:GetObject", Resource = "${aws_s3_bucket.b.arn}/*" },
      { Effect = "Deny", Action = "s3:GetObject", Resource = "${aws_s3_bucket.b.arn}/private/*" },
    ]
  })
}
data "archive_file" "fn" {
  type        = "zip"
  output_path = "${path.module}/build/fn.zip"
  source {
    filename = "app.py"
    content  = <<-PY
      import boto3
      def handler(e, c):
          s3 = boto3.client("s3"); out = {}
          for k in ["public/ok.txt", "private/secret.txt"]:
              try:
                  out[k] = s3.get_object(Bucket="probe-iam-deny", Key=k)["Body"].read().decode()
              except Exception as ex:
                  out[k] = "DENIED: " + str(ex)[:120]
          try:
              boto3.client("s3").put_object(Bucket="probe-iam-deny", Key="public/new.txt", Body=b"x")
              out["put"] = "allowed"
          except Exception as ex:
              out["put"] = "DENIED: " + str(ex)[:120]
          return out
    PY
  }
}
resource "aws_lambda_function" "f" {
  function_name    = "probe-iam-deny"
  role             = aws_iam_role.r.arn
  runtime          = "python3.12"
  handler          = "app.handler"
  filename         = data.archive_file.fn.output_path
  source_code_hash = data.archive_file.fn.output_base64sha256
  depends_on       = [aws_iam_role_policy.p]
}
output "fn" { value = aws_lambda_function.f.function_name }
