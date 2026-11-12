from lib import invoke, result

TITLE = "IAM evaluation inside Lambda (allow prefix, explicit deny, implicit deny)"
CATEGORY = "IAM"
AWS_EXPECTED = "public/ok.txt readable; private/* AccessDenied (explicit deny); PutObject AccessDenied (implicit deny)."
FINDINGS = ["iam-enforced-in-lambda"]


def check(outputs, row):
    err, b = invoke(outputs["fn"])
    if err:
        return result("gap", str(b)[:300])
    good = (b.get("public/ok.txt") == "ok" and str(b.get("private/secret.txt")).startswith("DENIED")
            and str(b.get("put")).startswith("DENIED"))
    return result("works" if good else "gap", str(b)[:400])
