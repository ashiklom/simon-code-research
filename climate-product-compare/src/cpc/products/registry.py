"""Product registry: name -> class."""

from __future__ import annotations

import importlib

PRODUCTS = {
    "era5": "era5:ERA5",
    "era5land": "era5land:ERA5Land",
    "merra2": "merra2:MERRA2",
    "nldas2_forcing": "nldas2:NLDAS2Forcing",
    "nldas2_noah": "nldas2:NLDAS2Noah",
    "nldas2_vic": "nldas2:NLDAS2VIC",
    "nldas2_mosaic": "nldas2:NLDAS2Mosaic",
    "geosfp": "geosfp:GEOSFP",
    "hrrr": "dynamical:HRRR",
    "prism": "prism:PRISM",
    "gridmet": "gridmet:GridMET",
    "daymet": "daymet:Daymet",
    "chelsa": "chelsa:CHELSA",
    "chirps3": "dynamical:CHIRPS3",
    "imerg_final_hh": "imerg:IMERGFinalHH",
    "imerg_final_daily": "imerg:IMERGFinalDaily",
    "imerg_late": "dynamical:IMERGLate",
}

_cache = {}


def get(name: str):
    if name not in _cache:
        mod, cls = PRODUCTS[name].split(":")
        m = importlib.import_module(f"cpc.products.{mod}")
        _cache[name] = getattr(m, cls)()
    return _cache[name]


def names() -> list[str]:
    return list(PRODUCTS)
