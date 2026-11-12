"""HTTP helpers: a shared requests session with retries/backoff, and Earthdata auth."""

from __future__ import annotations

import functools
import os
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

UA = "climate-product-compare/0.1 (research script)"


@functools.cache
def session(pool: int = 32) -> requests.Session:
    s = requests.Session()
    retry = Retry(total=6, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=("GET", "HEAD", "POST"), respect_retry_after_header=True)
    ad = HTTPAdapter(max_retries=retry, pool_connections=pool, pool_maxsize=pool)
    s.mount("https://", ad)
    s.mount("http://", ad)
    s.headers["User-Agent"] = UA
    return s


def get(url: str, *, timeout: float = 120, **kw) -> requests.Response:
    """GET with retry, raising for HTTP errors."""
    for attempt in range(4):
        try:
            r = session().get(url, timeout=timeout, **kw)
            r.raise_for_status()
            return r
        except (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError):
            if attempt == 3:
                raise
            time.sleep(2 ** (attempt + 1))
    raise RuntimeError("unreachable")


def earthdata_creds() -> tuple[str, str]:
    try:
        return os.environ["EARTHDATA_LOGIN_USER"], os.environ["EARTHDATA_LOGIN_PASSWORD"]
    except KeyError as e:
        raise RuntimeError("set EARTHDATA_LOGIN_USER and EARTHDATA_LOGIN_PASSWORD") from e


@functools.cache
def earthdata_token() -> str:
    """Return an Earthdata Login bearer token (EARTHDATA_TOKEN env, else find/create one)."""
    if tok := os.environ.get("EARTHDATA_TOKEN"):
        return tok
    auth = earthdata_creds()
    r = session().get("https://urs.earthdata.nasa.gov/api/users/tokens", auth=auth, timeout=60)
    r.raise_for_status()
    toks = r.json()
    if toks:
        return toks[0]["access_token"]
    r = session().post("https://urs.earthdata.nasa.gov/api/users/find_or_create_token", auth=auth, timeout=60)
    r.raise_for_status()
    return r.json()["access_token"]


def earthdata_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {earthdata_token()}"}
