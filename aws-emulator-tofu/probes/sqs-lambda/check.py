from lib import client, logs_contain, result

TITLE = "SQS queue -> Lambda event source mapping"
CATEGORY = "Event sources"
AWS_EXPECTED = "Messages are polled by the ESM and delivered to the Lambda."
FINDINGS = []


def check(outputs, row):
    client("sqs").send_message(QueueUrl=outputs["queue_url"], MessageBody="probe-sqs-msg-42")
    hit = logs_contain(outputs["log_group"], "probe-sqs-msg-42", timeout=45)
    return result("works", "message delivered to Lambda") if hit else result("gap", "no delivery within 45 s")
