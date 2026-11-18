"""ERA5 single levels from Earthmover's free Icechunk copy (group single/temporal)."""

from __future__ import annotations

import functools

import icechunk
import numpy as np
import pandas as pd
import zarr

from ..physics import K0, rh_from_dewpoint, vpd_kpa
from .base import Block, ChunkedStoreProduct, Grid, Var, bounded_map

G = 9.80665
SOIL_T = [(0, 7), (7, 28), (28, 100), (100, 289)]
SOIL_M = [(0, 7), (7, 28)]  # swvl3/4 are not in the Earthmover copy


def common_vars(t="t2m", d="d2m", tp="tp", sp="sp", u="u10", v="v10", ssrd="ssrd", skt="skt", stl="stl", swvl="swvl",
                n_sm=2, snow="sd", snow_kind="swe") -> dict[str, Var]:
    vs = {
        "tair": Var([t], "temp", "degC", lambda **a: a[t] - K0, {"desc": "2 m temperature (instantaneous)", "height_m": 2}),
        "tdew": Var([d], "temp", "degC", lambda **a: a[d] - K0, {"desc": "2 m dewpoint (instantaneous)"}),
        "rh": Var([t, d], "rh", "%", lambda **a: rh_from_dewpoint(a[t] - K0, a[d] - K0), {"desc": "RH from t2m, d2m"}),
        "vpd": Var([t, d], "vpd", "kPa", lambda **a: vpd_kpa(a[t] - K0, rh_from_dewpoint(a[t] - K0, a[d] - K0)), {}),
        "pr": Var([tp], "precip", "mm", lambda **a: np.maximum(a[tp], 0) * 1000, {"desc": "total precipitation over hour ending at stamp"}),
        "ps": Var([sp], "pres", "Pa", None, {"desc": "surface pressure"}),
        "wind": Var([u, v], "wind", "m s-1", lambda **a: np.hypot(a[u], a[v]), {"desc": "10 m wind speed", "height_m": 10}),
        "sw": Var([ssrd], "rad", "W m-2", lambda **a: np.maximum(a[ssrd], 0) / 3600, {"desc": "surface solar radiation downwards, hour mean"}),
        "tsurf": Var([skt], "temp", "degC", lambda **a: a[skt] - K0, {"desc": "skin temperature (instantaneous)"}),
    }
    for i, (top, bot) in enumerate(SOIL_T, 1):
        vs[f"tsoil{i}"] = Var([f"{stl}{i}"], "temp", "degC", (lambda name: (lambda **a: a[name] - K0))(f"{stl}{i}"),
                              {"desc": f"soil temperature layer {i}", "depth_top_cm": top, "depth_bot_cm": bot})
    for i, (top, bot) in enumerate((SOIL_T)[:n_sm], 1):
        vs[f"soilm{i}"] = Var([f"{swvl}{i}"], "sm", "m3 m-3", None,
                              {"desc": f"volumetric soil water layer {i}", "depth_top_cm": top, "depth_bot_cm": bot})
    if snow_kind == "swe":
        vs["swe"] = Var([snow], "swe", "mm", lambda **a: a[snow] * 1000, {"desc": "snow depth water equivalent"})
    else:
        vs["snowd"] = Var([snow], "snowd", "m", None, {"desc": "snow depth"})
    return vs


class _ERA5Arco(ChunkedStoreProduct):
    name = "era5"
    title = "ERA5"
    freq = "1h"
    start = pd.Timestamp("1940-01-01")
    source = "Earthmover free Icechunk s3://earthmover-icechunk-era5/icechunkV2 (single/temporal)"
    notes = "Final ERA5, quarterly updates. Instantaneous state variables; accumulations over the hour ending at the stamp."
    variables = common_vars()

    @functools.cached_property
    def group(self):
        st = icechunk.s3_storage(bucket="earthmover-icechunk-era5", prefix="icechunkV2", region="us-east-1", anonymous=True)
        s = icechunk.Repository.open(st).readonly_session("main")
        return zarr.open_group(s.store, mode="r", path="single/temporal")

    def grid(self):
        g = self.group
        return Grid(g["latitude"][:], g["longitude"][:], x_periodic=360.0, lon360=True)

    def elevation(self, st):
        z = self.group["z_sfc"]
        iy, ix = st.px_index()
        ok = iy >= 0
        out = np.full(iy.shape, np.nan)
        out[ok] = z.get_coordinate_selection((iy[ok], ix[ok])) / G
        return out

    def arrays(self):
        return {k: self.group[k] for k in ("t2m", "d2m", "tp", "sp", "u10", "v10", "ssrd", "skt", "stl1", "stl2", "stl3", "stl4",
                                           "swvl1", "swvl2", "sd")}

    @functools.cache
    def source_times(self):
        v = self.group["valid_time"][:]
        return pd.Timestamp("1940-01-01") + pd.to_timedelta(v, unit="h")

    def available_end(self):
        return self.source_times()[-1]


# ---- ERA5T fill after the Earthmover copy ends --------------------------------------------
# The free Earthmover copy is updated quarterly. With CDSAPI_KEY set, the months after it are
# filled from the CDS point time-series dataset (ERA5T, ~10 days behind real time), one request
# per stencil pixel. That dataset has only surface variables: soil layers and snow stay missing
# (NaN) in the fill period.
CDS_API = "https://cds.climate.copernicus.eu/api/retrieve/v1"
CDS_TS = "reanalysis-era5-single-levels-timeseries"
TS_VARS = {"t2m": "2m_temperature", "d2m": "2m_dewpoint_temperature", "tp": "total_precipitation",
           "sp": "surface_pressure", "u10": "10m_u_component_of_wind", "v10": "10m_v_component_of_wind",
           "ssrd": "surface_solar_radiation_downwards", "skt": "skin_temperature"}


def _cds_key() -> str | None:
    import os

    return os.environ.get("CDSAPI_KEY")


def cds_timeseries(lat: float, lon: float, d0: pd.Timestamp, d1: pd.Timestamp, variables=tuple(TS_VARS)) -> pd.DataFrame:
    """Hourly ERA5/ERA5T at the grid point nearest (lat, lon), d0..d1 (dates, inclusive).
    Cached under data/cache/era5ts. Columns are the short names (t2m, tp, ...), index valid_time."""
    import io
    import time
    import zipfile

    from .. import config, http

    cache = config.DATA / "cache" / "era5ts"
    cache.mkdir(parents=True, exist_ok=True)
    f = cache / f"{lat:.2f}_{lon:.2f}_{d0:%Y%m%d}_{d1:%Y%m%d}.csv"
    if not f.exists():
        hdr = {"PRIVATE-TOKEN": _cds_key()}
        body = {"inputs": {"variable": [TS_VARS[v] for v in variables], "location": {"latitude": float(lat), "longitude": float(lon)},
                           "date": [f"{d0:%Y-%m-%d}/{d1:%Y-%m-%d}"], "data_format": "csv"}}
        s = http.session()
        r = s.post(f"{CDS_API}/processes/{CDS_TS}/execution", json=body, headers=hdr, timeout=120)
        r.raise_for_status()
        job = r.json()["jobID"]
        for i in range(720):  # up to ~2 h in the queue
            st = s.get(f"{CDS_API}/jobs/{job}", headers=hdr, timeout=60).json()["status"]
            if st == "successful":
                break
            if st in ("failed", "rejected", "dismissed"):
                raise RuntimeError(f"CDS job {job} {st}")
            time.sleep(min(5 + i, 15))
        href = s.get(f"{CDS_API}/jobs/{job}/results", headers=hdr, timeout=60).json()["asset"]["value"]["href"]
        z = zipfile.ZipFile(io.BytesIO(http.get(href, timeout=300).content))
        parts = [pd.read_csv(z.open(n), parse_dates=["valid_time"]).set_index("valid_time").drop(columns=["latitude", "longitude"], errors="ignore")
                 for n in z.namelist() if n.endswith(".csv")]
        df = pd.concat(parts, axis=1)
        df = df.loc[:, ~df.columns.duplicated()]
        tmp = f.with_suffix(".tmp")
        df.to_csv(tmp)
        tmp.rename(f)
    return pd.read_csv(f, parse_dates=["valid_time"], index_col="valid_time")


class _ERA5Fill:
    """Mixin for ERA5: extends available_end and fetch() past the Earthmover copy."""

    @functools.cache
    def arco_end(self) -> pd.Timestamp:
        return self.source_times()[-1]

    @functools.cache
    def cds_end(self) -> pd.Timestamp | None:
        if not _cds_key():
            return None
        today = pd.Timestamp.now().floor("D")
        df = cds_timeseries(40.0, -100.0, today - pd.Timedelta(days=40), today, variables=("t2m",))
        df = df.dropna()
        return df.index.max() if len(df) else None

    def available_end(self):
        end = self.cds_end()
        return max(self.arco_end(), end) if end is not None else self.arco_end()

    def fetch(self, sites, st, t0, t1):
        em = self.arco_end()
        if t0 <= em:
            yield from super().fetch(sites, st, t0, min(t1, em))
        if t1 <= em or self.cds_end() is None:
            return
        f0 = max(t0, em + pd.Timedelta("1h"))
        f1 = min(t1, self.cds_end())
        if f1 < f0:
            return
        tsel = pd.date_range(f0, f1, freq="h")
        lat, lon = self.grid().px_latlon(st)  # (nsite, 4), lon in -180..180
        pts = sorted({(round(float(a), 2), round(float(o), 2)) for a, o in zip(lat.ravel(), lon.ravel()) if np.isfinite(a)})
        d0, d1 = f0.floor("D"), f1.floor("D")
        res = {}
        for p, df in bounded_map(lambda p: (p, cds_timeseries(p[0], p[1], d0, d1)), pts, 4):
            res[p] = df.reindex(tsel)
        for k in range(len(sites)):
            raw = {}
            for v in TS_VARS:
                cols = []
                for j in range(4):
                    p = (round(float(lat[k, j]), 2), round(float(lon[k, j]), 2))
                    cols.append(res[p][v].to_numpy("f8") if p in res and v in res[p] else np.full(len(tsel), np.nan))
                raw[v] = np.stack(cols)
            data = self.convert_all(raw)
            yield Block([sites.site_id.iloc[k]], tsel, {v: a[None] for v, a in data.items()})


class ERA5(_ERA5Fill, _ERA5Arco):
    source = ("Earthmover free Icechunk s3://earthmover-icechunk-era5/icechunkV2 (single/temporal); after it ends, "
              "CDS reanalysis-era5-single-levels-timeseries (ERA5T) at each stencil pixel")
    notes = ("Final ERA5, quarterly updates; the months after the Earthmover copy are preliminary ERA5T from the CDS "
             "point time series (surface variables only: no soil layers or snow there). Instantaneous state "
             "variables; accumulations over the hour ending at the stamp.")
