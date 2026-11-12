"""Common product interface.

Every product module defines a subclass of `Product` with:

* ``name``, ``freq`` ('30min' | '1h' | '1d'), ``start`` (first available time), ``revision_window``
* ``variables``: canonical name -> `Var` (source names, kind, units, converter, attrs)
* ``grid()``: returns a `Grid` (1-D y/x coords + optional projection + elevation getter)
* ``fetch(sites, stencil, t0, t1)``: yields `Block` objects with (site_ids, times, data)
* ``available_end()``: cheap metadata probe of the latest available time

Conventions for what `fetch` returns:
* times are UTC, stamped at the END of the averaging/accumulation interval (instantaneous
  values at their instant); daily products use the date label at 00:00 and describe their
  day window in the variable attrs (``day_end_offset_h`` = hours after the label date's
  00 UTC at which the day ends; or ``day_def='LST'``)
* units: degC, mm (per interval), W m-2 (interval mean), m3 m-3, %, kPa, Pa, m s-1, mm SWE, m
* data arrays have shape (nsite, 4, ntime) in stencil pixel order
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..grid import Stencil, haversine_km, regular_stencil
from ..store import VarSpec


@dataclass
class Var:
    src: list[str]
    kind: str
    units: str
    convert: Callable[..., np.ndarray] | None = None  # convert(**{src: array}) -> array
    attrs: dict = field(default_factory=dict)

    def apply(self, arrays: dict[str, np.ndarray]) -> np.ndarray:
        if self.convert is None:
            return np.asarray(arrays[self.src[0]], dtype="f8")
        return self.convert(**{k: np.asarray(arrays[k], dtype="f8") for k in self.src})

    def spec(self, name: str) -> VarSpec:
        return VarSpec(name, self.kind, self.units, dict(self.attrs))


@dataclass
class Grid:
    y: np.ndarray
    x: np.ndarray
    x_periodic: float | None = None
    to_yx: Callable[[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]] | None = None  # (lat, lon) -> (y, x)
    to_latlon: Callable[[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]] | None = None  # (y, x) -> (lat, lon)
    lon360: bool = False  # x is longitude in 0..360

    def stencil(self, lat, lon) -> Stencil:
        lat, lon = np.asarray(lat, "f8"), np.asarray(lon, "f8")
        if self.to_yx is not None:
            yy, xx = self.to_yx(lat, lon)
        else:
            yy, xx = lat, (lon % 360 if self.lon360 else lon)
        return regular_stencil(self.y, self.x, yy, xx, x_periodic=self.x_periodic)

    def px_latlon(self, st: Stencil) -> tuple[np.ndarray, np.ndarray]:
        iy, ix = st.px_index()
        ok = iy >= 0
        yv = np.where(ok, self.y[np.clip(iy, 0, None)], np.nan)
        xv = np.where(ok, self.x[np.clip(ix, 0, None)], np.nan)
        if self.to_latlon is not None:
            lat, lon = self.to_latlon(yv, xv)
        else:
            lat, lon = yv, xv
        lon = np.where(lon > 180, lon - 360, lon)
        return lat, lon


@dataclass
class Block:
    site_ids: list[str]
    times: pd.DatetimeIndex
    data: dict[str, np.ndarray]  # canonical var -> (nsite, 4, ntime)


class Product:
    name: str = ""
    title: str = ""
    freq: str = "1h"
    start: pd.Timestamp = pd.Timestamp("1980-01-01")
    revision_window: pd.Timedelta = pd.Timedelta(0)
    variables: dict[str, Var] = {}
    source: str = ""  # human-readable access path (shown on the site)
    notes: str = ""
    site_workers: int = 8  # parallel per-site reads for chunked stores

    def grid(self) -> Grid:
        raise NotImplementedError

    def elevation(self, st: Stencil) -> np.ndarray | None:
        return None

    def available_end(self) -> pd.Timestamp:
        raise NotImplementedError

    def fetch(self, sites: pd.DataFrame, st: Stencil, t0: pd.Timestamp, t1: pd.Timestamp) -> Iterator[Block]:
        raise NotImplementedError

    # ---- helpers
    def meta(self) -> dict:
        return {"product": self.name, "title": self.title, "source": self.source, "notes": self.notes,
                "freq": self.freq, "start": str(self.start)}

    def specs(self) -> dict[str, VarSpec]:
        return {k: v.spec(k) for k, v in self.variables.items()}

    def convert_all(self, raw: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        out = {}
        for k, v in self.variables.items():
            if all(s in raw for s in v.src):
                out[k] = v.apply(raw).astype("f4")
        return out


def px_distance_km(site_lat, site_lon, px_lat, px_lon):
    return haversine_km(np.asarray(site_lat)[:, None], np.asarray(site_lon)[:, None], px_lat, px_lon)


class ChunkedStoreProduct(Product):
    """Product backed by a time-series-chunked Zarr/Icechunk store: one box read per site.

    Subclasses implement ``arrays()`` -> dict src name -> zarr.Array with dims (time, y, x)
    (or a callable taking (it0, it1, iy, ix) for unusual layouts) and ``source_times()`` ->
    DatetimeIndex of the stored time axis already shifted to end-of-interval stamps.
    """

    def arrays(self) -> dict:
        raise NotImplementedError

    def source_times(self) -> pd.DatetimeIndex:
        raise NotImplementedError

    def read_box(self, arr, it0: int, it1: int, iy: np.ndarray, ix: np.ndarray) -> np.ndarray:
        """(nt, 2, 2) -> (4, nt) in stencil pixel order."""
        if callable(arr) and not hasattr(arr, "get_orthogonal_selection"):
            x = arr(it0, it1, iy, ix)
        else:
            x = arr.get_orthogonal_selection((slice(it0, it1), iy, ix))
        return np.asarray(x, dtype="f8").reshape(x.shape[0], 4).T

    def fetch(self, sites, st, t0, t1):
        times = self.source_times()
        it0 = int(times.searchsorted(t0))
        it1 = int(times.searchsorted(t1, side="right"))
        if it1 <= it0:
            return
        tsel = times[it0:it1]
        arrays = self.arrays()
        needed = sorted({s for v in self.variables.values() for s in v.src})

        def one(k):
            iy, ix = st.iy[k], st.ix[k]
            raw = {s: self.read_box(arrays[s], it0, it1, iy, ix) for s in needed if s in arrays}
            return k, self.convert_all(raw)

        for k, data in bounded_map(one, range(len(sites)), self.site_workers):
            yield Block([sites.site_id.iloc[k]], tsel, {v: a[None] for v, a in data.items()})


def bounded_map(fn, items, workers: int, ahead: int | None = None):
    """Like ThreadPoolExecutor.map, but keeps at most `ahead` results in flight (bounded memory)."""
    from collections import deque
    from concurrent.futures import ThreadPoolExecutor

    ahead = ahead or 2 * workers
    it = iter(items)
    with ThreadPoolExecutor(workers) as ex:
        q = deque()
        for x in it:
            q.append(ex.submit(fn, x))
            if len(q) >= ahead:
                yield q.popleft().result()
        while q:
            yield q.popleft().result()
