# REST API with a MOCK integration that returns CORS headers, called as a browser on another site would.
resource "aws_api_gateway_rest_api" "a" { name = "probe-cors" }
resource "aws_api_gateway_resource" "r" {
  rest_api_id = aws_api_gateway_rest_api.a.id
  parent_id   = aws_api_gateway_rest_api.a.root_resource_id
  path_part   = "data"
}
resource "aws_api_gateway_method" "m" {
  for_each      = toset(["GET", "OPTIONS"])
  rest_api_id   = aws_api_gateway_rest_api.a.id
  resource_id   = aws_api_gateway_resource.r.id
  http_method   = each.value
  authorization = "NONE"
}
resource "aws_api_gateway_integration" "i" {
  for_each          = aws_api_gateway_method.m
  rest_api_id       = aws_api_gateway_rest_api.a.id
  resource_id       = aws_api_gateway_resource.r.id
  http_method       = each.value.http_method
  type              = "MOCK"
  request_templates = { "application/json" = "{\"statusCode\": 200}" }
}
resource "aws_api_gateway_method_response" "mr" {
  for_each    = aws_api_gateway_method.m
  rest_api_id = aws_api_gateway_rest_api.a.id
  resource_id = aws_api_gateway_resource.r.id
  http_method = each.value.http_method
  status_code = "200"
  response_parameters = {
    "method.response.header.Access-Control-Allow-Origin"  = true
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
  }
}
resource "aws_api_gateway_integration_response" "ir" {
  for_each    = aws_api_gateway_method.m
  rest_api_id = aws_api_gateway_rest_api.a.id
  resource_id = aws_api_gateway_resource.r.id
  http_method = each.value.http_method
  status_code = aws_api_gateway_method_response.mr[each.key].status_code
  response_parameters = {
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
    "method.response.header.Access-Control-Allow-Headers" = "'Authorization,Content-Type'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,OPTIONS'"
  }
  response_templates = { "application/json" = "{\"ok\": true}" }
  depends_on         = [aws_api_gateway_integration.i]
}
resource "aws_api_gateway_deployment" "d" {
  rest_api_id = aws_api_gateway_rest_api.a.id
  depends_on  = [aws_api_gateway_integration_response.ir]
}
resource "aws_api_gateway_stage" "s" {
  rest_api_id   = aws_api_gateway_rest_api.a.id
  deployment_id = aws_api_gateway_deployment.d.id
  stage_name    = "prod"
}
output "api" { value = aws_api_gateway_rest_api.a.id }
