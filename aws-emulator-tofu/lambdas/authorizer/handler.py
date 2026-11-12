"""API Gateway REQUEST authorizer: verify a Cognito access token, map cognito:groups to permissions.

Environment (all JSON unless noted):
  JWKS_URL            pool JWKS URL (fetched once per container, refetched on unknown kid)
  JWKS_JSON           optional inline JWKS (fallback when the runtime cannot fetch JWKS_URL)
  ALLOWED_ISSUERS     list of accepted `iss` values
  ALLOWED_CLIENT_IDS  list of accepted app-client ids (`client_id` claim of access tokens)
  ROLE_PERMISSIONS    {"tiler": ["tiler"], "features": ["features"], "admin": ["*"]}
  BASE_PERMISSIONS    permissions every authenticated user gets, e.g. ["auth/me"]
  TOKEN_HEADERS       header names to read the token from, in order (default ["authorization", "x-auth-token"])
"""
import json
import os
import time
import urllib.request

from jwt_verify import InvalidToken, verify
from policy import permissions_for, policy

_JWKS = None


def _env_json(name, default):
    v = os.environ.get(name)
    return json.loads(v) if v else default


def _jwks(refresh=False):
    global _JWKS
    if _JWKS is not None and not refresh:
        return _JWKS
    url = os.environ.get("JWKS_URL")
    if url:
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                _JWKS = json.loads(r.read())
                return _JWKS
        except Exception as e:  # noqa: BLE001
            print(f"JWKS fetch from {url} failed: {e!r}; using JWKS_JSON fallback")
    _JWKS = _env_json("JWKS_JSON", {"keys": []})
    return _JWKS


def _token(event):
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    for h in _env_json("TOKEN_HEADERS", ["authorization", "x-auth-token"]):
        v = headers.get(h.lower())
        if v:
            return v[7:].strip() if v.lower().startswith("bearer ") else v.strip()
    if event.get("authorizationToken"):  # TOKEN-type authorizer event
        v = event["authorizationToken"]
        return v[7:].strip() if v.lower().startswith("bearer ") else v.strip()
    return None


def authenticate(token, now=None):
    """Return verified claims or raise InvalidToken."""
    try:
        _, claims = verify(token, _jwks())
    except InvalidToken as e:
        if str(e) != "unknown key id":
            raise
        _, claims = verify(token, _jwks(refresh=True))
    now = now or time.time()
    if claims.get("exp", 0) < now:
        raise InvalidToken("token expired")
    if claims.get("nbf", 0) > now + 60:
        raise InvalidToken("token not yet valid")
    issuers = [i.rstrip("/") for i in _env_json("ALLOWED_ISSUERS", [])]
    if (claims.get("iss") or "").rstrip("/") not in issuers:
        raise InvalidToken(f"untrusted issuer {claims.get('iss')}")
    if claims.get("token_use") != "access":
        raise InvalidToken("not an access token")
    if claims.get("client_id") not in _env_json("ALLOWED_CLIENT_IDS", []):
        raise InvalidToken("unknown client")
    return claims


def groups_of(claims):
    g = claims.get("cognito:groups") or []
    if isinstance(g, str):
        g = [x for x in g.replace(",", " ").split() if x]
    return list(g)


def handler(event, context):
    token = _token(event)
    if not token:
        raise Exception("Unauthorized")  # API Gateway maps this exact message to 401
    try:
        claims = authenticate(token)
    except InvalidToken as e:
        print(f"rejected token: {e}")
        raise Exception("Unauthorized")
    groups = groups_of(claims)
    perms = permissions_for(groups, _env_json("ROLE_PERMISSIONS", {}), _env_json("BASE_PERMISSIONS", []))
    username = claims.get("username") or claims.get("cognito:username") or claims.get("sub")
    return policy(claims.get("sub", username), event["methodArn"], perms, {
        "username": username, "sub": claims.get("sub", ""),
        "groups": ",".join(groups), "permissions": ",".join(perms),
    })
