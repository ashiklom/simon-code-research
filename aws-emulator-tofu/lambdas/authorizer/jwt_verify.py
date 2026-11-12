"""JWT signature verification (ES256 and RS256) in pure Python.

aws-emulator's Cognito signs tokens with ES256 (P-256); AWS Cognito signs with RS256. Supporting
both lets the same authorizer run unchanged on either. No `cryptography`/`jwt` packages: the
emulator's Lambda runtime (RustPython) cannot load native extensions.
"""
import base64
import hashlib
import json

# --- NIST P-256 -------------------------------------------------------------------------------
P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
A = P - 3
B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
G = (0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
     0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5)


def _jdouble(pt):
    if pt is None:
        return None
    x, y, z = pt
    if y == 0:
        return None
    delta = z * z % P
    gamma = y * y % P
    beta = x * gamma % P
    alpha = 3 * (x - delta) * (x + delta) % P
    x3 = (alpha * alpha - 8 * beta) % P
    z3 = ((y + z) ** 2 - gamma - delta) % P
    y3 = (alpha * (4 * beta - x3) - 8 * gamma * gamma) % P
    return (x3, y3, z3)


def _jadd(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1, z1 = p1
    x2, y2, z2 = p2
    z1z1 = z1 * z1 % P
    z2z2 = z2 * z2 % P
    u1 = x1 * z2z2 % P
    u2 = x2 * z1z1 % P
    s1 = y1 * z2 * z2z2 % P
    s2 = y2 * z1 * z1z1 % P
    if u1 == u2:
        return _jdouble(p1) if s1 == s2 else None
    h = (u2 - u1) % P
    i = (2 * h) ** 2 % P
    j = h * i % P
    r = 2 * (s2 - s1) % P
    v = u1 * i % P
    x3 = (r * r - j - 2 * v) % P
    y3 = (r * (v - x3) - 2 * s1 * j) % P
    z3 = ((z1 + z2) ** 2 - z1z1 - z2z2) * h % P
    return (x3, y3, z3)


def _on_curve(x, y):
    return 0 <= x < P and 0 <= y < P and (y * y - (x * x * x + A * x + B)) % P == 0


def ecdsa_p256_verify(digest, r, s, qx, qy):
    if not (1 <= r < N and 1 <= s < N) or not _on_curve(qx, qy):
        return False
    e = int.from_bytes(digest, "big")
    w = pow(s, N - 2, N)
    u1, u2 = e * w % N, r * w % N
    g, q = (G[0], G[1], 1), (qx, qy, 1)
    gq = _jadd(g, q)
    acc = None
    for bit in range(max(u1.bit_length(), u2.bit_length()) - 1, -1, -1):
        acc = _jdouble(acc)
        b1, b2 = (u1 >> bit) & 1, (u2 >> bit) & 1
        if b1 and b2:
            acc = _jadd(acc, gq)
        elif b1:
            acc = _jadd(acc, g)
        elif b2:
            acc = _jadd(acc, q)
    if acc is None:
        return False
    x, _, z = acc
    zinv2 = pow(z * z % P, P - 2, P)
    return (x * zinv2 % P) % N == r


# --- RSA PKCS#1 v1.5 / SHA-256 --------------------------------------------------------------------
SHA256_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


def rsa_sha256_verify(digest, sig, n, e):
    k = (n.bit_length() + 7) // 8
    if len(sig) != k:
        return False
    m = pow(int.from_bytes(sig, "big"), e, n).to_bytes(k, "big")
    t = SHA256_PREFIX + digest
    expected = b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t
    return m == expected


# --- JWT ------------------------------------------------------------------------------------------
class InvalidToken(Exception):
    pass


def b64url(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _int(s):
    return int.from_bytes(b64url(s), "big")


def unverified(token):
    try:
        h, p, _ = token.split(".")
        return json.loads(b64url(h)), json.loads(b64url(p))
    except Exception:  # noqa: BLE001
        raise InvalidToken("malformed token")


def verify(token, jwks):
    """Verify the signature against a JWKS dict; return (header, claims). Claims are NOT checked here."""
    try:
        h64, p64, s64 = token.split(".")
        header = json.loads(b64url(h64))
        claims = json.loads(b64url(p64))
        sig = b64url(s64)
    except Exception:  # noqa: BLE001
        raise InvalidToken("malformed token")
    alg = header.get("alg")
    key = next((k for k in jwks.get("keys", []) if k.get("kid") == header.get("kid")), None)
    if key is None:
        raise InvalidToken("unknown key id")
    digest = hashlib.sha256(f"{h64}.{p64}".encode()).digest()
    if alg == "ES256" and key.get("kty") == "EC" and key.get("crv") == "P-256":
        if len(sig) != 64:
            raise InvalidToken("bad signature length")
        ok = ecdsa_p256_verify(digest, int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big"),
                               _int(key["x"]), _int(key["y"]))
    elif alg == "RS256" and key.get("kty") == "RSA":
        ok = rsa_sha256_verify(digest, sig, _int(key["n"]), _int(key["e"]))
    else:
        raise InvalidToken(f"unsupported alg/key combination {alg}/{key.get('kty')}")
    if not ok:
        raise InvalidToken("bad signature")
    return header, claims
