"""Token service unit tests with a fake Cognito endpoint (urllib patched)."""
import base64
import io
import json
import urllib.error

import pytest

from lambda_harness import call, load


def fake_jwt(claims):
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()  # noqa: E731
    return f"{enc({'alg': 'ES256'})}.{enc(claims)}.sig"


@pytest.fixture()
def svc(monkeypatch):
    monkeypatch.setenv("CLIENT_ID", "c1")
    mod = load("token")
    calls = []

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout=None):
        body = json.loads(req.data)
        calls.append((req.get_header("X-amz-target"), body))
        p = body["AuthParameters"]
        if p.get("PASSWORD") == "bad":
            raise urllib.error.HTTPError(req.full_url, 400, "Bad", {}, io.BytesIO(
                json.dumps({"__type": "NotAuthorizedException", "message": "Incorrect"}).encode()))
        tok = fake_jwt({"username": p.get("USERNAME", "alice"), "cognito:groups": ["tiler"]})
        return Resp(json.dumps({"AuthenticationResult": {"AccessToken": tok, "IdToken": tok, "RefreshToken": "r",
                                                         "ExpiresIn": 3600, "TokenType": "Bearer"}}).encode())

    monkeypatch.setattr(mod.urllib.request, "urlopen", urlopen)
    mod._calls = calls
    return mod


def test_password_login(svc):
    st, _, b = call(svc, "/auth/token", method="POST", body=json.dumps({"username": "alice", "password": "pw"}))
    assert st == 200 and b["groups"] == ["tiler"] and b["username"] == "alice" and b["access_token"]
    target, body = svc._calls[0]
    assert target.endswith("InitiateAuth") and body["AuthFlow"] == "USER_PASSWORD_AUTH" and body["ClientId"] == "c1"


def test_refresh(svc):
    st, _, b = call(svc, "/auth/token", method="POST", body=json.dumps({"refresh_token": "r"}))
    assert st == 200 and svc._calls[0][1]["AuthFlow"] == "REFRESH_TOKEN_AUTH"


def test_bad_password_401(svc):
    st, _, b = call(svc, "/auth/token", method="POST", body=json.dumps({"username": "alice", "password": "bad"}))
    assert st == 401 and b == {"detail": "Incorrect username or password."}


def test_me(svc):
    st, _, b = call(svc, "/auth/me", authorizer={"username": "bob", "sub": "s", "groups": "features",
                                                 "permissions": "auth/me,features"})
    assert st == 200 and b["groups"] == ["features"] and b["permissions"] == ["auth/me", "features"]
