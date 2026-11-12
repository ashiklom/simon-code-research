"""PRISM AN daily 4 km (Oregon State), from the original zipped COGs.

TLS: PRISM's chain ends at "emSign Root CA - G1", which is missing from this environment's
trust bundle. We trust it ONLY for PRISM requests by appending certs/emsign-root-ca-g1.pem
(SHA-256 40:F6:AF:03:46:A9:9A:A1:CD:1D:55:5A:4E:9C:CE:62:C7:F9:63:46:03:EE:40:66:15:83:3D:C8:C8:D0:03:67,
checked against Mozilla's CA bundle) to the default bundle. Verification stays on.

Each 4 km zip (~2.4 MB) is downloaded once into memory and sampled for every site. PRISM days
are the 24 h ending 12 UTC on the label date (day_end_offset_h = 12). Last ~6 months provisional.
"""

from __future__ import annotations

import functools
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

from .. import config, http
from .base import Block, Grid, Product, Var

BASE = "https://data.prism.oregonstate.edu/time_series/us/an/4km"
SRC = ["ppt", "tmax", "tmin", "tmean", "tdmean", "vpdmin", "vpdmax", "soltotal"]
DAY = {"day_end_offset_h": 12}


@functools.cache
def ca_bundle() -> str:
    """Default CA bundle + emSign Root CA - G1, written to a temp file (PRISM requests only)."""
    out = Path(tempfile.gettempdir()) / "cpc-prism-ca-bundle.pem"
    out.write_text(Path(config.CCR_CA_BUNDLE).read_text() + "\n" + (config.CERTS / "emsign-root-ca-g1.pem").read_text())
    return str(out)


def get(url: str, **kw):
    return http.get(url, verify=ca_bundle(), **kw)


class PRISM(Product):
    name = "prism"
    title = "PRISM AN 4 km daily"
    freq = "1d"
    start = pd.Timestamp("1981-01-01")
    revision_window = pd.Timedelta(days=183)
    source = "PRISM Climate Group daily AN 4 km zipped COGs (data.prism.oregonstate.edu)"
    notes = "Station-interpolated (incl. USCRN, GHCN-D, SNOTEL, RAWS, mesonets). Day = 24 h ending 12 UTC. Last 6 months provisional."
    file_workers = 8
    variables = {
        "pr": Var(["ppt"], "precip", "mm", None, {**DAY}),
        "tmax": Var(["tmax"], "temp", "degC", None, {**DAY}),
        "tmin": Var(["tmin"], "temp", "degC", None, {**DAY}),
        "tair": Var(["tmean"], "temp", "degC", None, {**DAY, "desc": "(tmax+tmin)/2"}),
        "tdew": Var(["tdmean"], "temp", "degC", None, {**DAY, "desc": "daily mean dewpoint"}),
        "vpdmin": Var(["vpdmin"], "vpd", "kPa", lambda vpdmin: vpdmin / 10, {**DAY}),
        "vpdmax": Var(["vpdmax"], "vpd", "kPa", lambda vpdmax: vpdmax / 10, {**DAY}),
        "sw": Var(["soltotal"], "rad", "W m-2", lambda soltotal: soltotal * 1e6 / 86400, {**DAY, "desc": "daily total global solar, as 24 h mean"}),
    }

    def url(self, var, d):
        return f"{BASE}/{var}/daily/{d:%Y}/prism_{var}_us_25m_{d:%Y%m%d}.zip"

    @functools.cached_property
    def _grid(self):
        import rasterio

        with self._open("tmax", pd.Timestamp("2020-01-01")) as ds:
            t = ds.transform
            lon = t.c + t.a * (np.arange(ds.width) + 0.5)
            lat = t.f + t.e * (np.arange(ds.height) + 0.5)
        _ = rasterio
        return lat, lon

    def _open(self, var, d):
        from rasterio.io import ZipMemoryFile

        r = get(self.url(var, d), timeout=300)
        mf = ZipMemoryFile(r.content)
        name = Path(self.url(var, d)).name.replace(".zip", ".tif")
        ds = mf.open(name)
        ds._cpc_memfile = mf  # keep alive
        return ds

    def grid(self):
        lat, lon = self._grid
        return Grid(lat, lon)

    def available_end(self):
        y = pd.Timestamp.now().year
        for yy in (y, y - 1):
            r = http.session().get(f"{BASE}/ppt/daily/{yy}/", verify=ca_bundle(), timeout=120)
            days = re.findall(r"prism_ppt_us_25m_(\d{8})\.zip", r.text) if r.ok else []
            if days:
                return pd.Timestamp(max(days))
        raise RuntimeError("no PRISM files found")

    def fetch(self, sites, st, t0, t1):
        iy, ix = st.px_index()

        def read(task):
            var, d = task
            try:
                with self._open(var, d) as ds:
                    a = ds.read(1).astype("f8")
                    nod = ds.nodata
            except Exception as e:  # missing day / transient error after retries
                if "404" in str(e):
                    return task, np.full(iy.shape, np.nan)
                raise
            v = a[iy, ix]
            return task, np.where(v == nod, np.nan, v)

        for m0 in pd.date_range(t0.to_period("M").start_time, t1, freq="MS"):
            days = pd.date_range(max(t0, m0), min(t1, m0 + pd.offsets.MonthEnd(0)), freq="D")
            if len(days) == 0:
                continue
            raw = {v: np.full((len(sites), 4, len(days)), np.nan) for v in SRC}
            with ThreadPoolExecutor(self.file_workers) as ex:
                for (var, d), vals in ex.map(read, [(v, d) for v in SRC for d in days]):
                    raw[var][:, :, days.get_loc(d)] = vals
            yield Block(list(sites.site_id), days, self.convert_all(raw))
