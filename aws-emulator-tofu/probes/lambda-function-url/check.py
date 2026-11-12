from lib import result, session

TITLE = "Lambda function URL (auth NONE)"
CATEGORY = "Lambda runtime"
AWS_EXPECTED = "https://<id>.lambda-url.<region>.on.aws/ invokes the function over HTTPS."
FINDINGS = ["lambda-function-url"]


def check(outputs, row):
    url = outputs.get("url")
    s = session()
    tried = {}
    for u in [url, url and url.replace("https://", "http://")]:
        try:
            r = s.get(u.rstrip("/") + "/probe", timeout=10)
            tried[u] = (r.status_code, r.text[:120])
            if r.status_code == 200 and "url" in r.text:
                return result("works", f"{u} -> {r.status_code} {r.text[:100]}")
        except Exception as e:  # noqa: BLE001
            tried[u] = repr(e)[:160]
    # aws-emulator serves function URLs on its own port, selected by the Host header.
    from urllib.parse import urlparse
    from lib import ENDPOINT
    host = urlparse(url).hostname
    r = s.get(ENDPOINT + "/probe", headers={"Host": host}, timeout=10)
    if r.status_code == 200 and "url" in r.text:
        return result("partial", f"published URL {url} is unreachable (real AWS hostname, no DNS); works when sent to "
                                 f"{ENDPOINT} with Host: {host} -> {r.status_code} {r.text[:80]}")
    return result("gap", f"function_url={url}; requests: {tried}; Host-header form -> {r.status_code} {r.text[:120]}")
