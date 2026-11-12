"""Token service: mints user-specific JWTs from Cognito and reports the caller's roles.

  POST /auth/token  {"username": "...", "password": "..."}  -> Cognito InitiateAuth USER_PASSWORD_AUTH
  POST /auth/token  {"refresh_token": "..."}                -> REFRESH_TOKEN_AUTH
  GET  /auth/me                                             -> who am I (from the authorizer context)

InitiateAuth is an unsigned Cognito API, so it is called with plain urllib (aws-emulator's
in-Lambda boto3 stand-in has no cognito-idp client).
"""
import base64
import json
import os
import re
import urllib.error
import urllib.request

from apigw import HTTPError, dispatch, response

PREFIX = "/auth"


def _cognito(target, payload):
    region = os.environ.get("AWS_REGION", "us-east-1")
    url = os.environ.get("COGNITO_ENDPOINT") or f"https://cognito-idp.{region}.amazonaws.com/"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST", headers={
        "Content-Type": "application/x-amz-json-1.1",
        "X-Amz-Target": f"AWSCognitoIdentityProviderService.{target}",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read())
        except Exception:  # noqa: BLE001
            err = {}
        kind = (err.get("__type") or "").split("#")[-1]
        if kind in ("NotAuthorizedException", "UserNotFoundException"):
            raise HTTPError(401, "Incorrect username or password.")
        raise HTTPError(502, f"Cognito error {e.code}: {kind or err}")


def _claims(jwt):
    p = jwt.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))


def token(req):
    body = req.json()
    client_id = os.environ["CLIENT_ID"]
    if body.get("refresh_token"):
        payload = {"AuthFlow": "REFRESH_TOKEN_AUTH", "ClientId": client_id,
                   "AuthParameters": {"REFRESH_TOKEN": body["refresh_token"]}}
    elif body.get("username") and body.get("password"):
        payload = {"AuthFlow": "USER_PASSWORD_AUTH", "ClientId": client_id,
                   "AuthParameters": {"USERNAME": body["username"], "PASSWORD": body["password"]}}
    else:
        raise HTTPError(422, "Provide username+password or refresh_token")
    res = _cognito("InitiateAuth", payload)
    if "AuthenticationResult" not in res:
        raise HTTPError(401, f"Additional challenge required: {res.get('ChallengeName')}")
    ar = res["AuthenticationResult"]
    claims = _claims(ar["AccessToken"])
    return response(200, {
        "token_type": ar.get("TokenType", "Bearer"),
        "access_token": ar["AccessToken"],
        "id_token": ar.get("IdToken"),
        "refresh_token": ar.get("RefreshToken"),
        "expires_in": ar.get("ExpiresIn"),
        "username": claims.get("username") or claims.get("cognito:username"),
        "groups": claims.get("cognito:groups") or [],
    })


def me(req):
    a = req.authorizer
    split = lambda s: [x for x in (s or "").split(",") if x]  # noqa: E731
    return response(200, {"username": a.get("username"), "sub": a.get("sub"),
                          "groups": split(a.get("groups")), "permissions": split(a.get("permissions"))})


ROUTES = [
    ("POST", re.compile(PREFIX + r"/token"), token),
    ("GET", re.compile(PREFIX + r"/me"), me),
]


def handler(event, context):
    return dispatch(ROUTES, event)
