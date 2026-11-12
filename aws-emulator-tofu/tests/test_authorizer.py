"""Authorizer unit tests: pure-Python ES256/RS256 verification and role -> policy mapping."""
import base64
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from lambda_harness import load

ISS = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_TEST"
CLIENT = "client123"
ARN = "arn:aws:execute-api:us-east-1:000000000000:abc123/prod/GET/tiler/cog/info"


def b64(n, length=None):
    b = n.to_bytes(length or (n.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


@pytest.fixture(scope="module")
def keys():
    eck = ec.generate_private_key(ec.SECP256R1())
    rsk = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    epub, rpub = eck.public_key().public_numbers(), rsk.public_key().public_numbers()
    jwks = {"keys": [
        {"kid": "ec1", "kty": "EC", "crv": "P-256", "alg": "ES256", "x": b64(epub.x, 32), "y": b64(epub.y, 32)},
        {"kid": "rs1", "kty": "RSA", "alg": "RS256", "n": b64(rpub.n), "e": b64(rpub.e)},
    ]}
    return {"ES256": (eck, "ec1"), "RS256": (rsk, "rs1"), "jwks": jwks}


@pytest.fixture()
def authz(keys, monkeypatch):
    monkeypatch.setenv("JWKS_JSON", json.dumps(keys["jwks"]))
    monkeypatch.delenv("JWKS_URL", raising=False)
    monkeypatch.setenv("ALLOWED_ISSUERS", json.dumps([ISS]))
    monkeypatch.setenv("ALLOWED_CLIENT_IDS", json.dumps([CLIENT]))
    monkeypatch.setenv("ROLE_PERMISSIONS", json.dumps({"tiler": ["tiler"], "features": ["features"], "admin": ["*"]}))
    monkeypatch.setenv("BASE_PERMISSIONS", json.dumps(["auth/me"]))
    mod = load("authorizer")
    mod._JWKS = None
    return mod


def mint(keys, alg="ES256", **over):
    key, kid = keys[alg]
    claims = {"sub": "u-1", "username": "alice", "iss": ISS, "client_id": CLIENT, "token_use": "access",
              "exp": int(time.time()) + 600, "iat": int(time.time()), "cognito:groups": ["tiler"]}
    claims.update(over)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm=alg, headers={"kid": kid})


def run(authz, token, header="Authorization", prefix="Bearer "):
    return authz.handler({"type": "REQUEST", "methodArn": ARN, "headers": {header: prefix + token}}, None)


@pytest.mark.parametrize("alg", ["ES256", "RS256"])
def test_valid_token(authz, keys, alg):
    out = run(authz, mint(keys, alg))
    st = out["policyDocument"]["Statement"][0]
    assert st["Effect"] == "Allow"
    assert set(st["Resource"]) == {
        "arn:aws:execute-api:us-east-1:000000000000:*/*/*/auth/me",
        "arn:aws:execute-api:us-east-1:000000000000:*/*/*/auth/me/*",
        "arn:aws:execute-api:us-east-1:000000000000:*/*/*/tiler",
        "arn:aws:execute-api:us-east-1:000000000000:*/*/*/tiler/*"}
    assert out["context"]["username"] == "alice" and out["context"]["groups"] == "tiler"


def test_x_auth_token_header(authz, keys):
    out = run(authz, mint(keys), header="X-Auth-Token", prefix="")
    assert out["principalId"] == "u-1"


def test_admin_gets_wildcard(authz, keys):
    out = run(authz, mint(keys, **{"cognito:groups": ["admin"]}))
    assert out["policyDocument"]["Statement"][0]["Resource"] == ["arn:aws:execute-api:us-east-1:000000000000:*/*/*/*"]


def test_no_group_only_base(authz, keys):
    out = run(authz, mint(keys, **{"cognito:groups": None}))
    assert out["context"]["permissions"] == "auth/me"


@pytest.mark.parametrize("case", ["tampered", "expired", "issuer", "client", "id_token", "unknown_kid", "alg_none",
                                  "missing", "garbage"])
def test_rejected(authz, keys, case):
    if case == "tampered":
        h, p, s = mint(keys).split(".")
        claims = json.loads(base64.urlsafe_b64decode(p + "=="))
        claims["cognito:groups"] = ["admin"]
        p = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
        tok = f"{h}.{p}.{s}"
    elif case == "expired":
        tok = mint(keys, exp=int(time.time()) - 5)
    elif case == "issuer":
        tok = mint(keys, iss="https://evil.example.com/pool")
    elif case == "client":
        tok = mint(keys, client_id="other")
    elif case == "id_token":
        tok = mint(keys, token_use="id")
    elif case == "unknown_kid":
        other = ec.generate_private_key(ec.SECP256R1())
        tok = jwt.encode({"iss": ISS}, other, algorithm="ES256", headers={"kid": "nope"})
    elif case == "alg_none":
        tok = jwt.encode({"iss": ISS, "client_id": CLIENT, "token_use": "access", "exp": 2**31}, None, algorithm="none")
    elif case == "missing":
        with pytest.raises(Exception, match="Unauthorized"):
            authz.handler({"type": "REQUEST", "methodArn": ARN, "headers": {}}, None)
        return
    else:
        tok = "not.a.jwt"
    with pytest.raises(Exception, match="^Unauthorized$"):
        run(authz, tok)


def test_ecdsa_against_cryptography(keys):
    """Cross-check the pure-Python P-256 verifier against many signatures from `cryptography`."""
    import hashlib
    import sys
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    from lambda_harness import LAMBDAS
    sys.path.insert(0, str(LAMBDAS / "authorizer"))
    import jwt_verify
    sys.path.pop(0)
    key = keys["ES256"][0]
    pub = key.public_key().public_numbers()
    for i in range(20):
        msg = f"message {i}".encode()
        r, s = decode_dss_signature(key.sign(msg, ec.ECDSA(hashes.SHA256())))
        d = hashlib.sha256(msg).digest()
        assert jwt_verify.ecdsa_p256_verify(d, r, s, pub.x, pub.y)
        assert not jwt_verify.ecdsa_p256_verify(d, r, (s + 1) % jwt_verify.N, pub.x, pub.y)
