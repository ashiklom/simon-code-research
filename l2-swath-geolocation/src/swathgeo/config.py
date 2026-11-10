"""Paths and config loading."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"
DATA = ROOT / "data"
RAW = DATA / "raw"
RESULTS = ROOT / "results"
FIGURES = ROOT / "figures"
SUBDIR = {"modis": "modis", "viirs": "viirs", "ecostress": "ecostress"}


def load_toml(name: str) -> dict:
    with open(CONFIG / name, "rb") as f:
        return tomllib.load(f)


def local_path(url: str, sensor: str, sub: str | None = None) -> Path:
    return RAW / (sub or SUBDIR[sensor]) / url.rsplit("/", 1)[-1]


def scenes() -> dict:
    return load_toml("granules.toml")["scenes"]


def scene_paths(name: str) -> dict:
    sc = scenes()[name]
    out = {"sensor": sc["sensor"]}
    for k in ("geo", "l2", "att"):
        if k in sc:
            out[k] = [local_path(u, sc["sensor"]) for u in sc[k]]
    return out
