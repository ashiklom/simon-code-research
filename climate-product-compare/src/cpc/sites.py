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


# --- reference station lists (for independence / remoteness) -------------------------


def ghcnd_active(since: int = 2008) -> pd.DataFrame:
    """GHCN-Daily US stations reporting TMAX/TMIN/PRCP in or after `since`."""
    import io

    from . import http

    cache = config.CACHE / "ghcnd"
    cache.mkdir(parents=True, exist_ok=True)
    for f in ("ghcnd-stations.txt", "ghcnd-inventory.txt"):
        if not (cache / f).exists():
            (cache / f).write_bytes(http.get(f"https://www.ncei.noaa.gov/pub/data/ghcn/daily/{f}", timeout=600).content)
    st = pd.read_fwf(cache / "ghcnd-stations.txt", colspecs=[(0, 11), (12, 20), (21, 30), (31, 37), (38, 40), (41, 71)],
                     names=["id", "lat", "lon", "elev", "state", "name"])
    inv = pd.read_fwf(cache / "ghcnd-inventory.txt", colspecs=[(0, 11), (31, 35), (36, 40), (41, 45)],
                      names=["id", "el", "first", "last"])
    inv = inv[inv.el.isin(["TMAX", "TMIN", "PRCP"]) & (inv["last"] >= since)]
    st = st[st.id.isin(inv.id) & st.id.str.startswith("US")]
    _ = io
    return st.reset_index(drop=True)


def nearest_km(lat, lon, ref_lat, ref_lon) -> np.ndarray:
    """Distance (km) from each point to the nearest reference point (haversine via BallTree-free chunks)."""
    from .grid import haversine_km

    lat, lon = np.asarray(lat, float), np.asarray(lon, float)
    out = np.empty(len(lat))
    for i in range(len(lat)):
        out[i] = haversine_km(lat[i], lon[i], ref_lat, ref_lon).min()
    return out


def farthest_point(df: pd.DataFrame, k: int, seed_idx: int = 0) -> pd.DataFrame:
    """Greedy farthest-point subset of size k (spatial spread)."""
    from .grid import haversine_km

    lat, lon = df.lat.values, df.lon.values
    chosen = [seed_idx]
    d = haversine_km(lat[seed_idx], lon[seed_idx], lat, lon)
    while len(chosen) < min(k, len(df)):
        i = int(np.argmax(d))
        chosen.append(i)
        d = np.minimum(d, haversine_km(lat[i], lon[i], lat, lon))
    return df.iloc[chosen]


def build_tier2() -> pd.DataFrame:
    """Independent / high-quality non-USCRN sites (see PLAN.md, Tier 2)."""
    from .obs import ameriflux, iem, neon, nrcs, surfrad

    ghcn = ghcnd_active()
    us = load("uscrn")
    parts = [surfrad.stations(), neon.stations(), ameriflux.stations()]

    # SCAN: long records (begin <= 2009), >1 km from any GHCN-D/USCRN station, spread out
    scan = nrcs.station_list("SCAN")
    conus = scan.latitude.between(24, 50) & scan.longitude.between(-125, -66)
    scan = scan[(scan.begin <= "2009-01-01") & conus]
    scan = scan.rename(columns={"latitude": "lat", "longitude": "lon"}).reset_index(drop=True)
    scan["d_ghcn"] = nearest_km(scan.lat, scan.lon, ghcn.lat.values, ghcn.lon.values)
    scan["d_uscrn"] = nearest_km(scan.lat, scan.lon, us.lat.values, us.lon.values)
    scan = scan[(scan.d_ghcn > 1) & (scan.d_uscrn > 1)].reset_index(drop=True)
    scan = farthest_point(scan, 8)
    parts.append(pd.DataFrame({"site_id": "SCAN:" + scan.stationId, "network": "SCAN", "tier": 2, "name": scan.name,
                               "state": scan.stateCode, "lat": scan.lat, "lon": scan.lon, "elev_m": scan.elevation * 0.3048,
                               "triplet": scan.stationTriplet, "tz": scan.dataTimeZone,
                               "independence": "SCAN: not in GHCN-D; in MADIS (HRRR) and possibly PRISM; soil moisture not assimilated by any product."}))
    # SNOTEL: snow reference (in GHCN-D, so dependent for PRISM/Daymet T and P)
    sn = nrcs.station_list("SNOTEL")
    sn = sn[(sn.begin <= "2005-01-01") & ~sn.stateCode.isin(["AK"])].rename(columns={"latitude": "lat", "longitude": "lon"}).reset_index(drop=True)
    sn = farthest_point(sn, 6)
    parts.append(pd.DataFrame({"site_id": "SNOTEL:" + sn.stationId, "network": "SNOTEL", "tier": 2, "name": sn.name,
                               "state": sn.stateCode, "lat": sn.lat, "lon": sn.lon, "elev_m": sn.elevation * 0.3048,
                               "triplet": sn.stationTriplet, "tz": sn.dataTimeZone,
                               "independence": "SNOTEL: in GHCN-D and MADIS (dependent for PRISM/Daymet/HRRR T,P); used here for SWE/snow depth."}))
    # ISUSM: 4 long-record Iowa sites
    isu = iem.station_list()
    isu = isu[pd.to_datetime(isu.archive_begin) <= "2015-01-01"].reset_index(drop=True)
    isu["d_ghcn"] = nearest_km(isu.lat, isu.lon, ghcn.lat.values, ghcn.lon.values)
    isu = farthest_point(isu[isu.d_ghcn > 1].reset_index(drop=True), 4)
    parts.append(pd.DataFrame({"site_id": "ISUSM:" + isu.sid, "network": "ISUSM", "tier": 2, "name": isu.sname, "state": "IA",
                               "lat": isu.lat, "lon": isu.lon, "elev_m": isu.elevation, "code": isu.sid,
                               "independence": "ISUSM: not in GHCN-D; in MADIS (HRRR)."}))
    df = pd.concat(parts, ignore_index=True)
    df["d_ghcn_km"] = nearest_km(df.lat, df.lon, ghcn.lat.values, ghcn.lon.values).round(1)
    df["d_uscrn_km"] = nearest_km(df.lat, df.lon, us.lat.values, us.lon.values).round(1)
    return df


import numpy as np  # noqa: E402
