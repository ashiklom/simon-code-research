import os
import shutil
import subprocess
import zipfile
from pathlib import Path

from lib import invoke, result

TITLE = "Real tipg (FastAPI/asyncpg/pydantic-core wheels) as a python3.12 zip Lambda"
CATEGORY = "Lambda runtime"
AWS_EXPECTED = "Imports succeed (CPython + manylinux wheels); requests reach tipg (DB errors aside)."
FINDINGS = ["lambda-rustpython", "lambda-native-extensions"]
APPLY_TIMEOUT = 400

HANDLER = '''
import json, sys, traceback
def handler(event, context):
    try:
        import pydantic_core  # noqa: F401  (native extension)
        from mangum import Mangum
        from tipg.main import app
        return Mangum(app, lifespan="off")(event, context)
    except BaseException as e:
        return {"statusCode": 500, "body": json.dumps({"import_error": f"{type(e).__name__}: {e}",
                "impl": sys.implementation.name, "trace": traceback.format_exc()[-600:]})}
'''


def prepare(d: Path):
    build = d / "build"
    z = build / "tipg.zip"
    if z.exists():
        return {"zip_mb": round(z.stat().st_size / 1e6, 1)}
    pkg = build / "pkg"
    shutil.rmtree(pkg, ignore_errors=True)
    pkg.mkdir(parents=True)
    subprocess.run(["uv", "pip", "install", "--quiet", "--target", str(pkg), "--python-platform",
                    "x86_64-manylinux2014", "--python-version", "3.12", "--only-binary", ":all:",
                    "tipg==1.6.1", "mangum"], check=True)
    (pkg / "handler.py").write_text(HANDLER)
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in pkg.rglob("*"):
            if p.is_file() and "__pycache__" not in p.parts:
                zf.write(p, p.relative_to(pkg))
    shutil.rmtree(pkg)
    return {"zip_mb": round(z.stat().st_size / 1e6, 1)}


def check(outputs, row):
    if not row["apply"]["ok"]:
        return result("gap", row["apply"]["error"])
    ev = {"resource": "/{proxy+}", "path": "/collections", "httpMethod": "GET", "headers": {"host": "x"},
          "multiValueHeaders": {}, "queryStringParameters": None, "multiValueQueryStringParameters": None,
          "requestContext": {"stage": "prod", "path": "/prod/collections", "httpMethod": "GET",
                             "identity": {"sourceIp": "127.0.0.1"}, "requestId": "r"}, "body": None,
          "isBase64Encoded": False}
    err, body = invoke(outputs["fn"], ev)
    text = str(body)
    if err:
        return result("gap", f"invoke FunctionError={err}: {text[:500]}")
    if "import_error" in text:
        return result("gap", text[:500])
    return result("works", text[:300])
