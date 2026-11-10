"""Minimal CMR search + authenticated Earthdata HTTPS download (requests only).

Credentials come from EARTHDATA_LOGIN_USER / EARTHDATA_LOGIN_PASSWORD (or
EARTHDATA_USERNAME / EARTHDATA_PASSWORD, as used by earthaccess).
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import requests

CMR = "https://cmr.earthdata.nasa.gov/search/granules.json"
URS = "urs.earthdata.nasa.gov"


def _creds() -> tuple[str, str]:
    user = os.environ.get("EARTHDATA_LOGIN_USER") or os.environ.get("EARTHDATA_USERNAME")
    pw = os.environ.get("EARTHDATA_LOGIN_PASSWORD") or os.environ.get("EARTHDATA_PASSWORD")
    if not (user and pw):
        raise RuntimeError("Set EARTHDATA_LOGIN_USER and EARTHDATA_LOGIN_PASSWORD")
    return user, pw


class EarthdataSession(requests.Session):
    """Keep the Authorization header only when redirected to/from URS."""

    def __init__(self):
        super().__init__()
        self.auth = _creds()

    def rebuild_auth(self, prepared_request, response):
        headers = prepared_request.headers
        url = prepared_request.url
        if "Authorization" in headers:
            orig = requests.utils.urlparse(response.request.url).hostname
            redir = requests.utils.urlparse(url).hostname
            if orig != redir and redir != URS and orig != URS:
                del headers["Authorization"]


def search(short_name: str, version: str | None = None, *, point=None, bbox=None,
           temporal=None, page_size=200, day_night=None) -> list[dict]:
    params = {"short_name": short_name, "page_size": page_size}
    if version:
        params["version"] = version
    if point:
        params["point"] = f"{point[0]},{point[1]}"
    if bbox:
        params["bounding_box"] = ",".join(map(str, bbox))
    if temporal:
        params["temporal"] = f"{temporal[0]},{temporal[1]}"
    if day_night:
        params["day_night_flag"] = day_night
    r = requests.get(CMR, params=params, timeout=120)
    r.raise_for_status()
    return r.json()["feed"]["entry"]


def data_urls(entry: dict, suffixes=(".hdf", ".h5", ".nc")) -> list[str]:
    out = []
    for link in entry.get("links", []):
        href = link["href"]
        if href.startswith("https") and "opendap" not in href and href.endswith(suffixes):
            if link.get("rel", "").endswith("/data#") or href.endswith(suffixes):
                out.append(href)
    return sorted(set(out))


def download(url: str, dest_dir: Path, session: EarthdataSession | None = None,
             retries: int = 4) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / url.rsplit("/", 1)[-1]
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    s = session or EarthdataSession()
    tmp = dest.with_suffix(dest.suffix + ".part")
    for i in range(retries):
        try:
            with s.get(url, stream=True, timeout=300) as r:
                r.raise_for_status()
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 20):
                        f.write(chunk)
            tmp.rename(dest)
            return dest
        except Exception:  # noqa: BLE001
            if i == retries - 1:
                raise
            time.sleep(2 ** (i + 1))
    return dest
