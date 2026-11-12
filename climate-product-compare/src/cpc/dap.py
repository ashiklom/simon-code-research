"""Minimal thread-safe OPeNDAP (DAP2) helpers using the ASCII response.

netCDF4-python's DAP client is not thread-safe, so for many small box reads we request
``<url>.ascii?var[a:b][c:d]...`` with requests and parse the numbers.
"""

from __future__ import annotations

import re

import numpy as np

from . import http

_HDR = re.compile(r"^\s*(\w+(?:\.\w+)?)((?:\[\d+\])+)\s*$")


def constraint(var: str, slices: list[tuple[int, int]]) -> str:
    """slices: inclusive (start, stop) pairs."""
    return var + "".join(f"[{a}:1:{b}]" for a, b in slices)


def ascii_array(url: str, var: str, slices: list[tuple[int, int]], *, headers=None, timeout=300) -> np.ndarray:
    """Fetch var[slices] (inclusive) via DAP2 ASCII and return a float64 array (raw, unscaled)."""
    import time

    import requests

    for attempt in range(6):
        try:
            r = http.get(f"{url}.ascii?{constraint(var, slices)}", headers=headers or {}, timeout=timeout)
            return parse_ascii(r.text, var, [b - a + 1 for a, b in slices])
        except requests.HTTPError as e:
            # Earthdata Cloud OPeNDAP returns sporadic 401/403 under load: back off and retry
            code = e.response.status_code if e.response is not None else 0
            if code not in (401, 403, 429) or attempt == 5:
                raise
            time.sleep(5 * 2 ** attempt)
    raise RuntimeError("unreachable")


def parse_ascii(text: str, var: str, shape: list[int]) -> np.ndarray:
    lines = text.splitlines()
    # locate the array header "<var>.<var>[n][m]..." or "<var>[n][m]..."
    start = None
    for i, ln in enumerate(lines):
        m = _HDR.match(ln)
        if m and m.group(1).split(".")[-1] == var.split(".")[-1]:
            start = i + 1
            break
    if start is None:
        # Hyrax style: "var[i][j], v1, v2, ..." rows
        pre = re.compile(rf"^{re.escape(var.split('.')[-1])}(?:\[\d+\])*,")
        rows = [ln.split(",", 1)[1] for ln in lines if pre.match(ln)]
        if rows:
            vals = [float(x) for r in rows for x in r.split(",") if x.strip()]
            a = np.asarray(vals, dtype="f8")
            n_expected = int(np.prod(shape))
            if a.size != n_expected:
                raise ValueError(f"DAP ascii: expected {n_expected} values for {var}, got {a.size}")
            return a.reshape(shape)
        raise ValueError(f"DAP ascii: array {var} not found in response: {text[:300]!r}")
    vals = []
    n_expected = int(np.prod(shape))
    for ln in lines[start:]:
        if not ln.strip():
            if vals:
                break
            continue
        if ln.startswith("["):
            parts = ln.split(",")[1:]
        else:
            parts = ln.split(",")
        vals.extend(float(p) for p in parts if p.strip())
        if len(vals) >= n_expected:
            break
    a = np.asarray(vals[:n_expected], dtype="f8")
    if a.size != n_expected:
        raise ValueError(f"DAP ascii: expected {n_expected} values for {var}, got {a.size}")
    return a.reshape(shape)


def dds_shape(url: str, var: str, headers=None) -> list[int]:
    txt = http.get(f"{url}.dds", headers=headers or {}).text
    m = re.search(rf"\b{re.escape(var)}((?:\[\s*\w+\s*=\s*\d+\s*\])+)\s*;", txt)
    if not m:
        raise ValueError(f"{var} not in DDS of {url}")
    return [int(x) for x in re.findall(r"=\s*(\d+)", m.group(1))]
