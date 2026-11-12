import base64
import json

from lib import ENDPOINT, client, result, session

TITLE = "Cognito: pre-token-generation V2 claims/scopes, custom attributes, SRP, hosted OAuth2 client_credentials"
CATEGORY = "Cognito"
AWS_EXPECTED = ("Tokens are RS256; pre-token trigger adds custom_role claim + tiler/read scope; ID token carries "
                "custom:department; SRP works; https://<domain>.auth.<region>.amazoncognito.com/oauth2/token issues "
                "client_credentials tokens with scope tiler/read.")
FINDINGS = ["cognito-es256", "cognito-pretoken-ignored", "cognito-custom-attrs-missing", "cognito-no-oauth-endpoints",
            "cognito-no-srp", "cognito-iss-host"]


def claims(t):
    return json.loads(base64.urlsafe_b64decode(t.split(".")[1] + "=="))


def header(t):
    return json.loads(base64.urlsafe_b64decode(t.split(".")[0] + "=="))


def check(outputs, row):
    cog = client("cognito-idp")
    ar = cog.initiate_auth(AuthFlow="USER_PASSWORD_AUTH", ClientId=outputs["client"],
                           AuthParameters={"USERNAME": "probe", "PASSWORD": "Probe-Passw0rd!"})["AuthenticationResult"]
    at, it = claims(ar["AccessToken"]), claims(ar["IdToken"])
    c = {
        "alg": header(ar["AccessToken"]).get("alg"),
        "iss": at.get("iss"),
        "pretoken claim in access token": at.get("custom_role"),
        "pretoken scope added": "tiler/read" in (at.get("scope") or ""),
        "custom:department in id token": it.get("custom:department"),
    }
    try:
        cog.initiate_auth(AuthFlow="USER_SRP_AUTH", ClientId=outputs["client"],
                          AuthParameters={"USERNAME": "probe", "SRP_A": "a" * 512})
        c["USER_SRP_AUTH"] = "accepted"
    except Exception as e:  # noqa: BLE001
        c["USER_SRP_AUTH"] = f"{type(e).__name__}: {str(e)[:80]}"
    S = session()
    tok_url = f"{ENDPOINT}/oauth2/token"
    r = S.post(tok_url, data={"grant_type": "client_credentials", "scope": "tiler/read"},
               auth=(outputs["m2m_id"], outputs["m2m_secret"]))
    c["POST <emulator>/oauth2/token"] = f"{r.status_code} {r.text[:60]}"
    host = f"{outputs['domain']}.auth.us-east-1.amazoncognito.com"
    r = S.post(tok_url, data={"grant_type": "client_credentials", "scope": "tiler/read"},
               auth=(outputs["m2m_id"], outputs["m2m_secret"]), headers={"Host": host})
    c[f"POST /oauth2/token Host:{host}"] = f"{r.status_code} {r.text[:60]}"
    good = {"alg": c["alg"] == "RS256", "pretoken": c["pretoken claim in access token"] == "tiler",
            "scope": c["pretoken scope added"], "attr": c["custom:department in id token"] == "geo",
            "srp": c["USER_SRP_AUTH"] == "accepted",
            "oauth": any(v.startswith("200") for k, v in c.items() if "oauth2" in k)}
    n = sum(good.values())
    return result("works" if n == len(good) else ("partial" if n else "gap"),
                  "; ".join(f"{k}: {v}" for k, v in c.items()), checks=good)
