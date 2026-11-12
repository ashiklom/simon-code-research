"""Paths, periods and small shared settings."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]  # climate-product-compare/
DATA = Path(os.environ.get("CPC_DATA", ROOT / "data"))
CACHE = DATA / "cache"
RESULTS = ROOT / "results"
CERTS = ROOT / "certs"

# Analysis periods (see PLAN.md, "Comparison windows")
START = pd.Timestamp("2008-01-01")
W_COMMON = (pd.Timestamp("2018-09-01"), pd.Timestamp("2025-08-31 23:59"))
W_RECENT = (pd.Timestamp("2025-11-01"), pd.Timestamp("2026-10-31 23:59"))

CCR_CA_BUNDLE = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE") or "/root/.ccr/ca-bundle.crt"

DEFAULT_STORE = f"file://{DATA / 'extract.icechunk'}"


def store_url() -> str:
    return os.environ.get("CPC_STORE", DEFAULT_STORE)


for d in (DATA, CACHE):
    d.mkdir(parents=True, exist_ok=True)
