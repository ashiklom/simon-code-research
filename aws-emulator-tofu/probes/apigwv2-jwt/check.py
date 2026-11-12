import base64
import json

from lib import b64url, client, result, session

TITLE = "HTTP API (v2) JWT authorizer + Lambda permission enforcement"
CATEGORY = "API Gateway"
AWS_EXPECTED = ("Valid Cognito token -> 200; token with altered payload, foreign-key signature or alg=none -> 401; "
                "route whose Lambda has no lambda:InvokeFunction permission for API Gateway -> 500.")
FINDINGS = ["apigwv2-jwt-no-signature-check", "apigwv2-no-lambda-permission-check"]


def check(outputs, row):
    from cryptography.hazmat.primitives.asymmetric import ec
    import jwt as pyjwt
    tok = client("cognito-idp").initiate_auth(AuthFlow="USER_PASSWORD_AUTH", ClientId=outputs["client"],
                                              AuthParameters={"USERNAME": "probe", "PASSWORD": "Probe-Passw0rd!"})["AuthenticationResult"]["AccessToken"]
    h, p, s = tok.split(".")
    claims = json.loads(base64.urlsafe_b64decode(p + "=="))
    forged_payload = f"{h}.{b64url({**claims, 'username': 'mallory'})}.{s}"
    foreign = pyjwt.encode({**claims, "username": "mallory"}, ec.generate_private_key(ec.SECP256R1()), algorithm="ES256",
                           headers={"kid": json.loads(base64.urlsafe_b64decode(h + "=="))["kid"]})
    none_alg = f"{b64url({'alg': 'none'})}.{b64url(claims)}."
    S = session()
    base = outputs["endpoint"].rstrip("/")
    out = {}
    for name, t, path in [("valid", tok, "/withperm"), ("altered-payload", forged_payload, "/withperm"),
                          ("foreign-key-signature", foreign, "/withperm"), ("alg-none", none_alg, "/withperm"),
                          ("no-token", None, "/withperm"), ("valid, Lambda without permission", tok, "/noperm")]:
        r = S.get(base + path, headers={"Authorization": t} if t else {}, timeout=15)
        out[name] = f"{r.status_code} {r.text[:60]}"
    exp = {"valid": "200", "altered-payload": "401", "foreign-key-signature": "401", "alg-none": "401",
           "no-token": "401", "valid, Lambda without permission": "500"}
    bad = [k for k in exp if not out[k].startswith(exp[k])]
    status = "works" if not bad else ("partial" if out["valid"].startswith("200") else "gap")
    return result(status, "; ".join(f"{k}: {v}" for k, v in out.items()), mismatches=bad)
