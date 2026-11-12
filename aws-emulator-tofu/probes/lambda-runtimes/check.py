from lib import invoke, result

TITLE = "Lambda runtimes: python3.12/3.13, nodejs22.x, provided.al2023, ruby3.3, java21"
CATEGORY = "Lambda runtime"
AWS_EXPECTED = "Every managed runtime runs the handler (python = CPython, node = V8, custom runtimes via bootstrap)."
FINDINGS = ["lambda-rustpython", "lambda-runtimes-limited"]


def check(outputs, row):
    res = {}
    for k, fn in (outputs.get("functions") or {}).items():
        try:
            err, body = invoke(fn)
            res[k] = ("ERROR " + str(body)[:160]) if err else str(body)[:160]
        except Exception as e:  # noqa: BLE001  (e.g. InvalidRuntimeException from Invoke itself)
            res[k] = f"ERROR {type(e).__name__}: {str(e)[-140:]}"
    ok = [k for k, v in res.items() if not v.startswith("ERROR")]
    status = "works" if len(ok) == len(res) else ("partial" if ok else "gap")
    return result(status, "; ".join(f"{k}: {v}" for k, v in res.items()), per_runtime=res)
