"""Humidity / unit helpers. Temperatures in degC, pressure in Pa, RH in %."""

from __future__ import annotations

import numpy as np


def esat_kpa(t_c):
    """Saturation vapour pressure over water (Magnus, Alduchov & Eskridge 1996), kPa."""
    t_c = np.asarray(t_c, dtype="f8")
    return 0.61094 * np.exp(17.625 * t_c / (t_c + 243.04))


def dewpoint_from_rh(t_c, rh):
    rh = np.clip(np.asarray(rh, dtype="f8"), 0.1, 100.0)
    t_c = np.asarray(t_c, dtype="f8")
    g = np.log(rh / 100.0) + 17.625 * t_c / (243.04 + t_c)
    return 243.04 * g / (17.625 - g)


def rh_from_dewpoint(t_c, td_c):
    return np.clip(100.0 * esat_kpa(td_c) / esat_kpa(t_c), 0, 100)


def vpd_kpa(t_c, rh):
    return esat_kpa(t_c) * (1 - np.clip(np.asarray(rh, dtype="f8"), 0, 100) / 100.0)


def vp_from_q(q_kgkg, p_pa):
    """Vapour pressure (kPa) from specific humidity (kg/kg) and pressure (Pa)."""
    q = np.asarray(q_kgkg, dtype="f8")
    return q * np.asarray(p_pa, dtype="f8") / (0.622 + 0.378 * q) / 1000.0


def dewpoint_from_vp(e_kpa):
    e = np.maximum(np.asarray(e_kpa, dtype="f8"), 1e-6)
    g = np.log(e / 0.61094)
    return 243.04 * g / (17.625 - g)


def rh_from_q(t_c, q_kgkg, p_pa):
    return np.clip(100.0 * vp_from_q(q_kgkg, p_pa) / esat_kpa(t_c), 0, 100)


K0 = 273.15
