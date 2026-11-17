"""Paths, periods and small shared settings."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]  # air-quality-data-comparison/
DATA = Path(os.environ.get("AQC_DATA", ROOT / "data"))
CACHE = DATA / "cache"
RESULTS = ROOT / "results"

# Analysis periods (PLAN.md, "Comparison windows")
START = pd.Timestamp("2018-01-01")
W_COMMON = (pd.Timestamp("2018-01-01"), pd.Timestamp("2023-12-31 23:59"))
W_RECENT = (pd.Timestamp("2025-08-01"), pd.Timestamp("2026-10-31 23:59"))
W_V1V2 = (pd.Timestamp("2025-08-04"), pd.Timestamp("2026-01-02 23:59"))

DEFAULT_STORE = f"file://{DATA / 'store'}"


def store_url() -> str:
    return os.environ.get("AQC_STORE", DEFAULT_STORE)


for d in (DATA, CACHE):
    d.mkdir(parents=True, exist_ok=True)
