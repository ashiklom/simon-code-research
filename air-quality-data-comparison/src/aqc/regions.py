"""Coarse world regions from lat/lon (for stratified summaries; boxes, not borders)."""

from __future__ import annotations

import numpy as np

# (name, lat0, lat1, lon0, lon1), first match wins
BOXES = [
    ("North America", 14.5, 84, -170, -50),
    ("Latin America", -60, 14.5, -120, -30),
    ("Latin America", 14.5, 33, -120, -86),  # Mexico/Central America west of the Gulf
    ("Europe", 35, 72, -25, 40),
    ("Middle East", 12, 42, 42.5, 63),  # Arabian Peninsula, Iraq, Iran
    ("Africa", -36, 22, -20, 52),
    ("Africa", 22, 37.5, -20, 34.2),  # North Africa incl. Egypt west of Sinai
    ("Middle East", 22, 42, 34.2, 42.5),  # Levant, Sinai, Hejaz
    ("Central Asia", 35, 56, 46, 88),
    ("South Asia", 5, 37, 60, 98),
    ("East Asia", 18, 55, 98, 146),
    ("Southeast Asia", -11, 28.5, 92, 141),
    ("Oceania", -50, -10, 110, 180),
    ("Russia/North", 50, 82, 25, 180),
]


def region(lat, lon) -> np.ndarray:
    lat, lon = np.asarray(lat, float), np.asarray(lon, float)
    out = np.full(lat.shape, "Other", dtype=object)
    done = np.zeros(lat.shape, bool)
    for name, a, b, c, d in BOXES:
        m = ~done & (lat >= a) & (lat < b) & (lon >= c) & (lon < d)
        out[m] = name
        done |= m
    return out
