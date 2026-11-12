"""Process-pool map with bounded in-flight work (h5py serializes threads on a global lock)."""

from __future__ import annotations

import multiprocessing as mp
import os
from collections import deque
from concurrent.futures import ProcessPoolExecutor


def process_map(fn, items, workers: int, ahead: int | None = None):
    """Ordered results of fn(item) computed in `workers` processes (fn must be picklable)."""
    from . import http

    if "EARTHDATA_LOGIN_USER" in os.environ and "EARTHDATA_TOKEN" not in os.environ:
        try:
            os.environ["EARTHDATA_TOKEN"] = http.earthdata_token()
        except Exception:
            pass
    ahead = ahead or 4 * workers
    ctx = mp.get_context("forkserver")
    with ProcessPoolExecutor(workers, mp_context=ctx) as ex:
        q = deque()
        for x in items:
            q.append(ex.submit(fn, x))
            if len(q) >= ahead:
                yield q.popleft().result()
        while q:
            yield q.popleft().result()
