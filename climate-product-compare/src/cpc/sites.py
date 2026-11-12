"""Site tables. Committed CSVs in results/sites/ are the source of truth once generated."""

from __future__ import annotations

import pandas as pd

from . import config

SITES_DIR = config.RESULTS / "sites"

# Pilot: 12 USCRN stations spanning climates (hot desert, semi-arid, alpine, marine, humid
# subtropical, tropical, continental, subarctic) plus Hawaii.
PILOT = ["TX_Monahans_6_ENE", "AZ_Tucson_11_W", "CO_Boulder_14_W", "WA_Darrington_21_NNE", "FL_Everglades_City_5_NE",
         "ME_Limestone_4_NNW", "GA_Newton_8_W", "NE_Lincoln_11_SW", "ND_Medora_7_E", "CA_Bodega_6_WSW",
         "AK_Fairbanks_11_NE", "HI_Hilo_5_S"]

COLUMNS = ["site_id", "network", "tier", "name", "state", "lat", "lon", "elev_m"]


def build_uscrn() -> pd.DataFrame:
    from .obs import uscrn

    df = uscrn.stations()
    df["pilot"] = df.file_stub.isin(PILOT)
    return df


def save(df: pd.DataFrame, name: str):
    SITES_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(SITES_DIR / f"{name}.csv", index=False)


def load(name: str) -> pd.DataFrame:
    """name: 'pilot' | 'uscrn' | 'tier2' | 'remote' | 'all'"""
    if name == "pilot":
        df = load("uscrn")
        return df[df.pilot].reset_index(drop=True)
    if name == "all":
        parts = [load(n) for n in ("uscrn", "tier2", "remote") if (SITES_DIR / f"{n}.csv").exists()]
        return pd.concat(parts, ignore_index=True)
    return pd.read_csv(SITES_DIR / f"{name}.csv", dtype={"wban": str})
