"""Minimal API Gateway (REST, Lambda proxy v1.0 event) request/response helpers.

Pure standard library so it runs on AWS Lambda *and* on aws-emulator's RustPython runtime.
Copied into every function zip at package time (see infra/modules/lambda_function).
"""
import base64
import json
from urllib.parse import quote, urlencode


class HTTPError(Exception):
    def __init__(self, status, detail):
        super().__init__(detail)
        self.status = status
        self.detail = detail


class Request:
    def __init__(self, event):
        self.event = event
        self.method = event.get("httpMethod", "GET")
        self.path = event.get("path") or "/"
        self.headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
        mv = event.get("multiValueQueryStringParameters") or {}
        sv = event.get("queryStringParameters") or {}
        self.query_multi = {k: list(v) for k, v in mv.items()} if mv else {k: [v] for k, v in sv.items()}
        body = event.get("body")
        if body and event.get("isBase64Encoded"):
            body = base64.b64decode(body).decode("utf-8")
        self.body = body
        ctx = event.get("requestContext") or {}
        self.authorizer = ctx.get("authorizer") or {}
        self.stage = ctx.get("stage")
        self.base_url = self._base_url(ctx)

    def _base_url(self, ctx):
        """Public URL prefix that, joined with `self.path`, reproduces the URL the client called.

        CloudFront/proxies can set X-Forwarded-Host (+ X-Forwarded-Prefix); otherwise use the Host
        header and whatever came before the resource path in requestContext.path (the stage on
        AWS, `/_aws/execute-api/<id>/<stage>` on aws-emulator).
        """
        host = self.headers.get("x-forwarded-host") or self.headers.get("host") or "localhost"
        proto = self.headers.get("x-forwarded-proto") or self.headers.get("cloudfront-forwarded-proto") or "https"
        if self.headers.get("x-forwarded-host"):
            return f"{proto}://{host}{self.headers.get('x-forwarded-prefix', '')}"
        full = ctx.get("path") or ""
        prefix = full[: -len(self.path)] if self.path and full.endswith(self.path) else ""
        return f"{proto}://{host}{prefix}"

    def arg(self, name, default=None):
        v = self.query_multi.get(name)
        return v[0] if v else default

    def args(self, name):
        return self.query_multi.get(name, [])

    def json(self):
        try:
            return json.loads(self.body or "{}")
        except ValueError:
            raise HTTPError(400, "Body is not valid JSON")

    def url(self, path, params=None):
        q = ""
        if params:
            q = "?" + urlencode([(k, v) for k, v in params if v is not None], quote_via=quote)
        return self.base_url + path + q


def response(status=200, body=None, content_type="application/json", headers=None, binary=False):
    h = {"Content-Type": content_type}
    if headers:
        h.update(headers)
    if binary:
        return {"statusCode": status, "headers": h, "isBase64Encoded": True,
                "body": base64.b64encode(body).decode("ascii")}
    if not isinstance(body, str):
        body = json.dumps(body, separators=(",", ":"))
    return {"statusCode": status, "headers": h, "isBase64Encoded": False, "body": body}


def error(status, detail):
    return response(status, {"detail": detail})


def dispatch(routes, event):
    """routes: list of (method, compiled_regex, fn(req, **groups)). Returns a proxy response."""
    req = Request(event)
    try:
        for method, rx, fn in routes:
            m = rx.fullmatch(req.path)
            if m and method == req.method:
                return fn(req, **m.groupdict())
        raise HTTPError(404, "Not Found")
    except HTTPError as e:
        return error(e.status, e.detail)
