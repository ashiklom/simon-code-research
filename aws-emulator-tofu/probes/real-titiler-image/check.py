from lib import invoke, result

TITLE = "Container-image Lambda (PackageType=Image from ECR), as titiler's Lambda deployment uses"
CATEGORY = "Lambda runtime"
AWS_EXPECTED = "Image function runs its CMD handler."
FINDINGS = ["lambda-container-images"]


def check(outputs, row):
    if not row["apply"]["ok"]:
        return result("gap", row["apply"]["error"])
    err, body = invoke(outputs["fn"])
    if err:
        return result("gap", f"function created from {outputs.get('repository_url')}:latest, but Invoke fails: {str(body)[:300]}")
    return result("works", str(body)[:200])
