import base64
import json

import boto3
from lib import client, result

TITLE = "Cognito identity pool: user pool groups -> IAM roles via Token role mapping + CustomRoleArn"
CATEGORY = "Cognito"
AWS_EXPECTED = ("ID token carries cognito:roles for the user's groups; GetCredentialsForIdentity with CustomRoleArn "
                "vends 1 h STS credentials for a role in that list and refuses a role outside it; the session is "
                "assumed-role/<role>/CognitoIdentityCredentials and its policy (incl. explicit Deny) is enforced on "
                "S3; with server_side_token_check an ID token issued before AdminUserGlobalSignOut is refused.")
FINDINGS = ["cognito-identity-pool-roles"]


def claims(t):
    return json.loads(base64.urlsafe_b64decode(t.split(".")[1] + "=="))


def outcome(fn):
    try:
        fn()
        return "allowed"
    except Exception as e:  # noqa: BLE001
        return f"{type(e).__name__}"


def check(outputs, row):
    if not outputs:
        return result("gap", "apply failed: " + str((row.get("apply") or {}).get("error"))[:300])
    idp, ident, roles, bucket = client("cognito-idp"), client("cognito-identity"), outputs["roles"], outputs["bucket"]
    tok = idp.initiate_auth(AuthFlow="USER_PASSWORD_AUTH", ClientId=outputs["client"],
                            AuthParameters={"USERNAME": "probe", "PASSWORD": "Probe-Passw0rd-Identity!"})
    id_token = tok["AuthenticationResult"]["IdToken"]
    logins = {f"cognito-idp.us-east-1.amazonaws.com/{outputs['pool']}": id_token}
    iid = ident.get_id(IdentityPoolId=outputs["identity_pool"], Logins=logins)["IdentityId"]

    def creds(role):
        return ident.get_credentials_for_identity(IdentityId=iid, Logins=logins, CustomRoleArn=role)["Credentials"]

    c = {"cognito:roles": claims(id_token).get("cognito:roles")}
    rc = creds(roles["reader"])
    s = boto3.Session(aws_access_key_id=rc["AccessKeyId"], aws_secret_access_key=rc["SecretKey"],
                      aws_session_token=rc["SessionToken"])
    c["caller"] = s.client("sts").get_caller_identity()["Arn"]
    c["reader get data/ok.txt"] = outcome(lambda: s.client("s3").get_object(Bucket=bucket, Key="data/ok.txt"))
    c["reader get secret/no.txt"] = outcome(lambda: s.client("s3").get_object(Bucket=bucket, Key="secret/no.txt"))
    c["reader put"] = outcome(lambda: s.client("s3").put_object(Bucket=bucket, Key="data/new.txt", Body=b"x"))
    c["CustomRoleArn=writer (not in groups)"] = outcome(lambda: creds(roles["writer"]))
    c["CustomRoleArn=fallback (pool default, not in token)"] = outcome(lambda: creds(roles["fallback"]))
    idp.admin_user_global_sign_out(UserPoolId=outputs["pool"], Username="probe")
    c["old ID token after global sign-out"] = outcome(lambda: creds(roles["reader"]))
    good = {
        "roles claim": c["cognito:roles"] == [roles["reader"]],
        "session": "assumed-role/probe-idpool-reader/CognitoIdentityCredentials" in c["caller"],
        "allow": c["reader get data/ok.txt"] == "allowed",
        "explicit deny": c["reader get secret/no.txt"] != "allowed",
        "implicit deny": c["reader put"] != "allowed",
        "role outside groups refused": c["CustomRoleArn=writer (not in groups)"] != "allowed",
        "server_side_token_check": c["old ID token after global sign-out"] != "allowed",
    }
    n = sum(good.values())
    return result("works" if n == len(good) else ("partial" if n else "gap"),
                  "; ".join(f"{k}: {v}" for k, v in c.items()), checks=good)
