"""Station-remote points (Tier 4): ~100 land points far from any known monitor.

* Pollution map: ACAG V6.GL.03 annual-mean PM2.5 at 0.1 deg, averaged over 2019-2023 and
  coarsened to 0.5 deg (s3://satpmdata, anonymous). Land from the `global-land-mask` package
  (GLOBE 1 km), excluding coastal cells; 56S-70N.
* Known monitors: every AQS site open after 2017, AirNow's site list (US, Canada, Mexico,
  State Department posts), SPARTAN, Sensor.Community live nodes, and all sites in our tables.
  Government networks outside North America (China, India, Europe, ...) are only partly
  covered until OpenAQ locations can be listed (needs OPENAQ_API_KEY), so "remote" there means
  remote from the monitors we know about.
* Strata: world region (regions.py) x ACAG PM2.5 class (<5, 5-10, 10-25, 25-50, >50 ug m-3).
  Allocation proportional to sqrt(stratum area), at least 1 per stratum with eligible cells.
* Within a stratum, a random eligible cell (>= 100 km from any monitor; fixed seed), keeping
  points >= 300 km apart.
"""

from __future__ import annotations

import io
import zipfile

import numpy as np
import pandas as pd
import xarray as xr

from . import config
from .grid import haversine_km
from .http import get
from .regions import region

ACAG = "https://satpmdata.s3.amazonaws.com/V6GL03/CNNPM25c0p10/Annual/GL/V6GL03.CNNPM25.0p10.GL.{y}01-{y}12.nc"
CLASSES = [0, 5, 10, 25, 50, 1e9]
LABELS = ["<5", "5-10", "10-25", "25-50", ">50"]


def acag_mean(years=range(2019, 2024), coarsen: int = 5) -> xr.DataArray:
    cache = config.CACHE / "remote"
    cache.mkdir(parents=True, exist_ok=True)
    arrs = []
    for y in years:
        p = cache / f"acag_gl_{y}.nc"
        if not p.exists():
            p.write_bytes(get(ACAG.format(y=y), timeout=600).content)
        ds = xr.open_dataset(p)
        v = [k for k in ds.data_vars if ds[k].ndim == 2][0]
        arrs.append(ds[v].load())
    m = xr.concat(arrs, "y").mean("y")
    lat = [d for d in m.dims if "lat" in d.lower()][0]
    lon = [d for d in m.dims if "lon" in d.lower()][0]
    return m.coarsen({lat: coarsen, lon: coarsen}, boundary="trim").mean().rename({lat: "lat", lon: "lon"})


def known_monitors(sites: pd.DataFrame) -> pd.DataFrame:
    from .obs import aqs, embassy, lowcost

    pts = [sites[["lat", "lon"]]]
    m = aqs.read_zip_csv("aqs_sites", usecols=["Latitude", "Longitude", "Site Closed Date"])
    m = m[m["Site Closed Date"].isna() | (pd.to_datetime(m["Site Closed Date"], errors="coerce") >= "2018-01-01")]
    pts.append(m.rename(columns={"Latitude": "lat", "Longitude": "lon"})[["lat", "lon"]])
    # AirNow list (all agencies, not only State Department)
    for k in range(1, 15):
        d = pd.Timestamp.now().normalize() - pd.Timedelta(days=k)
        try:
            r = get(f"{embassy.S3}/airnow/{d:%Y}/{d:%Y%m%d}/Monitoring_Site_Locations_V2.dat")
            an = pd.read_csv(io.StringIO(r.text), sep="|", dtype=str)
            pts.append(pd.DataFrame({"lat": an.Latitude.astype(float), "lon": an.Longitude.astype(float)}))
            break
        except Exception:
            continue
    sc = lowcost.live_nodes()
    pts.append(sc[["lat", "lon"]])
    p = pd.concat(pts).dropna()
    p = p[(p.lat != 0) | (p.lon != 0)]
    return p.round(2).drop_duplicates()


def sample(sites: pd.DataFrame, n: int = 100, min_km: float = 100, spacing_km: float = 300, seed: int = 0,
           log=print) -> pd.DataFrame:
    pm = acag_mean()
    df = pm.to_dataframe(name="pm25").reset_index().dropna()
    df = df[(df.lat >= -56) & (df.lat <= 70)]
    from global_land_mask import globe

    # land at the cell centre and at least 3 of 4 points 0.15 deg away (drops coastal cells)
    land = globe.is_land(df.lat.values, df.lon.values).astype(int)
    for dy, dx in ((0.15, 0), (-0.15, 0), (0, 0.15), (0, -0.15)):
        land = land + globe.is_land(np.clip(df.lat.values + dy, -90, 90), (df.lon.values + dx + 180) % 360 - 180)
    df = df[land >= 4]
    mon = known_monitors(sites)
    log(f"[remote] {len(df)} land cells, {len(mon)} known monitor locations")
    # nearest-monitor distance via a coarse KD-tree on unit vectors
    from scipy.spatial import cKDTree

    def xyz(lat, lon):
        la, lo = np.radians(lat), np.radians(lon)
        return np.c_[np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)]

    tree = cKDTree(xyz(mon.lat.values, mon.lon.values))
    d, _ = tree.query(xyz(df.lat.values, df.lon.values))
    df["dist_km"] = 2 * 6371 * np.arcsin(np.clip(d / 2, 0, 1))
    df["region"] = region(df.lat.values, df.lon.values)
    df["pm_class"] = pd.cut(df.pm25, CLASSES, labels=LABELS, right=False).astype(str)
    df["stratum"] = df.region + " | " + df.pm_class
    elig = df[(df.dist_km >= min_km) & (df.region != "Other")]
    area = df[df.region != "Other"].groupby("stratum").size()
    area = area[area.index.isin(elig.stratum.unique())]
    w = np.sqrt(area)
    alloc = np.maximum(1, np.floor(w / w.sum() * n)).astype(int)
    while alloc.sum() > n:
        alloc[alloc.idxmax()] -= 1
    rng = np.random.default_rng(seed)
    chosen = []
    for s, k in alloc.sort_values().items():
        cand = elig[elig.stratum == s].sample(frac=1, random_state=int(rng.integers(1e9)))
        got = 0
        for r in cand.itertuples():
            if got >= k:
                break
            if all(haversine_km(r.lat, r.lon, c.lat, c.lon) >= spacing_km for c in chosen):
                chosen.append(r)
                got += 1
    c = pd.DataFrame(chosen)
    log(f"[remote] {len(c)} points in {c.stratum.nunique()} strata; median distance to a monitor "
        f"{c.dist_km.median():.0f} km")
    return pd.DataFrame({"site_id": [f"REM:{i:03d}" for i in range(len(c))], "network": "Remote", "tier": 4,
                         "name": c.stratum.values, "lat": c.lat.round(3).values, "lon": c.lon.round(3).values,
                         "elev": np.nan, "country": "", "region": c.region.values, "setting": "remote",
                         "utc_offset": np.nan, "params": "", "note": [f"ACAG 2019-23 mean {p:.1f} ug m-3; "
                                                                      f"{d:.0f} km to nearest known monitor"
                                                                      for p, d in zip(c.pm25, c.dist_km)]})
