from lib import logs_contain, result

TITLE = "EventBridge scheduled rule rate(1 minute) -> Lambda"
CATEGORY = "Event sources"
AWS_EXPECTED = "Lambda invoked about once a minute with a 'Scheduled Event'."
FINDINGS = []


def check(outputs, row):
    hit = logs_contain(outputs["log_group"], "Scheduled Event", timeout=100)
    return result("works", "scheduled invocation observed") if hit else result("gap", "no scheduled invocation within 100 s")
