"""Small geodesy helpers (WGS84 / sphere)."""

from __future__ import annotations

import numpy as np

A = 6378137.0
F = 1 / 298.257223563
E2 = F * (2 - F)
R_MEAN = 6371008.8


def lla_to_ecef(lat, lon, h=0.0):
    lat = np.radians(lat)
    lon = np.radians(lon)
    n = A / np.sqrt(1 - E2 * np.sin(lat) ** 2)
    x = (n + h) * np.cos(lat) * np.cos(lon)
    y = (n + h) * np.cos(lat) * np.sin(lon)
    z = (n * (1 - E2) + h) * np.sin(lat)
    return np.stack([x, y, z], axis=-1)


def ecef_to_lla(xyz):
    x, y, z = np.moveaxis(np.asarray(xyz, float), -1, 0)
    lon = np.arctan2(y, x)
    p = np.hypot(x, y)
    lat = np.arctan2(z, p * (1 - E2))
    for _ in range(5):
        n = A / np.sqrt(1 - E2 * np.sin(lat) ** 2)
        h = p / np.cos(lat) - n
        lat = np.arctan2(z, p * (1 - E2 * n / (n + h)))
    return np.degrees(lat), np.degrees(lon), h


def unit_xyz(lat, lon):
    """Unit vectors on the sphere (for KD-trees: chord distance is monotone in arc length)."""
    la = np.radians(lat)
    lo = np.radians(lon)
    c = np.cos(la)
    return np.stack([c * np.cos(lo), c * np.sin(lo), np.sin(la)], axis=-1)


def haversine_m(lat1, lon1, lat2, lon2):
    la1, lo1, la2, lo2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    return 2 * R_MEAN * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def local_aeqd(lat0, lon0):
    """pyproj transformer to a local azimuthal equidistant plane (metres)."""
    from pyproj import Transformer

    return Transformer.from_crs(
        "EPSG:4326", f"+proj=aeqd +lat_0={lat0} +lon_0={lon0} +datum=WGS84 +units=m", always_xy=True
    )


def local_laea(lat0, lon0):
    """pyproj transformer to a local Lambert azimuthal equal-area plane (metres)."""
    from pyproj import Transformer

    return Transformer.from_crs(
        "EPSG:4326", f"+proj=laea +lat_0={lat0} +lon_0={lon0} +datum=WGS84 +units=m", always_xy=True
    )
