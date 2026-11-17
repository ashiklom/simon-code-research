"""Product registry: name -> module:class (imported lazily)."""

from __future__ import annotations

import importlib

PRODUCTS = {
    "haqes": "haqes:HAQES",
    "naqfc": "naqfc:NAQFC",
    "naqfc_bc": "naqfc:NAQFCbc",
    "acag": "acag:ACAG",
    "cams_eac4": "cams:CAMSEAC4",
    "cams_fcst": "cams:CAMSForecast",
    "ghap": "ghap:GHAP",
    "ghap_m": "ghap:GHAPMonthly",
    "hrrr_smoke": "hrrrsmoke:HRRRSmoke",
    "geoscf_v1": "geoscf:GEOSCFv1",
    "geoscf_v2": "geoscf:GEOSCFv2",
    "merra2": "merra2:MERRA2",
    "merra2_cnn": "merra2:MERRA2CNN",
    "merra2_gmi": "merra2gmi:MERRA2GMI",
    # "merra2_gmi_gas": "merra2gmi:MERRA2GMIGas",  # daily-mean lowest-level O3/NO2; ~40 h per pass, not run
    "geosfp_aer": "geosfp:GEOSFPAer",
}


def names() -> list[str]:
    return list(PRODUCTS)


def get(name: str):
    mod, cls = PRODUCTS[name].split(":")
    return getattr(importlib.import_module(f"aqc.products.{mod}"), cls)()
