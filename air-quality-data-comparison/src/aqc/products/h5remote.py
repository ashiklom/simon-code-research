"""Fast remote reads of chunked netCDF4/HDF5 variables over HTTPS.

h5py reading through fsspec issues one small range request per chunk, sequentially (88 s for
one MERRA-2 aerosol variable-day). Here the chunk index is read once with h5py, the byte
spans of the requested variables are merged into a few large range requests made in
parallel, and chunks are decoded locally (deflate, optional byte shuffle). Only the chunk
filters used by GES DISC / NCCS netCDF4 files are supported (shuffle + deflate).
"""

from __future__ import annotations

import zlib
from concurrent.futures import ThreadPoolExecutor

import fsspec
import h5py
import numpy as np

from .. import http

SHUFFLE, DEFLATE = 2, 1


def _unshuffle(buf: bytes, itemsize: int) -> bytes:
    a = np.frombuffer(buf, dtype="u1")
    n = a.size // itemsize
    return a[: n * itemsize].reshape(itemsize, n).T.tobytes()


def _get(url: str, start: int, end: int, headers: dict | None = None) -> bytes:
    h = {"Range": f"bytes={start}-{end - 1}", **(headers or {})}
    for attempt in range(5):
        try:
            r = http.session().get(url, headers=h, timeout=300)
            r.raise_for_status()
            if len(r.content) != end - start:
                raise OSError(f"short read {len(r.content)} != {end - start}")
            return r.content
        except Exception:
            if attempt == 4:
                raise
            import time
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("unreachable")


def read_vars(url: str, names: list[str], *, headers: dict | None = None, workers: int = 8,
              max_gap: int = 1 << 16, missing_ok: bool = False, level: tuple[int, int] | None = None,
              file_kwargs: dict | None = None) -> dict[str, np.ndarray]:
    """Full arrays (float32) of `names` from a remote netCDF4/HDF5 file (fill/missing values -> NaN).

    level=(axis, index) reads only the chunks at that index along `axis` (chunk size 1 there,
    e.g. the lowest model level of a 3-D field); that axis is kept with length 1.
    """
    f = fsspec.open(url, block_size=2**21, cache_type="blockcache",
                    client_kwargs={"headers": headers} if headers else {}).open()
    meta = {}
    with h5py.File(f, "r") as h:
        for n in names:
            if n not in h:
                if missing_ok:
                    continue
                raise KeyError(n)
            d = h[n]
            pl = d.id.get_create_plist()
            filters = [pl.get_filter(i)[0] for i in range(pl.get_nfilters())]
            fill = None
            for a in ("_FillValue", "missing_value"):
                if a in d.attrs:
                    fill = np.asarray(d.attrs[a]).ravel()[0]
                    break
            if d.chunks is None:  # contiguous / compact: read directly
                meta[n] = ("dense", d[...], fill)
                continue
            info = [d.id.get_chunk_info(i) for i in range(d.id.get_num_chunks())]
            shape = d.shape
            if level is not None:
                ax, li = level
                assert d.chunks[ax] == 1
                info = [c for c in info if c.chunk_offset[ax] == li]
                info = [type(c)(tuple(0 if k == ax else o for k, o in enumerate(c.chunk_offset)), c.filter_mask,
                                c.byte_offset, c.size) for c in info]
                shape = tuple(1 if k == ax else n_ for k, n_ in enumerate(d.shape))
            meta[n] = ("chunked", (shape, d.chunks, d.dtype, filters, info), fill)
    f.close()
    # merge all chunk byte ranges into spans
    ranges = sorted((c.byte_offset, c.byte_offset + c.size) for n, (k, m, _) in meta.items() if k == "chunked"
                    for c in m[4])
    spans = []
    for s, e in ranges:
        if spans and s - spans[-1][1] <= max_gap:
            spans[-1][1] = max(spans[-1][1], e)
        else:
            spans.append([s, e])
    with ThreadPoolExecutor(workers) as ex:
        blobs = list(ex.map(lambda se: _get(url, se[0], se[1], headers), spans))
    starts = np.array([s for s, _ in spans])

    def piece(off: int, size: int) -> bytes:
        k = int(np.searchsorted(starts, off, side="right") - 1)
        b = off - spans[k][0]
        return blobs[k][b:b + size]

    out = {}
    for n, (kind, m, fill) in meta.items():
        if kind == "dense":
            a = np.asarray(m, dtype="f4")
        else:
            shape, chunks, dtype, filters, info = m
            a = np.empty(shape, dtype=dtype)
            for c in info:
                raw = piece(c.byte_offset, c.size)
                for flt in reversed(filters):
                    if flt == DEFLATE:
                        raw = zlib.decompress(raw)
                    elif flt == SHUFFLE:
                        raw = _unshuffle(raw, dtype.itemsize)
                    else:
                        raise NotImplementedError(f"HDF5 filter {flt}")
                blk = np.frombuffer(raw, dtype=dtype).reshape(chunks)
                sl = tuple(slice(o, min(o + ch, s)) for o, ch, s in zip(c.chunk_offset, chunks, shape))
                a[sl] = blk[tuple(slice(0, x.stop - x.start) for x in sl)]
            a = a.astype("f4", copy=False)
        if fill is not None:
            a[a == fill] = np.nan
        a[np.abs(a) >= 1e14] = np.nan
        out[n] = a
        meta[n] = None  # free chunk index
    del blobs
    return out
