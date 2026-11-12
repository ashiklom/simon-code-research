from lib import client, result

TITLE = "Route 53 hosted zone + ACM certificate with DNS validation"
CATEGORY = "DNS & certificates"
AWS_EXPECTED = ("Validation record makes the certificate ISSUED within minutes (for a publicly delegated zone; a reserved TLD such as .example is refused); TestDNSAnswer returns the A record.")
FINDINGS = []
APPLY_TIMEOUT = 240


def check(outputs, row):
    if not row["apply"]["ok"]:
        return result("gap", row["apply"]["error"])
    st = client("acm").describe_certificate(CertificateArn=outputs["cert"])["Certificate"]["Status"]
    try:
        ans = client("route53").test_dns_answer(HostedZoneId=outputs["zone"], RecordName="www.aws-emulator-tofu-probe.com",
                                                RecordType="A")["RecordData"]
    except Exception as e:  # noqa: BLE001
        ans = f"error: {e}"[:120]
    ok = st == "ISSUED" and ans == ["192.0.2.10"]
    return result("works" if ok else "partial", f"certificate={st}; TestDNSAnswer={ans}; (no real DNS is served)")
