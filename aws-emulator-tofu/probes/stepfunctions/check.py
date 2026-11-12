import json

from lib import client, logs_contain, result, wait_for

TITLE = "Step Functions (Pass -> Choice -> Lambda Task)"
CATEGORY = "Event sources"
AWS_EXPECTED = "Execution SUCCEEDED with the Lambda's output."
FINDINGS = []


def check(outputs, row):
    sfn = client("stepfunctions")
    ex = sfn.start_execution(stateMachineArn=outputs["sm"], input=json.dumps({"value": "sfn-probe-input"}))["executionArn"]
    def done():
        d = sfn.describe_execution(executionArn=ex)
        return d if d["status"] != "RUNNING" else None
    d = wait_for(done, timeout=30, every=1)
    if d and d["status"] == "SUCCEEDED":
        seen = logs_contain(outputs["log_group"], "sfn-probe-input", timeout=10)
        return result("works", f"SUCCEEDED output={d.get('output')} lambda_saw_input={bool(seen)}")
    return result("gap", f"execution: {d and d['status']} {d and d.get('error')} {d and d.get('cause')}")
