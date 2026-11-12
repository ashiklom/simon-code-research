# titiler's documented Lambda deployment is a container image. No Docker daemon is available
# here, so a minimal OCI image is pushed through the ECR API (push_image.py) to exercise the
# PackageType=Image path end to end.
resource "aws_ecr_repository" "r" {
  name                 = "probe/titiler"
  force_delete         = true
  image_tag_mutability = "MUTABLE"
}
resource "terraform_data" "push" {
  input = aws_ecr_repository.r.name
  provisioner "local-exec" {
    command     = "pixi run python probes/real-titiler-image/push_image.py ${aws_ecr_repository.r.name}"
    working_dir = "${path.module}/../.."
  }
}
resource "aws_iam_role" "r" {
  name               = "probe-titiler-image"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}
resource "aws_lambda_function" "f" {
  function_name = "probe-titiler-image"
  role          = aws_iam_role.r.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.r.repository_url}:latest"
  memory_size   = 1024
  timeout       = 30
  depends_on    = [terraform_data.push]
}
output "fn" { value = aws_lambda_function.f.function_name }
output "repository_url" { value = aws_ecr_repository.r.repository_url }
