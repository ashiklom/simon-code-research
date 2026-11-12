from lib import ENDPOINT, result, session

TITLE = "Application Load Balancer -> Lambda target"
CATEGORY = "Networking"
AWS_EXPECTED = "HTTP request to the (internal) ALB DNS name invokes the Lambda and returns 'alb-ok'."
FINDINGS = ["elb-data-plane"]


def check(outputs, row):
    if not row["apply"]["ok"]:
        return result("gap", row["apply"]["error"])
    S = session()
    tried = {}
    for url, hdr in [(f"http://{outputs['dns']}/x", {}), (f"{ENDPOINT}/x", {"Host": outputs["dns"]}),
                     (f"{ENDPOINT}/_aws/elb/{outputs['dns']}/x", {})]:
        try:
            r = S.get(url, headers=hdr, timeout=8)
            tried[url + (" Host:" + hdr["Host"] if hdr else "")] = f"{r.status_code} {r.text[:50]}"
            if "alb-ok" in r.text:
                return result("works", f"{url} -> {r.text[:40]}")
        except Exception as e:  # noqa: BLE001
            tried[url] = type(e).__name__
    return result("partial", f"control plane applied (ALB, TG, listener, attachment) but no data plane reachable: {tried}")
