"""End-to-end role x endpoint x route matrix against the deployed stack -> results/e2e.json.

Routes:
  apigw          API Gateway directly, token in `Authorization: Bearer`
  cf-authz       CloudFront, token in `Authorization: Bearer`   (the correct AWS configuration)
  cf-xauth       CloudFront, token in `X-Auth-Token`            (aws-emulator workaround)
`expected` is what AWS would return for the design; `observed` is what aws-emulator returned.
Also saves sample tiles / feature maps fetched through the stack into figures/.
"""
from __future__ import annotations

import base64
import io
import json
import math
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

import boto3
import requests

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
FIGS = ROOT / "figures"


def tofu_outputs():
    out = subprocess.run(["tofu", "-chdir=infra", "output", "-json"], cwd=ROOT, check=True,
                         capture_output=True, text=True).stdout
    return {k: v["value"] for k, v in json.loads(out).items()}


def xyz(lon, lat, z):
    n = 2 ** z
    lr = math.radians(lat)
    return int((lon + 180) / 360 * n), int((1 - math.log(math.tan(lr) + 1 / math.cos(lr)) / math.pi) / 2 * n)


def b64(d):
    return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()


def main():
    O = tofu_outputs()
    ca = os.environ["AWS_CA_BUNDLE"]
    os.environ["REQUESTS_CA_BUNDLE"] = ca  # requests prefers this env var over Session.verify
    S = requests.Session()
    S.verify = ca
    api, cf = O["api_base_urls"], O["cloudfront_base_url"]
    bucket = O["cogs_bucket"]
    pw = O["user_passwords"]
    groups = O["user_groups"]
    perms = O["role_permissions"]

    # --- callers: tokens minted by the token service (Lambda) -------------------------------
    tokens, mint = {}, {}
    for user in groups:
        t0 = time.time()
        r = S.post(api["auth"] + "/auth/token", json={"username": user, "password": pw[user]})
        mint[user] = {"status": r.status_code, "seconds": round(time.time() - t0, 3)}
        tokens[user] = r.json()["access_token"]
        mint[user]["groups"] = r.json().get("groups")
    # Same user, token minted on the host straight from Cognito (iss = the emulator endpoint).
    cog = boto3.client("cognito-idp")
    ar = cog.initiate_auth(AuthFlow="USER_PASSWORD_AUTH", ClientId=O["client_id"],
                           AuthParameters={"USERNAME": "alice", "PASSWORD": pw["alice"]})["AuthenticationResult"]
    tokens["alice(host-minted)"] = ar["AccessToken"]
    carol_id = S.post(api["auth"] + "/auth/token", json={"username": "carol", "password": pw["carol"]}).json()["id_token"]
    h, p, s = tokens["alice"].split(".")
    claims = json.loads(base64.urlsafe_b64decode(p + "=="))
    tampered = f"{h}.{b64({**claims, 'cognito:groups': ['admin']})}.{s}"
    none_alg = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64({**claims, 'cognito:groups': ['admin']})}."
    bad = {"anonymous": None, "tampered(alice->admin)": tampered, "id-token(carol)": carol_id,
           "alg-none(admin)": none_alg, "garbage": "not-a-jwt"}
    callers = {**{u: tokens[u] for u in groups}, "alice(host-minted)": tokens["alice(host-minted)"], **bad}
    caller_groups = {**{u: groups[u] for u in groups}, "alice(host-minted)": groups["alice"]}

    def allowed(caller, service):
        if caller not in caller_groups:
            return None  # not authenticated
        ps = {"auth/me"} | {p for g in caller_groups[caller] for p in perms.get(g, [])}
        return "*" in ps or service in ps

    tx, ty = xyz(33.46, 16.73, 12)
    url_s2 = f"s3://{bucket}/s2-aswan-tci.tif"
    endpoints = {
        "auth/me": ("auth", "/auth/me", {}, "auth/me"),
        "tiler/info": ("tiler", "/tiler/cog/info", {"url": url_s2}, "tiler"),
        "tiler/tile": ("tiler", f"/tiler/cog/tiles/WebMercatorQuad/12/{tx}/{ty}.png", {"url": url_s2}, "tiler"),
        "features/collections": ("features", "/features/collections", {}, "features"),
        "features/items": ("features", "/features/collections/public.countries/items",
                           {"bbox": "0,40,10,50", "limit": 5}, "features"),
        "reports (future API)": ("reports", "/reports/summary", {}, "reports"),
    }
    routes = {
        "apigw": (lambda svc: api[svc], "Authorization"),
        "cf-authz": (lambda svc: cf, "Authorization"),
        "cf-xauth": (lambda svc: cf, "X-Auth-Token"),
    }

    rows = []
    for route, (base, header) in routes.items():
        for caller, tok in callers.items():
            hdrs = {}
            if tok is not None:
                hdrs[header] = ("Bearer " + tok) if header == "Authorization" else tok
            for ep, (svc, path, params, perm) in endpoints.items():
                ok = allowed(caller, perm)
                expected = 401 if ok is None else (200 if ok else 403)
                t0 = time.time()
                r = S.get(base(svc) + path, params=params, headers=hdrs, timeout=60)
                dt = time.time() - t0
                rows.append({"route": route, "caller": caller, "endpoint": ep, "expected": expected,
                             "observed": r.status_code, "match": expected == r.status_code,
                             "seconds": round(dt, 3), "content_type": r.headers.get("content-type"),
                             "bytes": len(r.content)})
                print(f"{route:9s} {caller:24s} {ep:22s} exp {expected} got {r.status_code} {dt:5.2f}s")

    # Token endpoint behaviours.
    extra = []
    r = S.post(api["auth"] + "/auth/token", json={"username": "alice", "password": "wrong-Password-1!"})
    extra.append({"check": "wrong password -> 401", "observed": r.status_code, "match": r.status_code == 401})
    r = S.post(cf + "/auth/token", json={"username": "bob", "password": pw["bob"]})
    extra.append({"check": "POST /auth/token through CloudFront -> 200", "observed": r.status_code,
                  "match": r.status_code == 200})
    rt = S.post(api["auth"] + "/auth/token", json={"username": "bob", "password": pw["bob"]}).json()["refresh_token"]
    r = S.post(api["auth"] + "/auth/token", json={"refresh_token": rt})
    extra.append({"check": "refresh_token -> new access token", "observed": r.status_code,
                  "match": r.status_code == 200 and bool(r.json().get("access_token"))})
    r = S.get(cf + "/tiler/cog/info", params={"url": url_s2}, headers={"X-Auth-Token": tokens["alice"]})
    extra.append({"check": "CloudFront keeps origin Content-Type (application/json)",
                  "observed": r.headers.get("content-type"), "match": r.headers.get("content-type") == "application/json"})
    r = S.get(api["tiler"] + "/tiler/cog/info", params={"url": f"s3://{bucket}-other/x.tif"},
              headers={"Authorization": "Bearer " + tokens["alice"]})
    extra.append({"check": "tiler refuses buckets outside ALLOWED_BUCKETS -> 403", "observed": r.status_code,
                  "match": r.status_code == 403})
    for e in extra:
        print(e)

    # Latency summary (apigw route, authorized calls).
    lat = {}
    for ep in endpoints:
        xs = [r["seconds"] for r in rows if r["endpoint"] == ep and r["observed"] == 200 and r["route"] == "apigw"]
        if xs:
            lat[ep] = {"n": len(xs), "median_s": round(statistics.median(xs), 3), "max_s": round(max(xs), 3)}
    out = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "emulator": json.loads((RESULTS / "emulator-version.json").read_text()) if (RESULTS / "emulator-version.json").exists() else None,
        "token_minting": mint,
        "rows": rows, "extra_checks": extra, "latency": lat,
        "summary": {route: {"n": sum(r["route"] == route for r in rows),
                            "match": sum(r["match"] for r in rows if r["route"] == route)} for route in routes},
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "e2e.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out["summary"]), json.dumps(lat))
    figures(S, api, cf, bucket, tokens)


def figures(S, api, cf, bucket, tokens):
    """Sample outputs fetched through CloudFront (X-Auth-Token), for the report."""
    from PIL import Image
    FIGS.mkdir(exist_ok=True)

    def mosaic(user, key, z, lon, lat, n, params, name):
        cx, cy = xyz(lon, lat, z)
        im = Image.new("RGBA", (256 * n, 256 * n), (255, 255, 255, 0))
        for j in range(n):
            for i in range(n):
                x, y = cx - n // 2 + i, cy - n // 2 + j
                r = S.get(f"{cf}/tiler/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png",
                          params={"url": f"s3://{bucket}/{key}", **params}, headers={"X-Auth-Token": tokens[user]})
                if r.status_code == 200:
                    im.paste(Image.open(io.BytesIO(r.content)).convert("RGBA"), (256 * i, 256 * j))
        im.save(FIGS / name, optimize=True)

    mosaic("alice", "s2-aswan-tci.tif", 13, 33.46, 16.73, 3, {}, "tiles-s2-aswan.png")
    mosaic("carol", "cop90-alps-dem.tif", 10, 7.5, 46.5, 3, {"rescale": "400,4200", "colormap_name": "terrain"},
           "tiles-dem-alps.png")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7, 5), dpi=150)
    bbox = "-12,34,32,62"
    hdr = {"X-Auth-Token": tokens["bob"]}
    countries = S.get(f"{cf}/features/collections/public.countries/items", params={"bbox": bbox, "limit": 100},
                      headers=hdr).json()
    places = S.get(f"{cf}/features/collections/public.populated_places/items", params={"bbox": bbox, "limit": 200},
                   headers=hdr).json()
    rivers = S.get(f"{cf}/features/collections/public.rivers/items", params={"bbox": bbox, "limit": 100},
                   headers=hdr).json()
    for f in countries["features"]:
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        for poly in polys:
            xs, ys = zip(*poly[0])
            ax.fill(xs, ys, facecolor="#e8e4d8", edgecolor="#8a8170", linewidth=0.5)
    for f in rivers["features"]:
        g = f["geometry"]
        lines = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
        for ln in lines:
            xs, ys = zip(*ln)
            ax.plot(xs, ys, color="#3b7dd8", linewidth=0.8)
    px = [f["geometry"]["coordinates"] for f in places["features"]]
    if px:
        ax.scatter(*zip(*px), s=6, color="#c0392b", zorder=3)
    ax.set_xlim(-12, 32)
    ax.set_ylim(34, 62)
    ax.set_aspect(1.4)
    ax.set_title(f"tipg-lite via CloudFront (user bob, bbox {bbox}): {countries['numberMatched']} countries, "
                 f"{places['numberMatched']} places, {rivers['numberMatched']} rivers", fontsize=8)
    ax.tick_params(labelsize=7)
    fig.tight_layout()
    fig.savefig(FIGS / "features-europe.png")


if __name__ == "__main__":
    sys.exit(main())
