from lib import invoke, result

TITLE = "Python Lambda layer (pure-Python module under python/)"
CATEGORY = "Lambda runtime"
AWS_EXPECTED = "Layer is extracted to /opt; python/ is on sys.path, so `import probe_layer_mod` works."
FINDINGS = ["lambda-python-layers"]


def check(outputs, row):
    err, body = invoke(outputs["fn"])
    if not err and body == {"value": "from-layer"}:
        return result("works", "layer module imported")
    return result("gap", f"invoke error: {str(body)[:300]}")
