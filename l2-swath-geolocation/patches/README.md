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

### Option D — native HDF4 reader in VirtualiZarr, no kerchunk (added after review)

kerchunk is in maintenance mode, so instead of fixing its HDF4 decoder, `optionD-virtualizarr-native-hdf4.diff`
replaces `parsers/hdf4.py` with a self-contained reader of the HDF4 SD model (494 lines incl. docstrings; the
tag-walking follows kerchunk's MIT-licensed reader, re-implemented). It reads through the
`ObjectStoreRegistry` + `BlockStoreReader` like `HDFParser` (no fsspec, no kerchunk, no HDF4 C
library), and keeps Option A's three small non-HDF4 fixes (DMR++ byte order, string fill values).

* Data descriptors → `Var0.0` Vgroups → `SD`/`SDD`/`NT` + `Attr0.0` Vdatas + `Dim0.0` Vgroups.
* Storage: contiguous uncompressed; `SPECIAL_COMP` (DEFLATE); `SPECIAL_CHUNKED` with per-chunk
  DEFLATE or none, unwritten chunks → the chunk header's fill value; chunk tables and other
  metadata stored as linked blocks are reassembled. RLE/N-bit/Skipping-Huffman/SZIP/JPEG,
  linked-block or external *data* raise a clear `NotImplementedError` (use `skip_variables`).
* Correct byte order from the number type (fixes #2 without touching kerchunk), all values of
  multi-valued attributes (kerchunk kept only the first), NUL-separated string attributes kept
  intact, `/` in names (MOD03 `Land/SeaMask`, silently lost before) → `_` with `hdf4_name`
  recorded, n-D variables, char arrays, CF-encoded `_FillValue`.
* New, opt-in `dimension_names="hdf4"` uses the file's own dimension names (e.g.
  `Along_swath_lines_1km:MOD_Swath_LST`) so variables that share a dimension align; the default
  keeps the old `<var>_x/_y` names. `reader_options` (fsspec options for kerchunk) is accepted and ignored.
* The `hdf4` extra no longer depends on kerchunk; the existing HDF4 tests run ungated.
* Tests: 12 new (pyhdf-generated contiguous/DEFLATE/3-D/RLE/`/`-name/attribute fixtures, plus a
  committed 18 KB chunked fixture written through the HDF4 C library by
  `tests/data/make_hdf4_chunked.py`: chunked, chunked+DEFLATE, partially written).

Verification against the HDF4 C library (pyhdf): **32 MODIS granules** (MOD03/MYD03 from 2013
and 2024, MOD11_L2/MYD11_L2), **1,324 datasets** (values + dimension names) and **4,652
attributes**, 0 mismatches; `scripts/50_hdf4_virtual_check.py` ALL OK with kerchunk import blocked.
Building references over the simulated networks (37 MB MYD03): 35 MB / 16 s over Earthdata
HTTPS vs. 205 MB / 27 s for the kerchunk + fsspec path (fsspec's cache thrashed); see
`results/virtual_build.csv` (`hdf4_native`).

### Recommendation (updated)

**Option D**, as two VirtualiZarr PRs: (1) the small format-independent fixes (DMR++
`byteOrder`, string `_FillValue` handling; ~20 lines, from Option A) and (2) the native HDF4
parser replacing the kerchunk wrapper. Reasons:

* It removes the dependency on a package in maintenance mode while fixing every bug found,
  and it gets things right that the kerchunk path never did (multi-valued attributes, `/` in
  names, chunk fill values, real dimension names, remote reads through the same obstore stack as
  every other parser).
* It is a larger diff than A/B (a new 494-line module), but self-contained: one file, the HDF4
  SD model only, and the only public-API change is an *added* option (`dimension_names`).
  Existing tests pass unchanged apart from removing the kerchunk gate.
* Still worth sending kerchunk the 2-line big-endian float fix (Option A's kerchunk part,
  #2) even in maintenance mode: it is silent data corruption for anyone calling
  `kerchunk.hdf4` directly.

Options A/B remain valid if maintainers prefer the smallest possible change to the current
kerchunk-based parser.

## Test results

| | 5 real NASA files (`scripts/50_hdf4_virtual_check.py`) | new regression tests (3) | VirtualiZarr parsers + writers + manifests suites |
|---|---|---|---|
| stock 2.8.0 / 0.2.10 | 0 / 5 readable | 0 / 3 | 39 failing/erroring |
| blunt | 5 / 5, bit-identical | — | — |
| **Option A** | 5 / 5, bit-identical | 3 / 3 | 36 failing/erroring — **exactly** the stock set minus the 3 new tests |
| **Option B** (stock kerchunk) | 5 / 5, bit-identical | 3 / 3 | identical to A |
| **Option D** (native, no kerchunk) | 5 / 5, bit-identical; + 32 granules / 1,324 datasets / 4,652 attributes vs. pyhdf | 3 / 3 (+12 new native tests) | identical to A (510 passed) |
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
