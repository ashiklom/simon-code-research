from lib import client, result, wait_for

TITLE = "SNS topic -> SQS subscription (raw delivery)"
CATEGORY = "Event sources"
AWS_EXPECTED = "Published message appears in the queue."
FINDINGS = []


def check(outputs, row):
    client("sns").publish(TopicArn=outputs["topic"], Message="probe-sns-hello")
    def recv():
        m = client("sqs").receive_message(QueueUrl=outputs["queue_url"], WaitTimeSeconds=2).get("Messages")
        return m
    m = wait_for(recv, timeout=20, every=0)
    if m and "probe-sns-hello" in m[0]["Body"]:
        return result("works", "message delivered")
    return result("gap", f"received: {m}")
