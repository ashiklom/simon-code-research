"""Daymet V4R1 daily (ORNL DAAC) via Earthdata Cloud OPeNDAP server-side subsetting.

The NetCDF files are chunked (10 days x 300 x 300 km), so client-side range reads would move
~1 TB for our sites; Cloud OPeNDAP reads the chunks in-region and returns only the 2x2 box.
One request per site x variable x year. 365-day calendar (Dec 31 dropped in leap years);
days are local (standard-time) calendar days.
"""

from __future__ import annotations

import functools
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import pyproj

from .. import dap, http
from ..physics import dewpoint_from_vp
from .base import Block, Grid, Product, Var, bounded_map

COLL = "C2532426483-ORNL_CLOUD"
URL = "https://opendap.earthdata.nasa.gov/collections/" + COLL + "/granules/Daymet_Daily_V4R1.daymet_v4_daily_{reg}_{var}_{year}.nc"
PROJ = "+proj=lcc +lat_1=25 +lat_2=60 +lat_0=42.5 +lon_0=-100 +x_0=0 +y_0=0 +ellps=WGS84 +units=m +no_defs"
SRC = ["tmax", "tmin", "prcp", "srad", "vp", "swe", "dayl"]
DAY = {"day_def": "LST"}


class Daymet(Product):
    name = "daymet"
    title = "Daymet V4R1"
    freq = "1d"
    start = pd.Timestamp("1980-01-01")
    source = "ORNL DAAC Daymet_Daily_V4R1 via Earthdata Cloud OPeNDAP (opendap.earthdata.nasa.gov)"
    notes = "1 km daily from GHCN-D stations; 365-day calendar; local-time days. srad converted to 24 h mean."
    site_workers = 2
    request_workers = 8
    variables = {
        "tmax": Var(["tmax"], "temp", "degC", None, {**DAY}),
        "tmin": Var(["tmin"], "temp", "degC", None, {**DAY}),
        "pr": Var(["prcp"], "precip", "mm", None, {**DAY}),
        "sw": Var(["srad", "dayl"], "rad", "W m-2", lambda srad, dayl: srad * dayl / 86400, {**DAY, "desc": "24 h mean shortwave (srad*dayl/86400)"}),
        "vp": Var(["vp"], "vpd", "kPa", lambda vp: vp / 1000, {**DAY, "desc": "daily mean vapour pressure"}),
        "tdew": Var(["vp"], "temp", "degC", lambda vp: dewpoint_from_vp(vp / 1000), {**DAY, "desc": "dewpoint from vp"}),
        "swe": Var(["swe"], "swe", "mm", None, {**DAY}),
    }

    @functools.cached_property
    def regions(self):
        h = http.earthdata_headers()
        out = {}
        for reg in ("na", "hi"):
            u = URL.format(reg=reg, var="tmax", year=2020)
            nt, ny, nx = dap.dds_shape(u, "tmax", headers=h)
            x = dap.ascii_array(u, "x", [(0, nx - 1)], headers=h)
            y = dap.ascii_array(u, "y", [(0, ny - 1)], headers=h)
            out[reg] = (y, x)
        return out

    @functools.cached_property
    def _tf(self):
        return (pyproj.Transformer.from_crs("EPSG:4326", PROJ, always_xy=True),
                pyproj.Transformer.from_crs(PROJ, "EPSG:4326", always_xy=True))

    def _grid(self, reg):
        y, x = self.regions[reg]
        fwd, inv = self._tf

        def to_yx(lat, lon):
            xx, yy = fwd.transform(lon, lat)
            return yy, xx

        def to_latlon(yy, xx):
            lon, lat = inv.transform(xx, yy)
            return lat, lon

        return Grid(y, x, to_yx=to_yx, to_latlon=to_latlon)

    def grid(self):
        """Composite: NA grid, with Hawaii handled by region switching in `fetch`.

        For stencil purposes we return a wrapper that tries NA first then HI."""
        return _MultiGrid({r: self._grid(r) for r in ("na", "hi")})

    def available_end(self):
        r = http.get("https://cmr.earthdata.nasa.gov/search/granules.json", params={
            "collection_concept_id": COLL, "readable_granule_name": "*na_tmax_*", "options[readable_granule_name][pattern]": "true",
            "sort_key": "-start_date", "page_size": 1}).json()
        title = r["feed"]["entry"][0]["title"]
        year = int(title.rsplit("_", 1)[1].split(".")[0])
        return pd.Timestamp(f"{year}-12-30") if year % 4 == 0 else pd.Timestamp(f"{year}-12-31")

    def fetch(self, sites, st, t0, t1):
        g = self.grid()
        g.stencil(sites.lat.values, sites.lon.values)  # sets g.region_of for these sites
        h = http.earthdata_headers()
        years = list(range(t0.year, t1.year + 1))

        def one(k):
            reg = g.region_of[k] if hasattr(g, "region_of") else "na"
            iy, ix = st.iy[k], st.ix[k]
            y0, y1, x0, x1 = iy.min(), iy.max(), ix.min(), ix.max()
            yy, xx = (iy - y0)[[0, 0, 1, 1]], (ix - x0)[[0, 1, 0, 1]]
            tasks = [(v, yr) for v in SRC for yr in years]

            def req(task):
                v, yr = task
                a = dap.ascii_array(URL.format(reg=reg, var=v, year=yr), v, [(0, 364), (y0, y1), (x0, x1)], headers=h)
                a = np.where(a <= -9999, np.nan, a)
                return task, a[:, yy, xx].T  # (4, 365)

            res = {}
            with ThreadPoolExecutor(self.request_workers) as ex:
                for task, a in ex.map(req, tasks):
                    res[task] = a
            times, raw = [], {v: [] for v in SRC}
            for yr in years:
                d = pd.date_range(f"{yr}-01-01", periods=365, freq="D")
                times.append(d)
                for v in SRC:
                    raw[v].append(res[(v, yr)])
            tt = pd.DatetimeIndex(np.concatenate([x.values for x in times]))
            raw = {v: np.concatenate(a, axis=1) for v, a in raw.items()}
            sel = (tt >= t0) & (tt <= t1)
            return k, tt[sel], {v: a[:, sel] for v, a in self.convert_all(raw).items()}

        for k, tt, data in bounded_map(one, range(len(sites)), self.site_workers, ahead=self.site_workers):
            yield Block([sites.site_id.iloc[k]], tt, {v: a[None] for v, a in data.items()})


class _MultiGrid(Grid):
    """Stencil on the first region grid that contains each point (Daymet NA / HI)."""

    def __init__(self, grids: dict):
        self.grids = grids
        self.region_of = None

    def stencil(self, lat, lon):
        from ..grid import Stencil

        lat, lon = np.asarray(lat, "f8"), np.asarray(lon, "f8")
        n = len(lat)
        iy = np.full((n, 2), -1)
        ix = np.full((n, 2), -1)
        w = np.full((n, 4), np.nan)
        reg = np.array(["na"] * n, dtype=object)
        for r, g in self.grids.items():
            s = g.stencil(lat, lon)
            take = s.inside & (iy[:, 0] < 0)
            iy[take], ix[take], w[take] = s.iy[take], s.ix[take], s.w[take]
            reg[take] = r
        self.region_of = list(reg)
        return Stencil(iy, ix, w)

    def px_latlon(self, st):
        lat = np.full(st.w.shape, np.nan)
        lon = np.full(st.w.shape, np.nan)
        for r, g in self.grids.items():
            m = np.array([x == r for x in self.region_of])
            if m.any():
                from ..grid import Stencil

                sub = Stencil(st.iy[m], st.ix[m], st.w[m])
                la, lo = g.px_latlon(sub)
                lat[m], lon[m] = la, lo
        return lat, lon
