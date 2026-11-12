from lib import client, logs_contain, result

TITLE = "S3 event notification -> Lambda"
CATEGORY = "Event sources"
AWS_EXPECTED = "PutObject under incoming/ asynchronously invokes the Lambda with an ObjectCreated event."
FINDINGS = []


def check(outputs, row):
    client("s3").put_object(Bucket=outputs["bucket"], Key="incoming/a.txt", Body=b"x")
    hit = logs_contain(outputs["log_group"], "incoming/a.txt", timeout=45)
    return result("works", "Lambda received ObjectCreated event") if hit else result("gap", "no invocation within 45 s")
