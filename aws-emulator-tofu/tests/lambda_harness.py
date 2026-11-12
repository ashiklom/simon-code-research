"""Load a Lambda package (lambdas/<name> + lambdas/common) in-process under CPython, isolated."""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent.parent
LAMBDAS = ROOT / "lambdas"
_SHARED = {"apigw", "handler", "cog", "render", "colormaps", "db", "geom", "jwt_verify", "ec", "policy"}


def load(name: str):
    for mod in list(sys.modules):
        if mod in _SHARED:
            del sys.modules[mod]
    sys.path[:0] = [str(LAMBDAS / name), str(LAMBDAS / "common")]
    try:
        return importlib.import_module("handler")
    finally:
        del sys.path[:2]


def event(path, params=None, method="GET", headers=None, body=None, authorizer=None, stage="prod"):
    mv = {}
    for k, v in (params or {}).items():
        mv.setdefault(k, []).extend(v if isinstance(v, list) else [str(v)])
    return {
        "resource": "/{proxy+}", "path": path, "httpMethod": method,
        "headers": {"Host": "api.example.com", **(headers or {})},
        "queryStringParameters": {k: v[-1] for k, v in mv.items()} or None,
        "multiValueQueryStringParameters": mv or None,
        "body": body, "isBase64Encoded": False,
        "requestContext": {"stage": stage, "path": f"/{stage}{path}", "authorizer": authorizer or {}},
    }


def call(mod, path, params=None, **kw):
    r = mod.handler(event(path, params, **kw), None)
    body = r["body"]
    if r.get("isBase64Encoded"):
        import base64
        body = base64.b64decode(body)
    elif r["headers"].get("Content-Type", "").endswith("json"):
        body = json.loads(body)
    return r["statusCode"], r["headers"], body
