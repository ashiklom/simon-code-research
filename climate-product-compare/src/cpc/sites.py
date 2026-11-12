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
    """Great-circle distance (km) from each point to the nearest reference point (KD-tree on the unit sphere)."""
    from scipy.spatial import cKDTree

    def xyz(la, lo):
        la, lo = np.radians(np.asarray(la, float)), np.radians(np.asarray(lo, float))
        return np.c_[np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)]

    chord, _ = cKDTree(xyz(ref_lat, ref_lon)).query(xyz(lat, lon))
    return 2 * 6371.0088 * np.arcsin(np.clip(chord / 2, 0, 1))


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


# --- Tier 3: station-remote points -----------------------------------------------------

KG = {1: "Af", 2: "Am", 3: "Aw", 4: "BWh", 5: "BWk", 6: "BSh", 7: "BSk", 8: "Csa", 9: "Csb", 10: "Csc", 11: "Cwa", 12: "Cwb",
      13: "Cwc", 14: "Cfa", 15: "Cfb", 16: "Cfc", 17: "Dsa", 18: "Dsb", 19: "Dsc", 20: "Dsd", 21: "Dwa", 22: "Dwb", 23: "Dwc",
      24: "Dwd", 25: "Dfa", 26: "Dfb", 27: "Dfc", 28: "Dfd", 29: "ET", 30: "EF"}
IGBP = {1: "ENF", 2: "EBF", 3: "DNF", 4: "DBF", 5: "MF", 6: "CSH", 7: "OSH", 8: "WSA", 9: "SAV", 10: "GRA", 11: "WET",
        12: "CRO", 13: "URB", 14: "CVM", 15: "SNO", 16: "BSV"}
LC_GROUP = {"ENF": "forest", "EBF": "forest", "DNF": "forest", "DBF": "forest", "MF": "forest", "CSH": "shrub", "OSH": "shrub",
            "WSA": "savanna", "SAV": "savanna", "GRA": "grass", "WET": "wetland", "CRO": "crop", "CVM": "crop",
            "BSV": "barren", "SNO": "barren", "URB": "urban"}


def _all_station_points() -> pd.DataFrame:
    """Union of station networks that products may use or that we compare against."""
    from .obs import iem, nrcs

    parts = [ghcnd_active()[["lat", "lon"]], load("uscrn")[["lat", "lon"]], load("tier2")[["lat", "lon"]]]
    for net in ("SCAN", "SNOTEL"):
        s = nrcs.station_list(net)
        parts.append(s.rename(columns={"latitude": "lat", "longitude": "lon"})[["lat", "lon"]])
    parts.append(iem.station_list()[["lat", "lon"]])
    return pd.concat(parts, ignore_index=True).dropna()


def build_remote(n: int = 100, seed: int = 42, min_sep_km: float = 75.0) -> pd.DataFrame:
    """Sample `n` CONUS points far from stations, stratified by Koppen-Geiger x IGBP group.

    Candidates: 0.1 deg cells inside the PRISM 4 km land mask (CONUS, US only). Allocation is
    proportional to stratum area (largest-remainder), at least 1 point for strata covering
    >= 0.3 % of CONUS. Within a stratum we greedily take the cell with the largest distance to
    any station or already-chosen point (points >= `min_sep_km` apart where possible).
    """
    import rasterio
    from pyhdf.SD import SD

    from .grid import haversine_km
    from .products import registry

    rng = np.random.default_rng(seed)
    # CONUS land mask from a PRISM grid (4 km), sampled on a 0.1 deg lattice
    prism = registry.get("prism")
    with prism._open("tmax", pd.Timestamp("2020-07-01")) as ds:
        a = ds.read(1)
        tr, nod = ds.transform, ds.nodata
    lats = np.arange(24.55, 49.45, 0.1)
    lons = np.arange(-124.65, -66.95, 0.1)
    LA, LO = np.meshgrid(lats, lons, indexing="ij")
    r = ((LA - tr.f) / tr.e).astype(int)
    c = ((LO - tr.c) / tr.a).astype(int)
    ok = (r >= 0) & (r < a.shape[0]) & (c >= 0) & (c < a.shape[1])
    land = np.zeros_like(ok)
    land[ok] = a[r[ok], c[ok]] != nod
    cand = pd.DataFrame({"lat": LA[land].round(3), "lon": LO[land].round(3)})
    # Koppen-Geiger 1991-2020 (Beck et al. 2023), 1 km
    with rasterio.open(config.CACHE / "koppen" / "1991_2020" / "koppen_geiger_0p00833333.tif") as kg:
        cand["kg"] = [KG.get(int(v[0]), "NA") for v in kg.sample(zip(cand.lon, cand.lat))]
    # MODIS MCD12C1 2020 IGBP majority class (0.05 deg)
    sd = SD(str(config.CACHE / "modis" / "MCD12C1_2020.hdf"))
    lc = sd.select("Majority_Land_Cover_Type_1")[:]
    lr = ((90 - cand.lat) / 0.05).astype(int).clip(0, 3599)
    lcc = ((cand.lon + 180) / 0.05).astype(int).clip(0, 7199)
    cand["igbp"] = [IGBP.get(int(v), "WAT") for v in lc[lr, lcc]]
    cand["lc"] = cand.igbp.map(LC_GROUP).fillna("water")
    cand = cand[(cand.lc != "water") & (cand.lc != "urban") & (cand.kg != "NA")].reset_index(drop=True)
    st = _all_station_points()
    cand["d_station_km"] = nearest_km(cand.lat, cand.lon, st.lat.values, st.lon.values)
    cand["stratum"] = cand.kg + "/" + cand.lc
    share = cand.stratum.value_counts(normalize=True)
    share = share[share >= 0.003]
    alloc = np.floor(share * n).astype(int).clip(lower=1)
    rem = (share * n - np.floor(share * n)).sort_values(ascending=False)
    i = 0
    while alloc.sum() < n:
        alloc[rem.index[i % len(rem)]] += 1
        i += 1
    while alloc.sum() > n:
        alloc[alloc.idxmax()] -= 1
    chosen = []
    plat, plon = np.array([]), np.array([])
    for stratum, k in alloc.sort_values(ascending=False).items():
        sub = cand[cand.stratum == stratum].copy()
        # small random jitter breaks ties reproducibly
        sub["score"] = sub.d_station_km + rng.uniform(0, 0.01, len(sub))
        for _ in range(int(k)):
            d_pts = (np.array([haversine_km(sub.lat.values, sub.lon.values, la, lo) for la, lo in zip(plat, plon)]).min(0)
                     if len(plat) else np.full(len(sub), np.inf))
            ok = d_pts >= min_sep_km
            pool = sub[ok] if ok.any() else sub
            best = pool.score.idxmax()
            row = sub.loc[best]
            chosen.append(row)
            plat, plon = np.append(plat, row.lat), np.append(plon, row.lon)
            sub = sub.drop(best)
    df = pd.DataFrame(chosen).reset_index(drop=True)
    df.insert(0, "site_id", [f"REMOTE:{k:03d}" for k in range(len(df))])
    df.insert(1, "network", "REMOTE")
    df.insert(2, "tier", 3)
    df["name"] = df.stratum + " (" + df.igbp + ")"
    df["state"] = ""
    df["elev_m"] = np.nan
    df["d_station_km"] = df.d_station_km.round(1)
    return df[["site_id", "network", "tier", "name", "state", "lat", "lon", "elev_m", "kg", "igbp", "lc", "stratum", "d_station_km"]]
