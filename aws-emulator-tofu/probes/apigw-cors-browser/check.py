from lib import ENDPOINT, result, session

TITLE = "Browser-style cross-origin calls to a REST API with CORS headers (MOCK integration)"
CATEGORY = "API Gateway"
AWS_EXPECTED = "GET and OPTIONS preflight from Origin https://maps.example.org return 200 with Access-Control-Allow-Origin."
FINDINGS = ["front-door-cross-origin"]


def check(outputs, row):
    S = session()
    url = f"{ENDPOINT}/_aws/execute-api/{outputs['api']}/prod/data"
    plain = S.get(url)
    origin = {"Origin": "https://maps.example.org"}
    get = S.get(url, headers={**origin, "Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "cors"})
    pre = S.options(url, headers={**origin, "Access-Control-Request-Method": "GET",
                                  "Access-Control-Request-Headers": "authorization", "Sec-Fetch-Site": "cross-site",
                                  "Sec-Fetch-Mode": "cors"})
    d = (f"no Origin: {plain.status_code} {plain.text[:40]} ACAO={plain.headers.get('access-control-allow-origin')}; "
         f"cross-site GET: {get.status_code} {get.text[:80]} ACAO={get.headers.get('access-control-allow-origin')}; "
         f"preflight: {pre.status_code} {pre.text[:60]}")
    ok = get.status_code == 200 and pre.status_code == 200 and get.headers.get("access-control-allow-origin") == "*"
    return result("works" if ok else ("partial" if plain.status_code == 200 else "gap"), d)
