# Making MODIS HDF4 (and friends) work as virtual Zarr

VirtualiZarr 2.8.0 + kerchunk 0.2.10 (the versions in `pixi.lock`) could not virtualise any of
the MODIS C6.1 HDF4 granules in this experiment, nor the one HDF4-derived DMR++ sidecar, and
needed variables dropped for VIIRS VNP21. The vendored copies (`vendor/VirtualiZarr`,
`vendor/kerchunk`, git submodules pinned to those release tags) were patched until every file
reads **bit-identical** to pyhdf/h5py (`scripts/50_hdf4_virtual_check.py`).

## Root causes

| # | Symptom | Root cause | Where |
|---|---|---|---|
| 1 | `KeyError: 'data'` (MYD03) | A plain (non-extended) HDF4 `SD` tag stores the array contiguously and **uncompressed**; kerchunk only records refs for chunked/compressed (extended) tags. | kerchunk `hdf4.py::_descend_vg` |
| 2 | garbage floats, `Failed to decode fill_value` (MYD11_L2) | kerchunk's HDF4 type table maps `DFNT_FLOAT32/64` to **little-endian** `f4`/`f8`; HDF4 is big-endian (integers were already `>i2` etc.). Float arrays *and* float attributes (`_FillValue`, `valid_range`) are byte-swapped. | kerchunk `hdf4.py::dtypes` |
| 3 | `Failed to decode fill_value: expected str or bytes for dtype float32` | `HDF4Parser` passes the raw `_FillValue` attribute through; all other parsers CF-encode it (`encode_cf_fill_value`) as xarray's Zarr backend expects. | VirtualiZarr `parsers/hdf4.py` |
| 4 | (silent) wrong data for uncompressed arrays | `HDF4Parser` sets a zlib codec on **every** array that has refs, so #1's contiguous arrays would be "decompressed". kerchunk's own `translate` has the same bug. | VirtualiZarr `parsers/hdf4.py`, kerchunk `translate` |
| 5 | `For string dtype, ArrayBytesCodec must be VLenUTF8Codec` (MYD03 "Scan Type") | HDF4 char arrays come through as dtype `"str"`; Zarr v3 cannot store that with a bytes codec. They are 1 byte per element: `|S1`. | VirtualiZarr `parsers/hdf4.py` |
| 6 | `dimension_names and shape need the same number of dimensions` (MYD03 `T_inst2ECR`, 203×3×3) | Dimension names are generated only for ≤ 2-D variables. | VirtualiZarr `parsers/hdf4.py` |
| 7 | MOD11_L2 DMR++ values byte-swapped | The DMR++ declares `byteOrder="BE"` on `<dmrpp:chunks>`; the DMR++ parser ignores it. | VirtualiZarr `parsers/dmrpp.py` |
| 8 | `Failed to encode fill_value: expected int or float for dtype uint16, got str` (VNP21 `QC`/`PWV`/`oceanpix`: `"n/a"`; MOD11_L2 DMR++ `QC`: `"NA"`) | String `_FillValue` on a numeric variable. These are product-metadata defects, but they make the *whole file* unreadable. | VirtualiZarr `parsers/utils.py` (+ call sites in `hdf.py`, `dmrpp.py`) |

## The blunt fix

`blunt-kerchunk.diff`, `blunt-virtualizarr.diff`: fix every symptom where it appears
(also reads the real HDF4 compression coder instead of assuming DEFLATE). This is what
built the MODIS virtual stores used in the read benchmark.

## Minimal options

All options were verified with `scripts/50_hdf4_virtual_check.py` (5 real NASA files, every
variable compared with pyhdf/h5py) and with new regression tests
(`virtualizarr/tests/test_parsers/test_nasa_regressions.py`, fixtures generated with pyhdf/h5py:
a contiguous uncompressed array, a big-endian float with `_FillValue`, a 3-D array, a char
array, an HDF5 string fill value, a big-endian DMR++). Upstream test-suite results: see
"Test results" below.

### Option A — fix each bug where it lives (kerchunk + VirtualiZarr)

* **kerchunk** (`optionA-kerchunk.diff`, +11/−3): big-endian floats in `dtypes` (#2);
  record contiguous `SD` data as `("NONE", offset, length)` (#1); `translate` only applies zlib
  when refs are actually DEFLATE-compressed (#4, kerchunk side).
* **VirtualiZarr** (`optionA-virtualizarr.diff`, +33/−5 in 4 source files, plus a 113-line test file): `hdf4.py` — per-variable codec from the
  refs (#4), CF-encode `_FillValue` (#3), `str` → `|S1` (#5), n-D dimension names (#6);
  `dmrpp.py` — honour `byteOrder="BE"` (#7); `utils.encode_cf_fill_value` — parse numeric text,
  otherwise warn and return `None`, and the HDF5/DMR++/HDF4 call sites drop the attribute (#8).

### Option B — VirtualiZarr only (works with released kerchunk)

`optionB-virtualizarr.diff` (+46/−5 in 4 source files, plus the same tests) = Option A's VirtualiZarr part plus two guarded
work-arounds for the kerchunk bugs inside `parsers/hdf4.py`: fill in `data` for plain `SD`
tags before calling kerchunk's `_descend_vg` (#1), and turn kerchunk's `f4`/`f8` into `>f4`/`>f8`
while byte-swapping float attributes (#2). Both guards are no-ops once kerchunk is fixed (tested
against Option A's kerchunk too).

### Option C — no fork: monkeypatch at import time

The same changes applied from user code (e.g. a `swathgeo.vz_compat` module patching
`kerchunk.hdf4.dtypes`, `HDF4ToZarr._descend_vg`, `virtualizarr.parsers.hdf4._manifestarray`,
`DMRPPParser._parse_variable`). Zero install friction, but brittle (private functions,
breaks silently on upgrade). Not implemented beyond noting it is possible.

### Recommendation

**Option A**, upstreamed as two small PRs (kerchunk, VirtualiZarr) — with **Option B's two
guards** kept in VirtualiZarr until a fixed kerchunk is released and pinned. Reasons:

* Bug #2 is silent **data corruption** in kerchunk itself: anyone using
  `kerchunk.hdf4.HDF4ToZarr` directly gets byte-swapped floats today. Working around it only in
  VirtualiZarr leaves that in place.
* Bug #4 also corrupts kerchunk's own references for uncompressed arrays.
* The VirtualiZarr changes are local to the HDF4 parser, the DMR++ dtype line, and the shared
  fill-value encoder; no public API changes. The only behaviour change for previously working
  files: a `_FillValue` that is a *numeric string* (e.g. `"0"`) is now parsed instead of raising,
  and a non-numeric one is dropped with a warning instead of making the whole file unreadable.
* Dropping vs. keeping the bogus fill value: dropping is the conservative choice (no masking is
  better than masking with a value the producer never meant); an alternative is to keep the
  original text under another attribute name, at the cost of inventing a convention.

## Test results

| | 5 real NASA files (`scripts/50_hdf4_virtual_check.py`) | new regression tests (3) | VirtualiZarr parsers + writers + manifests suites |
|---|---|---|---|
| stock 2.8.0 / 0.2.10 | 0 / 5 readable | 0 / 3 | 39 failing/erroring |
| blunt | 5 / 5, bit-identical | — | — |
| **Option A** | 5 / 5, bit-identical | 3 / 3 | 36 failing/erroring — **exactly** the stock set minus the 3 new tests |
| **Option B** (stock kerchunk) | 5 / 5, bit-identical | 3 / 3 | identical to A |
| Option B + Option A's kerchunk | 5 / 5 | 3 / 3 | — (guards are no-ops) |

The 36 pre-existing failures/errors are environmental (DMR++ tests that fetch remote fixtures,
writer tests needing optional services) and identical before and after, i.e. **no regressions**.
kerchunk's own `tests/test_hdf4.py` errors identically on stock and patched kerchunk (a zarr-3
incompatibility in that test). With Option A, `kerchunk.hdf4.HDF4ToZarr(...).translate()` itself now
returns correct big-endian floats and correct uncompressed contiguous arrays (checked on a
pyhdf-generated file).

Reproduce (from `l2-swath-geolocation/`):

```bash
git submodule update --init --depth 1 vendor/VirtualiZarr vendor/kerchunk
git -C vendor/VirtualiZarr apply ../../patches/optionA-virtualizarr.diff   # or blunt-/optionB-
git -C vendor/kerchunk apply ../../patches/optionA-kerchunk.diff
PYTHONPATH=vendor/VirtualiZarr:vendor/kerchunk pixi run python scripts/50_hdf4_virtual_check.py
```
