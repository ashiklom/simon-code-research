"""Network simulator: throttling reverse proxy for S3-API and plain-HTTPS-like access.

    reader --HTTP--> [proxy :port (profile)] --> local files, served either through a minimal
                                                 S3 API (path-style GET/HEAD/ListObjectsV2;
                                                 signatures accepted, not verified) or as plain
                                                 HTTP with Range support

Every request gets, per the profile (config/net_profiles.toml):
  * connection setup cost on the first request of each TCP connection (TCP+TLS handshakes),
  * time-to-first-byte (lognormal: median + sigma; optional extra heavy tail),
  * per-connection bandwidth (sampled per request; optional variability) and a shared
    aggregate bandwidth cap (token bucket),
  * random mid-transfer stalls and 5xx errors (S3: 503 SlowDown; HTTP: 503/502),
  * HTTP profiles: optional redirect emulation (Earthdata TEA/CloudFront -> signed S3 URL:
    the first request for an object returns 307 to a "/signed/..." URL; clients that cache
    the redirect skip it afterwards).

Counters (requests, bytes, redirects, errors) are exposed at GET /__stats (and reset with
?reset=1) so benchmarks can attribute requests/bytes to each reader.

Run as a process:  python -m swathgeo.netsim --profiles s3_in_region,https_earthdata ...
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import time
import tomllib
from pathlib import Path

from aiohttp import web

CHUNK = 64 * 1024


class TokenBucket:
    def __init__(self, rate_bps):
        self.rate = rate_bps
        self.tokens = 0.0
        self.t = time.monotonic()
        self.lock = asyncio.Lock()

    async def take(self, n):
        if not self.rate:
            return
        async with self.lock:
            now = time.monotonic()
            self.tokens = min(self.tokens + (now - self.t) * self.rate, self.rate * 0.05)
            self.t = now
            self.tokens -= n
            if self.tokens < 0:
                await asyncio.sleep(-self.tokens / self.rate)


class Profile:
    def __init__(self, name, cfg):
        self.name = name
        self.kind = cfg["kind"]  # "s3" | "http"
        self.connect_ms = cfg.get("connect_ms", 0.0)
        self.ttfb_median_ms = cfg.get("ttfb_median_ms", 0.0)
        self.ttfb_sigma = cfg.get("ttfb_sigma", 0.0)
        self.tail_prob = cfg.get("tail_prob", 0.0)
        self.tail_ms = cfg.get("tail_ms", [0.0, 0.0])  # uniform extra delay range
        self.bw_mbps = cfg.get("bw_MBps", 0.0)  # per-connection MB/s (0 = unlimited)
        self.bw_sigma = cfg.get("bw_sigma", 0.0)  # lognormal variability of per-request bw
        self.agg_mbps = cfg.get("aggregate_MBps", 0.0)
        self.error_prob = cfg.get("error_prob", 0.0)
        self.stall_prob = cfg.get("stall_prob", 0.0)
        self.stall_ms = cfg.get("stall_ms", [0.0, 0.0])
        self.redirect = cfg.get("redirect", False)
        self.redirect_ms = cfg.get("redirect_ms", 0.0)  # median of the extra (lognormal) redirect hop
        self.redirect_sigma = cfg.get("redirect_sigma", 0.0)
        self.bw_max = cfg.get("bw_max_MBps", 0.0)
        self.max_conn = cfg.get("max_concurrent", 0)
        self.agg = TokenBucket(self.agg_mbps * 1e6) if self.agg_mbps else None
        self.sem = asyncio.Semaphore(self.max_conn) if self.max_conn else None

    def ttfb(self):
        t = self.ttfb_median_ms * random.lognormvariate(0, self.ttfb_sigma) if self.ttfb_sigma else self.ttfb_median_ms
        if self.tail_prob and random.random() < self.tail_prob:
            t += random.uniform(*self.tail_ms)
        return t / 1e3

    def bandwidth(self):
        if not self.bw_mbps:
            return 0.0
        b = self.bw_mbps * (random.lognormvariate(0, self.bw_sigma) if self.bw_sigma else 1.0)
        if self.bw_max:
            b = min(b, self.bw_max)
        return b * 1e6

    def redirect_delay(self):
        r = self.redirect_ms * (random.lognormvariate(0, self.redirect_sigma) if self.redirect_sigma else 1.0)
        return r / 1e3

    def stall(self):
        if self.stall_prob and random.random() < self.stall_prob:
            return random.uniform(*self.stall_ms) / 1e3
        return 0.0


class Stats:
    def __init__(self):
        self.reset()

    def reset(self):
        self.d = {"requests": 0, "bytes": 0, "connections": 0, "redirects": 0, "errors": 0, "heads": 0,
                  "range_gets": 0, "full_gets": 0, "lists": 0, "puts": 0, "stall_s": 0.0, "injected_s": 0.0}


def parse_range(h, size):
    m = re.match(r"bytes=(\d*)-(\d*)$", h or "")
    if not m:
        return 0, size - 1
    a, b = m.groups()
    if a == "":
        n = int(b)
        return max(size - n, 0), size - 1
    a = int(a)
    b = int(b) if b else size - 1
    return a, min(b, size - 1)


def make_app(profile: Profile, files_root: Path):
    stats = Stats()
    seen_conns: set = set()
    signed: set = set()
    async def stats_handler(request):
        out = dict(stats.d)
        if request.query.get("reset"):
            stats.reset()
            seen_conns.clear()
            signed.clear()
        return web.json_response(out)

    async def preamble(request):
        """Connection cost + TTFB; returns injected seconds."""
        inj = 0.0
        conn = id(request.transport)
        if conn not in seen_conns:
            seen_conns.add(conn)
            stats.d["connections"] += 1
            inj += profile.connect_ms / 1e3
        inj += profile.ttfb()
        stats.d["injected_s"] += inj
        await asyncio.sleep(inj)
        return inj

    async def stream_body(resp, chunks):
        bw = profile.bandwidth()
        t0 = time.monotonic()
        sent = 0
        stall_at = random.random()  # a per-request stall happens part-way through the body
        st = profile.stall()
        async for chunk in chunks:
            if st and sent >= stall_at * CHUNK:
                stats.d["stall_s"] += st
                await asyncio.sleep(st)
                t0 += st
                st = 0.0
            if profile.agg:
                await profile.agg.take(len(chunk))
            await resp.write(chunk)
            sent += len(chunk)
            stats.d["bytes"] += len(chunk)
            if bw:
                ahead = sent / bw - (time.monotonic() - t0)
                if ahead > 0.002:
                    await asyncio.sleep(ahead)
        await resp.write_eof()
        return resp

    async def file_chunks(path, a, b):
        with open(path, "rb") as f:
            f.seek(a)
            left = b - a + 1
            while left > 0:
                buf = f.read(min(CHUNK, left))
                if not buf:
                    break
                left -= len(buf)
                yield buf

    async def http_handler(request):
        """Plain HTTP(S)-like file server with Range support and optional redirect."""
        path = request.match_info["path"]
        is_signed = path.startswith("signed/")
        rel = path.removeprefix("signed/")
        fpath = files_root / rel
        if not fpath.is_file():
            return web.Response(status=404)
        if profile.sem:
            await profile.sem.acquire()
        try:
            stats.d["requests"] += 1
            await preamble(request)
            if profile.error_prob and random.random() < profile.error_prob:
                stats.d["errors"] += 1
                return web.Response(status=random.choice([502, 503]), text="Service Unavailable")
            if profile.redirect and not is_signed:
                # TEA: every authenticated GET -> 303 to a fresh pre-signed S3 URL (valid 1 h)
                stats.d["redirects"] += 1
                await asyncio.sleep(profile.redirect_delay())
                now = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
                q = (f"X-Amz-Algorithm=AWS4-HMAC-SHA256&X-Amz-Credential=SIM%2F{now[:8]}%2Fus-west-2%2Fs3%2Faws4_request"
                     f"&X-Amz-Date={now}&X-Amz-Expires=3600&X-Amz-SignedHeaders=host&X-Amz-Signature={random.getrandbits(128):032x}")
                host = request.headers.get("Host", request.host)
                return web.Response(status=303, headers={"Location": f"http://{host}/signed/{rel}?{q}",
                                                         "Cache-Control": "private, max-age=3540"})
            size = fpath.stat().st_size
            hdr = {"Accept-Ranges": "bytes", "Content-Type": "application/octet-stream",
                   "ETag": f'"{int(fpath.stat().st_mtime)}-{size}"',
                   "Last-Modified": time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(fpath.stat().st_mtime))}
            if request.method == "HEAD":
                stats.d["heads"] += 1
                return web.Response(status=200, headers={**hdr, "Content-Length": str(size)})
            rng = request.headers.get("Range")
            a, b = parse_range(rng, size)
            if rng:
                stats.d["range_gets"] += 1
                status = 206
                hdr["Content-Range"] = f"bytes {a}-{b}/{size}"
            else:
                stats.d["full_gets"] += 1
                status = 200
            hdr["Content-Length"] = str(b - a + 1)
            resp = web.StreamResponse(status=status, headers=hdr)
            await resp.prepare(request)
            return await stream_body(resp, file_chunks(fpath, a, b))
        finally:
            if profile.sem:
                profile.sem.release()

    async def s3_handler(request):
        """Minimal S3 REST API over files_root/<key> for bucket BUCKET (path-style)."""
        if profile.sem:
            await profile.sem.acquire()
        try:
            stats.d["requests"] += 1
            path = request.path.lstrip("/")
            bucket, _, key = path.partition("/")
            m = request.method
            listing = m == "GET" and not key
            if m == "HEAD":
                stats.d["heads"] += 1
            elif listing:
                stats.d["lists"] += 1
            elif m == "GET" and "Range" in request.headers:
                stats.d["range_gets"] += 1
            elif m == "GET":
                stats.d["full_gets"] += 1
            await preamble(request)
            if profile.error_prob and random.random() < profile.error_prob:
                stats.d["errors"] += 1
                body = ("<?xml version=\"1.0\" encoding=\"UTF-8\"?><Error><Code>SlowDown</Code>"
                        "<Message>Please reduce your request rate.</Message></Error>")
                return web.Response(status=503, text=body, content_type="application/xml")
            if listing:
                prefix = request.query.get("prefix", "")
                items = []
                for f in sorted(files_root.rglob("*")):
                    if f.is_file():
                        k = str(f.relative_to(files_root))
                        if k.startswith(prefix):
                            st = f.stat()
                            items.append(f"<Contents><Key>{k}</Key><Size>{st.st_size}</Size>"
                                         f"<ETag>\"{int(st.st_mtime)}-{st.st_size}\"</ETag>"
                                         f"<LastModified>{time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime(st.st_mtime))}</LastModified>"
                                         f"<StorageClass>STANDARD</StorageClass></Contents>")
                    if len(items) >= 1000:
                        break
                xml = ('<?xml version="1.0" encoding="UTF-8"?><ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
                       f"<Name>{bucket}</Name><Prefix>{prefix}</Prefix><KeyCount>{len(items)}</KeyCount>"
                       f"<MaxKeys>1000</MaxKeys><IsTruncated>false</IsTruncated>{''.join(items)}</ListBucketResult>")
                return web.Response(text=xml, content_type="application/xml")
            fpath = files_root / key
            if not fpath.is_file():
                body = ("<?xml version=\"1.0\" encoding=\"UTF-8\"?><Error><Code>NoSuchKey</Code>"
                        f"<Message>The specified key does not exist.</Message><Key>{key}</Key></Error>")
                return web.Response(status=404, text=body if m != "HEAD" else None, content_type="application/xml")
            st = fpath.stat()
            size = st.st_size
            hdr = {"Accept-Ranges": "bytes", "Content-Type": "binary/octet-stream",
                   "ETag": f'"{int(st.st_mtime)}-{size}"',
                   "Last-Modified": time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(st.st_mtime))}
            if m == "HEAD":
                return web.Response(status=200, headers={**hdr, "Content-Length": str(size)})
            rng = request.headers.get("Range")
            a, b = parse_range(rng, size)
            status = 206 if rng else 200
            if rng:
                hdr["Content-Range"] = f"bytes {a}-{b}/{size}"
            hdr["Content-Length"] = str(b - a + 1)
            resp = web.StreamResponse(status=status, headers=hdr)
            await resp.prepare(request)
            return await stream_body(resp, file_chunks(fpath, a, b))
        finally:
            if profile.sem:
                profile.sem.release()

    app = web.Application(client_max_size=1024**3)
    app.router.add_get("/__stats", stats_handler)
    if profile.kind == "http":
        app.router.add_route("GET", "/{path:.*}", http_handler)
        app.router.add_route("HEAD", "/{path:.*}", http_handler)
    else:
        app.router.add_route("*", "/{path:.*}", s3_handler)
    return app


def load_profiles(path: Path) -> dict:
    return tomllib.loads(path.read_text())["profile"]


async def serve(profiles: dict, ports: dict, files_root: Path):
    runners = []
    for name, cfg in profiles.items():
        app = make_app(Profile(name, cfg), files_root)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", ports[name], backlog=1024)
        await site.start()
        runners.append(runner)
    print("READY", json.dumps(ports), flush=True)
    while True:
        await asyncio.sleep(3600)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--profiles", required=True)
    ap.add_argument("--base-port", type=int, default=18000)
    ap.add_argument("--files-root", required=True)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    random.seed(a.seed)
    allp = load_profiles(Path(a.config))
    names = a.profiles.split(",")
    profiles = {n: allp[n] for n in names}
    ports = {n: a.base_port + i for i, n in enumerate(names)}
    asyncio.run(serve(profiles, ports, Path(a.files_root)))


if __name__ == "__main__":
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    main()
