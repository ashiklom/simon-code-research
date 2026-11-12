resource "aws_sns_topic" "t" { name = "probe-topic" }
resource "aws_sqs_queue" "q" { name = "probe-sns-target" }
resource "aws_sqs_queue_policy" "p" {
  queue_url = aws_sqs_queue.q.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "sns.amazonaws.com" },
  Action = "sqs:SendMessage", Resource = aws_sqs_queue.q.arn, Condition = { ArnEquals = { "aws:SourceArn" = aws_sns_topic.t.arn } } }] })
}
resource "aws_sns_topic_subscription" "s" {
  topic_arn            = aws_sns_topic.t.arn
  protocol             = "sqs"
  endpoint             = aws_sqs_queue.q.arn
  raw_message_delivery = true
}
output "topic" { value = aws_sns_topic.t.arn }
output "queue_url" { value = aws_sqs_queue.q.url }
