# Vendored from climate-product-compare/src/cpc/parallel.py (unchanged except package name).
"""Process-pool map with bounded in-flight work (h5py serializes threads on a global lock).

The executor is created once per worker count and reused: spawning a pool per block costs
far more CPU (each worker imports numpy/h5py/xarray) than the work itself.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import threading
from collections import deque
from concurrent.futures import ProcessPoolExecutor

_POOLS: dict[int, ProcessPoolExecutor] = {}
_ALL: list[ProcessPoolExecutor] = []  # every pool created, including ones replaced after a worker died


def _pool(workers: int) -> ProcessPoolExecutor:
    if workers not in _POOLS:
        from . import http

        if "EARTHDATA_LOGIN_USER" in os.environ and "EARTHDATA_TOKEN" not in os.environ:
            try:
                os.environ["EARTHDATA_TOKEN"] = http.earthdata_token()
            except Exception:
                pass
        ctx = mp.get_context("forkserver")
        # never preload aqc/icechunk here: its runtime threads do not survive fork
        ctx.set_forkserver_preload(["numpy", "h5py", "pandas", "fsspec", "aiohttp"])
        _POOLS[workers] = ProcessPoolExecutor(workers, mp_context=ctx)
        _ALL.append(_POOLS[workers])
    return _POOLS[workers]


def shutdown():
    """Stop every pool without waiting, terminating its (idle) workers.

    concurrent.futures' own exit hook joins each executor's manager thread; a manager whose
    pool was abandoned after a worker died can wait forever for results that never come, which
    hung `cpc update` at exit after all its work was committed. Terminated workers make every
    manager thread exit, so that join returns at once.
    """
    for p in _ALL:
        procs = list((getattr(p, "_processes", None) or {}).values())
        try:
            p.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass
        for proc in procs:
            try:
                proc.terminate()
            except Exception:
                pass
    _ALL.clear()
    _POOLS.clear()


# threading's exit hooks run in reverse registration order: this one runs before
# concurrent.futures.process._python_exit (registered when that module was imported above).
threading._register_atexit(shutdown)


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
        """New pool; resubmit only tasks that did not finish successfully."""
        import sys

        _POOLS.pop(workers, None)
        ex = _pool(workers)
        n = 0
        for entry in q:
            f = entry[1]
            ok = f.done() and not f.cancelled() and f.exception() is None
            if not ok:
                entry[1] = ex.submit(fn, entry[0])
                n += 1
        print(f"process_map: worker died; pool rebuilt, {n} task(s) resubmitted", file=sys.stderr, flush=True)

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
