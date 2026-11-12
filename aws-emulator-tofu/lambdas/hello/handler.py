"""A stand-in for a *future* API (`/reports/...`) that no role grants yet: only admin ("*") reaches it."""
import re

from apigw import dispatch, response

ROUTES = [("GET", re.compile(r"/reports(?:/.*)?"), lambda req: response(200, {
    "message": "hello from a future API that no role was explicitly granted",
    "path": req.path, "caller": req.authorizer.get("username"),
    "groups": [g for g in (req.authorizer.get("groups") or "").split(",") if g]}))]


def handler(event, context):
    return dispatch(ROUTES, event)
