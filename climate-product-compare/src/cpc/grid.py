"""2x2 enclosing-stencil computation for regular (1-D coordinate) grids.

Pixel order in the stencil is (y0,x0), (y0,x1), (y1,x0), (y1,x1), where y0/y1 and x0/x1 are
the coordinate indices bracketing the site. Bilinear weights use the fractional position
between the bracketing pixel centres, computed in the grid's own coordinates (degrees or
projected metres). Nearest-neighbour is the stencil pixel with the largest weight.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Stencil:
    iy: np.ndarray  # (nsite, 2) int, -1 if outside
    ix: np.ndarray  # (nsite, 2) int
    w: np.ndarray  # (nsite, 4) bilinear weights (NaN if outside)

    @property
    def inside(self) -> np.ndarray:
        return self.iy[:, 0] >= 0

    def px_index(self) -> tuple[np.ndarray, np.ndarray]:
        """(nsite, 4) y and x indices in stencil pixel order."""
        iy = np.stack([self.iy[:, 0], self.iy[:, 0], self.iy[:, 1], self.iy[:, 1]], axis=1)
        ix = np.stack([self.ix[:, 0], self.ix[:, 1], self.ix[:, 0], self.ix[:, 1]], axis=1)
        return iy, ix


def _bracket(coord: np.ndarray, v: np.ndarray, periodic: float | None = None):
    """Indices (i0, i1) and fraction f in [0,1] of v between coord[i0] and coord[i1].

    coord may be ascending or descending (but regular-ish). If periodic is given (e.g. 360),
    values are wrapped into the coordinate range and the last/first index pair wraps around.
    Returns i0 = -1 where v is outside the coordinate range by more than half a step.
    """
    c = np.asarray(coord, dtype="f8")
    v = np.asarray(v, dtype="f8").copy()
    desc = c[0] > c[-1]
    if desc:
        c = c[::-1]
    n = len(c)
    step = np.median(np.diff(c))
    if periodic is not None:
        v = (v - c[0]) % periodic + c[0]
    j = np.searchsorted(c, v) - 1  # c[j] <= v < c[j+1]
    i0 = np.clip(j, 0, n - 1)
    i1 = i0 + 1
    f = np.empty_like(v)
    if periodic is not None:
        wrap = i1 >= n
        i1 = np.where(wrap, 0, i1)
        c1 = np.where(wrap, c[0] + periodic, c[np.minimum(i1, n - 1)])
        f = (v - c[i0]) / (c1 - c[i0])
        bad = np.zeros_like(v, bool)
    else:
        lo, hi = v < c[0], v >= c[-1]
        i0 = np.where(lo, 0, np.where(hi, n - 2, i0))
        i1 = i0 + 1
        f = np.clip((v - c[i0]) / (c[i1] - c[i0]), 0.0, 1.0)
        bad = (v < c[0] - step / 2) | (v > c[-1] + step / 2)
    if desc:
        i0, i1 = n - 1 - i0, n - 1 - i1
    i0 = np.where(bad, -1, i0)
    i1 = np.where(bad, -1, i1)
    return i0, i1, np.where(bad, np.nan, f)


def regular_stencil(ycoord, xcoord, y, x, *, x_periodic: float | None = None) -> Stencil:
    """Stencil for points (y, x) on a grid with 1-D coordinates ycoord, xcoord."""
    y0, y1, fy = _bracket(ycoord, y)
    x0, x1, fx = _bracket(xcoord, x, periodic=x_periodic)
    bad = (y0 < 0) | (x0 < 0)
    iy = np.stack([y0, y1], 1)
    ix = np.stack([x0, x1], 1)
    iy[bad] = -1
    ix[bad] = -1
    w = np.stack([(1 - fy) * (1 - fx), (1 - fy) * fx, fy * (1 - fx), fy * fx], 1)
    w[bad] = np.nan
    return Stencil(iy.astype("i8"), ix.astype("i8"), w)


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371.0088 * np.arcsin(np.sqrt(a))
