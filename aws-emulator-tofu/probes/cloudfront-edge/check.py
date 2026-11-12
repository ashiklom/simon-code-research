import json

from lib import ENDPOINT, result, session

TITLE = "CloudFront edge features in front of a REST API"
CATEGORY = "CloudFront"
AWS_EXPECTED = ("viewer-request CloudFront Function runs; response-headers policy adds header; origin Content-Type/"
                "custom headers pass through; 2nd GET is a cache hit (same body); http:// -> 301; WAF blocks /blocked "
                "(403); Authorization forwarded only if in the cache key (not here), X-Custom via origin request policy.")
FINDINGS = ["cloudfront-no-functions", "cloudfront-drops-origin-headers", "cloudfront-authorization-dropped",
            "cloudfront-viewer-protocol", "cloudfront-waf-works"]


def check(outputs, row):
    S = session()
    base = f"{ENDPOINT}/_aws/cloudfront/{outputs['id']}"
    r1 = S.get(base + "/echo", params={"q": "1"}, headers={"X-Custom": "c1", "Authorization": "Bearer t"})
    r2 = S.get(base + "/echo", params={"q": "1"})
    b1 = json.loads(r1.text) if r1.status_code == 200 else {}
    b2 = json.loads(r2.text) if r2.status_code == 200 else {}
    hdrs = b1.get("headers", {})
    checks = {
        "origin reachable": r1.status_code == 200,
        "CloudFront Function ran (x-cf-function seen by origin)": hdrs.get("x-cf-function") == "ran",
        "response-headers policy header (X-Probe-RHP)": r1.headers.get("x-probe-rhp") == "added",
        "origin Content-Type kept (text/x-probe)": r1.headers.get("content-type") == "text/x-probe",
        "origin custom header kept (X-Origin-Header)": r1.headers.get("x-origin-header") == "kept",
        "X-Custom forwarded (origin request policy)": hdrs.get("x-custom") == "c1",
        "query string forwarded": (b1.get("query") or {}).get("q") == "1",
        "2nd request cache hit (same nonce)": bool(b1) and b1.get("nonce") == b2.get("nonce"),
        "x-cache header present": "x-cache" in {k.lower() for k in r2.headers},
        "WAF blocks /blocked (403)": S.get(base + "/blocked/x").status_code == 403,
    }
    try:
        rh = S.get(f"http://{outputs['domain']}/echo", allow_redirects=False, timeout=10)
        checks["http:// redirected to https (301)"] = rh.status_code in (301, 302)
        checks_detail = f"http:// -> {rh.status_code}"
    except Exception as e:  # noqa: BLE001
        checks["http:// redirected to https (301)"] = False
        checks_detail = f"http:// -> {e!r}"[:100]
    ok = [k for k, v in checks.items() if v]
    bad = [k for k, v in checks.items() if not v]
    status = "works" if not bad else ("partial" if checks["origin reachable"] else "gap")
    return result(status, f"OK: {ok} | NOT: {bad} | {checks_detail} | x-cache={r2.headers.get('x-cache')}",
                  checks=checks)
