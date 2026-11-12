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


def process_map(fn, items, workers: int, ahead: int | None = None, timeout: float = 900, retries: int = 3):
    """Ordered results of fn(item) computed in `workers` processes (fn must be picklable).

    Robust to (a) lost tasks: no result within `timeout` s -> resubmitted, and (b) workers that
    die (e.g. a hard per-task deadline calls os._exit): the pool is rebuilt and every pending
    task resubmitted. Each item is retried at most `retries` times.
    """
    from concurrent.futures import TimeoutError as FutTimeout
    from concurrent.futures.process import BrokenProcessPool

    ahead = ahead or 4 * workers
    q: deque = deque()  # [item, future, tries]

    def resubmit_all():
        _POOLS.pop(workers, None)
        ex = _pool(workers)
        for entry in q:
            entry[1] = ex.submit(fn, entry[0])

    def get_head():
        while True:
            entry = q[0]
            try:
                res = entry[1].result(timeout=timeout)
                q.popleft()
                return res
            except (FutTimeout, BrokenProcessPool):
                entry[2] += 1
                if entry[2] > retries:
                    raise
                broken = isinstance(entry[1].exception(timeout=0) if entry[1].done() else None, BrokenProcessPool) \
                    or any(f.done() and isinstance(f.exception(), BrokenProcessPool) for _, f, _ in q)
                if broken:
                    try:
                        _POOLS[workers].shutdown(wait=False, cancel_futures=True)
                    except Exception:
                        pass
                    resubmit_all()
                else:
                    entry[1].cancel()
                    entry[1] = _pool(workers).submit(fn, entry[0])

    for x in items:
        q.append([x, _pool(workers).submit(fn, x), 0])
        if len(q) >= ahead:
            yield get_head()
    while q:
        yield get_head()
