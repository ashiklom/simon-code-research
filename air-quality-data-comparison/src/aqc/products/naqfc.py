"""NOAA National Air Quality Forecast Capability (NAQFC / AQM), CONUS 5 km (NCEP grid 227).

Source: s3://noaa-nws-naqfc-pds (anonymous), ``AQMv{5,6,7}/CS/YYYYMMDD/HH/
aqm.tHHz.ave_1hr_{pm25,o3}[_bc].YYYYMMDD.227.grib2``. Each file holds every forecast hour
(48 h for AQMv5, 72 h for v6/v7) of 1-hour averages; there is no .idx, so the reader fetches a
leading byte range sized for the first 24 messages and walks the GRIB2 section-0 lengths,
decoding with gribberish.

* Versions: AQMv5 (CMAQ) 2020-01-01..2021-07-19, AQMv6 2021-07-20..2024-04-19, AQMv7
  (UFS-AQM) 2024-05-14 onward. 2024-04-20..2024-05-13 is missing from the bucket.
* Continuous series: forecast hours 1-24 of the 12 UTC cycle of each day (valid 13 UTC day D
  .. 12 UTC day D+1); if that cycle is missing, hours 7-30 of the 06 UTC cycle. Hour 1 is the
  first hour the model integrates from its own previous-cycle chemistry; NAQFC assimilates no
  surface PM/O3 observations in the raw product.
* Time: each message is an average over [forecast_date, forecast_date_end]; it is stamped at
  the end (verified with the O3 diurnal phase against GEOS-CF and AQS).
* ``naqfc_bc``: NOAA's bias-corrected PM2.5/O3 (Kalman-filter/analog correction trained on
  AirNow observations), so NOT independent of AirNow/AQS.
"""

from __future__ import annotations

import functools
import struct
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import gribberish
import numpy as np
import pandas as pd
import pyproj

from ..http import session
from .base import FieldProduct, Grid, Var, scale

S3 = "https://noaa-nws-naqfc-pds.s3.amazonaws.com"
VERSIONS = [("AQMv5", pd.Timestamp("2020-01-01"), pd.Timestamp("2021-07-19"), 48),
            ("AQMv6", pd.Timestamp("2021-07-20"), pd.Timestamp("2024-04-19"), 72),
            ("AQMv7", pd.Timestamp("2024-05-14"), pd.Timestamp("2100-01-01"), 72)]


def _version(day: pd.Timestamp):
    for v, a, b, nf in VERSIONS:
        if a <= day <= b:
            return v, nf
    return None, None


def _list(prefix: str, delimiter: str | None = None) -> tuple[list[tuple[str, int]], list[str]]:
    keys, prefixes, token = [], [], None
    while True:
        url = f"{S3}/?list-type=2&prefix={prefix}" + (f"&delimiter={delimiter}" if delimiter else "")
        if token:
            url += f"&continuation-token={token}"
        r = session().get(url, timeout=60)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        ns = {"s": root.tag.split("}")[0].strip("{")}
        for c in root.findall("s:Contents", ns):
            keys.append((c.find("s:Key", ns).text, int(c.find("s:Size", ns).text)))
        prefixes += [e.text for e in root.findall("s:CommonPrefixes/s:Prefix", ns)]
        tok = root.find("s:NextContinuationToken", ns)
        if tok is None:
            return keys, prefixes
        token = tok.text


def _range(url: str, a: int, b: int) -> bytes:
    for attempt in range(5):
        try:
            r = session().get(url, headers={"Range": f"bytes={a}-{b}"}, timeout=180)
            if r.status_code == 404:
                raise FileNotFoundError(url)
            r.raise_for_status()
            return r.content
        except FileNotFoundError:
            raise
        except Exception:
            if attempt == 4:
                raise
    raise RuntimeError("unreachable")


def first_messages(url: str, size: int, n_fcst: int, n_want: int = 30, sample=None) -> list[tuple[pd.Timestamp, pd.Timestamp, np.ndarray, object]]:
    """Decode the leading messages of a multi-message GRIB2 file -> [(start, end, values, metadata)].

    ``sample(flat_values, metadata)`` reduces each decoded field right away (e.g. to the site
    stencil), so only small arrays are kept; consumed bytes are dropped from the buffer.
    """
    est = int(size * min(1.0, (n_want + 1) / n_fcst)) + 1
    buf = _range(url, 0, min(size, est) - 1)
    base = 0  # file offset of buf[0]
    out, off = [], 0  # off: file offset of the next message
    while len(out) < n_want and off < size:
        rel = off - base
        if rel + 16 > len(buf):
            buf += _range(url, base + len(buf), min(size, base + len(buf) + 4_000_000) - 1)
            continue
        if buf[rel:rel + 4] != b"GRIB":
            break
        n = struct.unpack(">Q", buf[rel + 8:rel + 16])[0]
        if rel + n > len(buf):
            buf += _range(url, base + len(buf), min(size, off + n + 2 * n) - 1)
            continue
        m = gribberish.parse_grib_message(buf, rel)
        md = m.metadata
        vals = m.data()
        if sample is not None:
            vals = sample(vals, md)
        out.append((pd.Timestamp(md.forecast_date).tz_convert(None), pd.Timestamp(md.forecast_date_end).tz_convert(None),
                    vals, md))
        del m
        off += n
        buf = buf[rel + n:]
        base = off
    return out


class _NAQFC(FieldProduct):
    freq = "1h"
    start = pd.Timestamp("2020-01-01 13:00")
    suffix = ""
    block_workers = 1
    day_workers = 3
    revision_window = pd.Timedelta(0)

    @property
    def variables(self):
        return {
            "pm25": Var([f"pm25{self.suffix}"], "pm", "ug m-3", attrs={"desc": "surface PM2.5, 1 h mean"}),
            "o3": Var([f"o3{self.suffix}"], "ppb", "ppb", attrs={"desc": "surface O3, 1 h mean"}),
        }

    @functools.cached_property
    def _ref(self):
        """Grid reference from an AQMv7 file (all versions use NCEP grid 227, checked per file)."""
        keys, _ = _list("AQMv7/CS/20250607/12/")
        k, size = next((k, s) for k, s in keys if "ave_1hr_pm25." in k)
        md = first_messages(f"{S3}/{k}", size, 72, n_want=1)[0][3]
        x, y = md.xy()
        return md.proj, np.asarray(y), np.asarray(x), md.grid_shape

    def grid(self) -> Grid:
        proj, y, x, _ = self._ref
        crs = pyproj.CRS.from_proj4(proj)
        fwd = pyproj.Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        inv = pyproj.Transformer.from_crs(crs, "EPSG:4326", always_xy=True)

        def to_yx(lat, lon):
            xx, yy = fwd.transform(lon, lat)
            return yy, xx

        def to_latlon(yy, xx):
            lon, lat = inv.transform(xx, yy)
            return lat, lon

        return Grid(y, x, to_yx=to_yx, to_latlon=to_latlon)

    def available_end(self) -> pd.Timestamp:
        _, pre = _list("AQMv7/CS/", "/")
        days = sorted(p.rstrip("/").rsplit("/", 1)[1] for p in pre)
        for d in reversed(days[-5:]):
            keys, _ = _list(f"AQMv7/CS/{d}/12/")
            if any(f"ave_1hr_pm25{self.suffix}." in k for k, _ in keys) and any(f"ave_1hr_o3{self.suffix}." in k for k, _ in keys):
                return min(pd.Timestamp(d) + pd.Timedelta(hours=36), pd.Timestamp.now().floor("h"))
        raise RuntimeError("no recent AQMv7 12z cycle")

    def blocks(self, t0, t1):
        # day D's 12z cycle covers (D 12:00, D+1 12:00]
        d0 = (pd.Timestamp(t0) - pd.Timedelta(hours=13)).normalize()
        d1 = (pd.Timestamp(t1) - pd.Timedelta(hours=13)).normalize()
        days = pd.date_range(d0, d1, freq="D")
        months = days.to_period("M")
        return [(days[months == p], pd.Timestamp(t0), pd.Timestamp(t1)) for p in months.unique()]

    def _day(self, day: pd.Timestamp, ny: int, nx: int, jy, jx):
        ver, nf = _version(day)
        if ver is None:
            return None
        want = pd.date_range(day + pd.Timedelta(hours=13), periods=24, freq="h")
        for cyc, fh0 in ((12, 1), (6, 7)):
            keys, _ = _list(f"{ver}/CS/{day:%Y%m%d}/{cyc:02d}/")
            sizes = dict(keys)
            res = {}
            for src in (f"pm25{self.suffix}", f"o3{self.suffix}"):
                k = next((k for k in sizes if f"ave_1hr_{src}." in k), None)
                if k is None:
                    break
                def sample(v, md, _k=k):
                    if md.grid_shape != (ny, nx):
                        raise ValueError(f"{_k}: grid {md.grid_shape} != {(ny, nx)}")
                    return np.asarray(v).reshape(ny, nx)[jy, jx].astype("f8")

                msgs = first_messages(f"{S3}/{k}", sizes[k], nf, n_want=fh0 + 23, sample=sample)
                vals = np.full(jy.shape + (24,), np.nan)
                for t_a, t_b, v, md in msgs:
                    if (t_b - t_a) != pd.Timedelta(hours=1) or t_b not in want:
                        continue
                    vals[..., want.get_loc(t_b)] = v
                res[src] = vals
            if len(res) == 2:
                return want, res
        return None

    def read_block(self, key, st):
        days, t0, t1 = key
        _, _, _, (ny, nx) = self._ref
        iy, ix = st.px_index()
        ok = iy >= 0
        jy, jx = np.clip(iy, 0, None), np.clip(ix, 0, None)
        times, parts = [], {f"pm25{self.suffix}": [], f"o3{self.suffix}": []}
        with ThreadPoolExecutor(self.day_workers) as ex:
            for r in ex.map(lambda d: self._day(d, ny, nx, jy, jx), days):
                if r is None:
                    continue
                t, res = r
                times.append(t)
                for s, v in res.items():
                    v[~ok] = np.nan
                    parts[s].append(v)
        if not times:
            raise FileNotFoundError("no NAQFC cycles in block")
        times = times[0].append(times[1:]) if len(times) > 1 else times[0]
        raw = {s: np.concatenate(v, axis=-1) for s, v in parts.items()}
        # O3 in ppm on grid 227 files? convert to ppb if values look like ppm
        o3 = raw[f"o3{self.suffix}"]
        if np.nanmax(o3) < 1.0:
            raw[f"o3{self.suffix}"] = o3 * 1000.0
        return times, raw


class NAQFC(_NAQFC):
    name = "naqfc"
    title = "NOAA NAQFC/AQM (raw)"
    source = "s3://noaa-nws-naqfc-pds AQMv5/v6/v7 CS ave_1hr_{pm25,o3} (12z cycle, f01-f24)"
    notes = ("5 km CONUS (grid 227); CMAQ (v5/v6) then UFS-AQM (v7, 2024-05-14). Forecast hours 1-24 of the "
             "12 UTC cycle joined; no surface observations assimilated.")


class NAQFCbc(_NAQFC):
    name = "naqfc_bc"
    title = "NOAA NAQFC/AQM (bias-corrected)"
    suffix = "_bc"
    source = "s3://noaa-nws-naqfc-pds AQMv5/v6/v7 CS ave_1hr_{pm25,o3}_bc (12z cycle, f01-f24)"
    notes = ("Bias-corrected NAQFC (analog/Kalman correction trained on AirNow observations: not independent "
             "of AQS/AirNow). Forecast hours 1-24 of the 12 UTC cycle joined.")
