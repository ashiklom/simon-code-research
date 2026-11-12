"""Process-pool map with bounded in-flight work (h5py serializes threads on a global lock).

The executor is created once per worker count and reused: spawning a pool per block costs
far more CPU (each worker imports numpy/h5py/xarray) than the work itself.
"""

from __future__ import annotations

import atexit
import multiprocessing as mp
import os
from collections import deque
from concurrent.futures import ProcessPoolExecutor

_POOLS: dict[int, ProcessPoolExecutor] = {}


def _pool(workers: int) -> ProcessPoolExecutor:
    if workers not in _POOLS:
        from . import http

        if "EARTHDATA_LOGIN_USER" in os.environ and "EARTHDATA_TOKEN" not in os.environ:
            try:
                os.environ["EARTHDATA_TOKEN"] = http.earthdata_token()
            except Exception:
                pass
        ctx = mp.get_context("forkserver")
        # never preload cpc/icechunk here: its runtime threads do not survive fork
        ctx.set_forkserver_preload(["numpy", "h5py", "pandas", "fsspec", "aiohttp"])
        _POOLS[workers] = ProcessPoolExecutor(workers, mp_context=ctx)
    return _POOLS[workers]


@atexit.register
def _shutdown():
    for p in _POOLS.values():
        p.shutdown(cancel_futures=True)


def process_map(fn, items, workers: int, ahead: int | None = None, timeout: float = 900, retries: int = 2):
    """Ordered results of fn(item) computed in `workers` processes (fn must be picklable).

    A task that produces no result within `timeout` seconds is resubmitted (up to `retries`
    times): a lost task otherwise blocks the whole run while every worker sits idle.
    """
    from concurrent.futures import TimeoutError as FutTimeout

    ahead = ahead or 4 * workers
    ex = _pool(workers)
    q = deque()

    def get(item, fut):
        for attempt in range(retries + 1):
            try:
                return fut.result(timeout=timeout)
            except FutTimeout:
                if attempt == retries:
                    raise
                fut.cancel()
                fut = ex.submit(fn, item)

    for x in items:
        q.append((x, ex.submit(fn, x)))
        if len(q) >= ahead:
            yield get(*q.popleft())
    while q:
        yield get(*q.popleft())
