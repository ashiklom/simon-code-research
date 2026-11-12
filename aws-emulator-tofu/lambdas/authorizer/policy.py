"""Role -> permission -> IAM policy mapping for the API Gateway Lambda authorizer.

Convention: every API's resources live under `/<service>/...` (e.g. /tiler/..., /features/...),
so a permission is just a service path prefix and is independent of API ids and stages:

    "tiler"   -> arn:aws:execute-api:<region>:<acct>:*/*/*/tiler  and  .../tiler/*
    "auth/me" -> arn:aws:execute-api:<region>:<acct>:*/*/*/auth/me
    "*"       -> arn:aws:execute-api:<region>:<acct>:*/*/*/*        (admin: every current AND future API)

The returned policy lists *everything* the caller may call, not just the current method ARN, so a
cached authorizer result (keyed on the token) stays correct for the caller's other requests.
"""


def permissions_for(groups, role_permissions, base_permissions):
    perms = list(base_permissions)
    for g in groups:
        for p in role_permissions.get(g, []):
            if p not in perms:
                perms.append(p)
    return perms


def resources(method_arn, permissions):
    # method_arn: arn:aws:execute-api:region:account:apiId/stage/VERB/path...
    parts = method_arn.split(":")
    prefix = ":".join(parts[:5])
    out = []
    for p in permissions:
        if p == "*":
            return [f"{prefix}:*/*/*/*"]
        p = p.strip("/")
        out += [f"{prefix}:*/*/*/{p}", f"{prefix}:*/*/*/{p}/*"]
    return out


def policy(principal, method_arn, permissions, context):
    return {
        "principalId": principal,
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [{"Action": "execute-api:Invoke", "Effect": "Allow",
                           "Resource": resources(method_arn, permissions)}],
        },
        "context": context,
    }
