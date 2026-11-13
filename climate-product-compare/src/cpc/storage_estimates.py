"""Storage-volume estimates per product (PROMPT.md, Follow-up 3).

Five numbers per product:

1. ``all_orig``   complete product, original format, all variables
2. ``used_orig``  complete product, original format, only the source variables used here
3. ``used_opt``   complete product, only the variables stored here, quantized + pcodec in Icechunk
                  (time-series chunks; no-data pixels such as ocean in land-only products not stored)
4. ``sites_full`` as 3, but only at the extracted sites (2x2 stencil), over the complete record
5. ``sites_meas`` measured: our store, ``results/store_sizes.csv`` (2008 onward, or product start)

Inputs and provenance:

* Original-format sizes come from real files (HTTP HEAD / bucket listings / GRIB ``.idx`` byte
  offsets, 2026-11-13); the numbers are in the ``basis`` strings below.
* Bytes/value of the optimized encoding come from ``measure_fullgrid``: random 16x16-pixel x 1-year
  blocks anywhere on the grid (land and ocean), quantized and pcodec-encoded like the site store, in
  the better of two in-chunk layouts per variable ((time, y, x) or (y, x, time)). Measured for the
  six products with ARCO copies plus one full year of gridMET (tmmx, pr); written to
  ``results/storage_fullgrid_bpv.csv`` together with the site-store bytes/value of the same
  variables. For the other products: site-store bytes/value x the range of full-grid/site ratios
  measured for products of the same time step (hourly or daily).
* Record ends are the ``extracted_end`` of our store, so "complete product" means the product's
  first time step through the date we extracted to.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config

TB = 1e12
MB = 1e6

FULLGRID_CSV = "storage_fullgrid_bpv.csv"
OUT_CSV = "storage_estimates.csv"


# --- full-grid re-encoding measurement --------------------------------------------------


def _encode(a: np.ndarray, kind: str, codec) -> tuple[int, int]:
    """Bytes of the better of two in-chunk layouts, and the number of valid values.

    a: (time, y, x). Layout "t,y,x" (natural Zarr order; pcodec deltas run along x, exploiting
    spatial smoothness) vs "y,x,t" (pixel time series contiguous). All-NaN blocks are not stored.
    """
    from . import store

    q = store.quantize(a, kind)
    nvalid = int(np.isfinite(q).sum())
    if nvalid == 0:
        return 0, 0
    sizes = [len(codec.encode(np.ascontiguousarray(x))) for x in (q, np.moveaxis(q, 0, -1))]
    return min(sizes), nvalid


def measure_fullgrid(name: str, nbox: int = 12, start: str = "2020-01-01", box: int = 16, seed: int = 0) -> dict:
    """Quantize + pcodec-encode random `box` x `box`-pixel x 1-year blocks of an ARCO product.

    Blocks anywhere on the grid (land and ocean); bytes per valid value, better layout per variable.
    """
    from concurrent.futures import ThreadPoolExecutor

    import numcodecs

    from .products import registry

    codec = numcodecs.get_codec({"id": "pcodec", "level": 8})
    p = registry.get(name)
    arrs, times = p.arrays(), p.source_times()
    nt = {"1d": 365, "1h": 8760, "30min": 17520}[p.freq]
    i0 = int(times.searchsorted(pd.Timestamp(start)))
    a0 = next(iter(arrs.values()))
    ny, nx = a0.shape[1], a0.shape[2]
    rng = np.random.default_rng(seed)
    boxes = [(int(rng.integers(0, ny - box)), int(rng.integers(0, nx - box))) for _ in range(nbox)]
    needed = sorted({s for v in p.variables.values() for s in v.src})

    def one(yx):
        y, x = yx
        raw = {s: np.asarray(arrs[s][i0:i0 + nt, y:y + box, x:x + box], dtype="f8") for s in needed if s in arrs}
        return {v: _encode(np.asarray(a), p.variables[v].kind, codec) for v, a in p.convert_all(raw).items()}

    tot = {v: [0, 0] for v in p.variables}
    with ThreadPoolExecutor(4) as ex:
        for r in ex.map(one, boxes):
            for v, (e, n) in r.items():
                tot[v][0] += e
                tot[v][1] += n
    return _summary(name, nbox, start, tot)


def _summary(name, nbox, start, tot) -> dict:
    e = sum(a for a, _ in tot.values())
    n = sum(b for _, b in tot.values())
    return {"product": name, "boxes": nbox, "start": start, "bytes_per_value": round(e / n, 4),
            "per_var": {v: (round(a / b, 4) if b else None) for v, (a, b) in tot.items()}}


def measure_gridmet(year: int = 2020, box: int = 16) -> dict:
    """gridMET full CONUS grid for one year (tmmx, pr): the daily fine-grid case."""
    import tempfile

    import numcodecs
    import xarray as xr

    from . import http

    codec = numcodecs.get_codec({"id": "pcodec", "level": 8})
    tot = {}
    for v, var, kind, off in (("tmmx", "air_temperature", "temp", 273.15), ("pr", "precipitation_amount", "precip", 0)):
        with tempfile.NamedTemporaryFile(suffix=".nc", dir=config.DATA) as f:
            f.write(http.get(f"https://www.northwestknowledge.net/metdata/data/{v}_{year}.nc", timeout=900).content)
            f.flush()
            a = xr.open_dataset(f.name)[var].values.astype("f8") - off
        e = n = 0
        for j in range(0, a.shape[1], box):
            for k in range(0, a.shape[2], box):
                de, dn = _encode(a[:, j:j + box, k:k + box], kind, codec)
                e, n = e + de, n + dn
        tot[v] = [e, n]
    return _summary("gridmet", 0, f"{year}-01-01", tot)


def site_store_bpv(name: str, variables: list[str]) -> float:
    """Bytes/value of the same pcodec encoding on our site store ((site, px, time) blocks), for `variables`."""
    import numcodecs
    import zarr

    from . import store
    from .products import registry

    codec = numcodecs.get_codec({"id": "pcodec", "level": 8})
    p = registry.get(name)
    g = zarr.open_group(store.readonly("products", name).store, mode="r",
                        path=store.group_path("products", name, p.freq))
    e = n = 0
    for v in variables:
        if v not in g:
            continue
        for i in range(g[v].shape[0]):
            b = g[v][i]
            if np.isfinite(b).any():
                e += len(codec.encode(np.ascontiguousarray(b)))
                n += int(np.isfinite(b).sum())
    return round(e / n, 4)


GRIDMET_VARS = {"tmmx": "tmax", "pr": "pr"}  # gridMET file name -> our variable name


def measure_all() -> pd.DataFrame:
    jobs = [("era5", 12, "2020-01-01"), ("era5land", 12, "2020-01-01"), ("merra2", 12, "2020-01-01"),
            ("hrrr", 12, "2023-01-01"), ("chirps3", 24, "2020-01-01"), ("imerg_late", 12, "2023-01-01")]
    results = [measure_fullgrid(*j) for j in jobs] + [measure_gridmet()]
    rows = []
    for r in results:
        print(json.dumps(r))
        vs = [GRIDMET_VARS[v] for v in r["per_var"]] if r["product"] == "gridmet" else \
            [v for v, b in r["per_var"].items() if b is not None]
        rows.append({k: r[k] for k in ("product", "boxes", "start", "bytes_per_value")} |
                    {"site_bpv_same_vars": site_store_bpv(r["product"], vs), "per_var": json.dumps(r["per_var"])})
    df = pd.DataFrame(rows)
    df.to_csv(config.RESULTS / FULLGRID_CSV, index=False)
    return df


# --- per-product parameters ---------------------------------------------------------------


@dataclass
class P:
    name: str  # store/registry name (several for IMERG Final)
    label: str
    resolution: str
    start: str  # first time step of the complete product
    freq: str
    pixels: int  # full grid
    data_frac: tuple[float, float]  # fraction of pixels with data (stored in the optimized copy)
    all_orig: tuple[float, float]  # bytes
    used_orig: tuple[float, float]  # bytes
    basis: str  # provenance of the original-format numbers
    fullgrid: str | None = None  # product whose measured full-grid bytes/value applies
    end: str | None = None  # override record end (default: our store's extracted_end)
    stores: list[str] = field(default_factory=list)  # store repos (default [name])
    per_year: bool = False  # GEOS-FP: per 12 months


def _steps(start, end, freq) -> int:
    return len(pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq=freq))


def _h(start, end):
    return _steps(start, end, "1h")


def _d(start, end):
    return _steps(start, end, "1D")


def _ends() -> dict[str, str]:
    """extracted_end per store, from the Icechunk group attributes (falls back to the CSV cache)."""
    cache = config.RESULTS / "storage_record_ends.json"
    try:
        from . import store
        from .products import registry

        ends = {}
        for n in registry.names():
            p = registry.get(n)
            a = store.group_attrs(store.readonly("products", n), store.group_path("products", n, p.freq))
            ends[n] = str(pd.Timestamp(a["extracted_end"]))
        cache.write_text(json.dumps(ends, indent=1) + "\n")
        return ends
    except Exception:
        return json.loads(cache.read_text())


def products(ends: dict[str, str]) -> list[P]:
    e = ends
    out = []

    # ERA5: CDS GRIB, simple packing at 16 bits (some fields 24) = 2.0-2.6 B/value on 721 x 1440.
    n = _h("1940-01-01", e["era5"]) * 721 * 1440
    out.append(P("era5", "ERA5", "0.25°, hourly", "1940-01-01", "1h", 721 * 1440, (1, 1),
                 (1.3e15, 5e15), (15 * n * 2.0, 15 * n * 2.6),
                 "GRIB 2.0-2.6 B/value. All: ~260 single-level fields + 16 vars x 37 pressure levels "
                 "≈ 1.3 PB; with model levels and the ensemble, several PB. Used: 15 single-level fields.",
                 fullgrid="era5"))

    # ERA5-Land: GRIB with a land bitmap; ~50 hourly variables; 27-33 % of the 0.1° grid is land.
    pix = 1801 * 3600
    n = _h("1950-01-01", e["era5land"]) * pix
    out.append(P("era5land", "ERA5-Land", "0.1°, hourly, land", "1950-01-01", "1h", pix, (0.27, 0.33),
                 (50 * n * 0.27 * 2.0, 50 * n * 0.33 * 2.6), (17 * n * 0.27 * 2.0, 17 * n * 0.33 * 2.6),
                 "GRIB 2.0-2.6 B per land value, 27-33 % land. All: ~50 hourly variables. Used: 17.",
                 fullgrid="era5land"))

    # MERRA-2: NetCDF4 deflate. tavg1_2d_slv_Nx = 413.6 MB/day for 47 vars -> 1.76 B/value.
    pix = 361 * 576
    n = _h("1980-01-01", e["merra2"]) * pix
    days = _d("1980-01-01", e["merra2"])
    out.append(P("merra2", "MERRA-2", "0.5° x 0.625°, hourly", "1980-01-01", "1h", pix, (1, 1),
                 (0.2e15, 0.45e15), (18 * n * 1.2, 18 * n * 1.8),
                 f"NetCDF4: slv 413.6, flx 399.8, rad 222.9, lnd 210.4 MB/day; these four 2-D hourly "
                 f"collections alone = {1.2467e9 * days / TB:.0f} TB. All ~40 collections incl. 3-D (unmeasured, "
                 "dominated by 3-D): 0.2-0.45 PB. Used: 18 fields at 1.2-1.8 B/value (slv = 1.76).",
                 fullgrid="merra2"))

    # NLDAS-2: NetCDF4 hourly files on 464 x 224 (103,936 cells, ~73 % land).
    pix = 464 * 224
    h = _h("1979-01-01", e["nldas2_forcing"])
    out.append(P("nldas2_forcing", "NLDAS-2 forcing", "0.125°, hourly, CONUS", "1979-01-01", "1h", pix,
                 (0.70, 0.76), (h * 3.1 * MB, h * 3.4 * MB), (h * 1.6 * MB * 7 / 11, h * 1.9 * MB * 7 / 11),
                 "NetCDF4: FORA 1.6-1.9 MB/h (11 vars), FORB 1.5 MB/h. Used: 7 of the 11 FORA vars."))
    h = _h("1979-01-01", e["nldas2_noah"])
    for nm, lab, mb, nall, nused in (("nldas2_noah", "NLDAS-2 Noah", (6.8, 7.4), 52, 11),
                                     ("nldas2_vic", "NLDAS-2 VIC", (5.8, 5.8), 43, 4),
                                     ("nldas2_mosaic", "NLDAS-2 Mosaic", (5.8, 5.8), 38, 4)):
        f = nused / nall
        out.append(P(nm, lab, "0.125°, hourly, CONUS", "1979-01-01", "1h", pix, (0.70, 0.76),
                     (h * mb[0] * MB, h * mb[1] * MB), (h * mb[0] * MB * f * 0.8, h * mb[1] * MB * f * 1.25),
                     f"NetCDF4 {mb[0]}-{mb[1]} MB/h, ~{nall} vars; used {nused} (share of bytes ±25 %)."))

    # GEOS-FP: per 12 months. NCCS portal NetCDF4 per hour: slv 48.0, lnd 166.5, rad 22-40, flx 41 MB.
    out.append(P("geosfp", "GEOS-FP (per 12 months)", "0.3125° x 0.25°, hourly", "2025-11-12", "1h",
                 1152 * 721, (1, 1), (20 * TB, 30 * TB), (0.2 * TB, 0.4 * TB),
                 "NCCS NetCDF4 per hour: slv 48.0, lnd 166.5, rad 22-40, flx 41 MB (2.4-2.6 TB/yr for these four). "
                 "All assimilation collections incl. 3-D: ~20-30 TB/yr (unmeasured). Used: 18 fields ≈ 32 MB/h.",
                 per_year=True, end="2026-11-11 23:00"))

    # HRRR analysis (f00) GRIB2 on 1799 x 1059. wrfsfc 134-142, wrfprs 380, wrfnat 640 MB per hour.
    h = _h("2014-10-01", e["hrrr"])
    out.append(P("hrrr", "HRRR (analysis)", "3 km, hourly, CONUS", "2014-10-01", "1h", 1799 * 1059, (1, 1),
                 (h * 0.8e9, h * 1.16e9), (h * 10 * MB, h * 13 * MB),
                 "GRIB2 f00: wrfsfc 134-142 MB (170 fields), wrfprs 380 MB (708), wrfnat 640 MB (1,133); "
                 "older years smaller. The whole AWS archive with all forecast hours is several PB. "
                 "Used: 9 analysis fields (11.7 MB, from .idx offsets) + 1-h APCP from f01 (0.3 MB).",
                 fullgrid="hrrr"))

    # PRISM 4 km daily: zipped COG 2.0-2.6 MB per variable-day; 872,505 cells, 55 % land.
    d = _d("1981-01-01", e["prism"])
    out.append(P("prism", "PRISM 4 km", "4 km, daily, CONUS", "1981-01-01", "1D", 621 * 1405, (0.55, 0.55),
                 (d * 8 * 2.0 * MB, d * 8 * 2.6 * MB), (d * 8 * 2.0 * MB, d * 8 * 2.6 * MB),
                 "Zipped COG, 2.0-2.6 MB per variable-day; 8 daily variables (incl. soltotal), all used. "
                 "The 800 m product is ~16x larger."))

    # gridMET: yearly NetCDF per variable: tmmx 146.7 MB, pr 58.7 MB (2020); 16 variables.
    y = _d("1979-01-01", e["gridmet"]) / 365.25
    out.append(P("gridmet", "gridMET", "1/24°, daily, CONUS", "1979-01-01", "1D", 585 * 1386, (0.55, 0.60),
                 (16 * y * 60 * MB, 16 * y * 150 * MB), (9 * y * 60 * MB, 9 * y * 150 * MB),
                 "NetCDF4 per variable-year: 59 MB (pr) to 147 MB (tmmx); 16 variables; used 9."))

    # Daymet V4R1: NA grid 7814 x 8075, tmax_2020 13.82 GB; prcp/swe/dayl compress better.
    yr = 2025 - 1980 + 1
    out.append(P("daymet", "Daymet V4R1", "1 km, daily, N. America", "1980-01-01", "1D", 7814 * 8075, (0.40, 0.50),
                 (7 * yr * 9e9, 7 * yr * 14e9), (7 * yr * 9e9, 7 * yr * 14e9),
                 "NetCDF4 per variable-year, North America: tmax 13.8 GB (2020); 9-14 GB across the 7 variables; "
                 "all used (Hawaii/Puerto Rico add <1 %)."))

    # CHELSA-daily v2.1: COG per variable-day (Jan 2019 means); 12 variables.
    d = _d("1941-01-01", e["chelsa"])
    out.append(P("chelsa", "CHELSA-daily", "30″ (~1 km), daily, global land", "1941-01-01", "1D", 43200 * 20880,
                 (0.27, 0.31), (d * 1884.7 * MB * 0.85, d * 1884.7 * MB * 1.15),
                 (d * 1816.9 * MB * 0.85, d * 1816.9 * MB * 1.15),
                 "COG MB/day: rsds 407, sfcWind 361, hurs 233, ps 170, tasmin 159, tasmax 156, tas 151, pr 93, "
                 "prec 87, we 45, clt 18, tz 4 (1,885 MB/day, ±15 %). Used: 9 (1,817 MB/day)."))

    # CHIRPS v3 rnl daily: 3.87 GB per year (NetCDF, 2020).
    y = _d("1981-01-01", e["chirps3"]) / 365.25
    out.append(P("chirps3", "CHIRPS v3", "0.05°, daily, 50°S-50°N land", "1981-01-01", "1D", 7200 * 2000,
                 (0.25, 0.30), (y * 3.87e9 * 2.2, y * 3.87e9 * 3.0), (y * 3.87e9 * 0.95, y * 3.87e9 * 1.05),
                 "rnl daily NetCDF 3.87 GB/yr. All: two variants (sat, rnl) x daily/pentad/dekad/monthly, NetCDF + "
                 "COG ≈ 2.2-3x. Used: rnl daily precipitation only.",
                 fullgrid="chirps3"))

    # IMERG V07 HDF5: HH 8.15 MB per half hour, DF 33.7 MB per day; 10 grids per file.
    hh = _steps("1998-06-01", "2025-09-30 23:30", "30min")
    dd = _d("1998-06-01", "2025-09-30")
    out.append(P("imerg_final", "IMERG Final V07 (HH + daily)", "0.1°, half-hourly + daily, 60°S-60°N",
                 "1998-06-01", "30min", 3600 * 1800, (1, 1),
                 ((hh * 8.15 + dd * 33.7) * MB * 0.9, (hh * 8.15 + dd * 33.7) * MB * 1.1),
                 ((hh * 8.15 + dd * 33.7) * MB * 0.10, (hh * 8.15 + dd * 33.7) * MB * 0.25),
                 "HDF5: HH 8.15 MB, daily 33.7 MB; 10 grids per file (precipitation, randomError, IR/MW precip, "
                 "quality, ...). Used: precipitation only, 10-25 % of the bytes.",
                 fullgrid="imerg_late", end="2025-09-30 23:30", stores=["imerg_final_hh", "imerg_final_daily"]))
    hh = _steps("1998-06-01", e["imerg_late"], "30min")
    out.append(P("imerg_late", "IMERG Late V07", "0.1°, half-hourly, 60°S-60°N", "1998-06-01", "30min",
                 3600 * 1800, (1, 1), (hh * 7.5 * MB * 1.05, hh * 8.2 * MB * 1.1),
                 (hh * 7.5 * MB * 0.10, hh * 8.2 * MB * 0.25),
                 "HDF5 HH 7.5-8.2 MB (+5-10 % for the Late daily product); used: precipitation, 10-25 % of the bytes.",
                 fullgrid="imerg_late"))
    return out


# --- estimate ---------------------------------------------------------------------------------


def estimate() -> pd.DataFrame:
    from .products import registry

    sizes = pd.read_csv(config.RESULTS / "store_sizes.csv").set_index("repo")
    fg = pd.read_csv(config.RESULTS / FULLGRID_CSV).set_index("product")
    ratio = fg.bytes_per_value / fg.site_bpv_same_vars  # full grid, best layout / site-store layout
    r_h = ratio[["era5", "era5land", "merra2", "hrrr"]]
    r_d = ratio[["chirps3", "gridmet"]]
    ends = _ends()
    rows = []
    for p in products(ends):
        stores = p.stores or [p.name]
        end = p.end or ends[p.name]
        meas = sizes.loc[[f"products-{s}" for s in stores]]
        nvars = int(meas.variables.iloc[0])
        site_bpv = float((meas.size_MB.sum() * MB) / meas.stored_values.sum())
        # optimized bytes/value
        if p.name in fg.index and p.name != "gridmet":  # measured on the full grid, all variables
            b = float(fg.loc[p.name, "bytes_per_value"])
            bpv = (0.85 * b, 1.15 * b)
            bpv_src = f"{b:.2f} measured on the full grid ±15 %"
        elif p.name == "gridmet":  # tmmx + pr measured on the full grid: apply their ratio to all variables
            b = site_bpv * float(ratio["gridmet"])
            bpv = (0.85 * b, 1.15 * b)
            bpv_src = f"{b:.2f} = site store {site_bpv:.2f} x {ratio['gridmet']:.2f} (full-grid tmmx+pr ratio) ±15 %"
        else:
            rr = r_d if p.freq == "1D" else r_h
            bpv = (site_bpv * rr.min(), site_bpv * rr.max())
            bpv_src = (f"{bpv[0]:.2f}-{bpv[1]:.2f} = site store {site_bpv:.2f} x {rr.min():.2f}-{rr.max():.2f} "
                       f"(full-grid/site ratio of the measured {'daily' if p.freq == '1D' else 'hourly'} products)")
        if p.name == "imerg_final":
            # half-hourly at the IMERG Late full-grid rate + daily at the site-store rate x the daily ratios
            hh = _steps(p.start, end, "30min")
            dd = _d(p.start, pd.Timestamp(end).normalize())
            dbpv = float(sizes.loc["products-imerg_final_daily", "bytes_per_value"])
            b = float(fg.loc["imerg_late", "bytes_per_value"])
            opt = (p.pixels * (hh * 0.85 * b + dd * dbpv * r_d.min()),
                   p.pixels * (hh * 1.15 * b + dd * dbpv * r_d.max()))
            bpv_src = (f"half-hourly {b:.2f} (IMERG Late, full grid) ±15 %; daily: site store {dbpv:.2f} "
                       f"x {r_d.min():.2f}-{r_d.max():.2f}")
            # sites, full record: scale each store's measured bytes to the full record
            sf = 0.0
            for s, n_full in (("imerg_final_hh", hh), ("imerg_final_daily", dd)):
                r = sizes.loc[f"products-{s}"]
                sf += r.size_MB * MB * n_full / r.time_steps
            sites_full = sf
            nsteps = hh
        else:
            nsteps = _steps(p.start, end, p.freq) if not p.per_year else 8760
            opt = tuple(nsteps * p.pixels * fr * nvars * b for fr, b in zip(p.data_frac, bpv))
            r = meas.iloc[0]
            sites_full = r.size_MB * MB * nsteps / r.time_steps
        reg = registry.get(stores[0])
        rows.append({
            "product": p.label, "key": p.name, "resolution": p.resolution,
            "record": f"{p.start[:10]} – {str(end)[:10]}" if not p.per_year else "12 months",
            "time_steps": nsteps, "grid_pixels": p.pixels,
            "data_frac": f"{p.data_frac[0]:.2f}" if p.data_frac[0] == p.data_frac[1] else f"{p.data_frac[0]:.2f}-{p.data_frac[1]:.2f}",
            "n_src_used": len({s for v in reg.variables.values() for s in v.src}), "n_stored": nvars,
            "all_orig_lo_TB": p.all_orig[0] / TB, "all_orig_hi_TB": p.all_orig[1] / TB,
            "used_orig_lo_TB": p.used_orig[0] / TB, "used_orig_hi_TB": p.used_orig[1] / TB,
            "used_opt_lo_TB": opt[0] / TB, "used_opt_hi_TB": opt[1] / TB,
            "opt_bytes_per_value": bpv_src,
            "sites_full_GB": sites_full / 1e9,
            "sites_meas_GB": float(meas.size_MB.sum()) / 1e3,
            "sites_meas_steps": int(meas.time_steps.max()),
            "n_sites": int(meas.sites.max()),
            "basis": p.basis,
        })
    df = pd.DataFrame(rows)
    num = [c for c in df.columns if c.endswith(("_TB", "_GB"))]
    df[num] = df[num].astype(float)
    df.round(6).to_csv(config.RESULTS / OUT_CSV, index=False)
    return df


# --- formatting ------------------------------------------------------------------------------


def fmt_bytes(x: float) -> str:
    """Bytes -> short string with an SI unit and 2 significant figures."""
    for unit, s in (("PB", 1e15), ("TB", 1e12), ("GB", 1e9), ("MB", 1e6), ("kB", 1e3)):
        if x >= s:
            v = x / s
            return f"{v:.2g} {unit}" if v < 10 else f"{v:.0f} {unit}"
    return f"{x:.0f} B"


def fmt_range(lo: float, hi: float) -> str:
    a, b = fmt_bytes(lo), fmt_bytes(hi)
    if a == b:
        return a
    ua, ub = a.split()[1], b.split()[1]
    return f"{a.split()[0]}–{b}" if ua == ub else f"{a}–{b}"


def table_rows(df: pd.DataFrame) -> list[dict]:
    out = []
    for r in df.itertuples():
        out.append({
            "product": r.product, "key": r.key, "resolution": r.resolution, "record": r.record,
            "all_orig": fmt_range(r.all_orig_lo_TB * TB, r.all_orig_hi_TB * TB),
            "used_orig": fmt_range(r.used_orig_lo_TB * TB, r.used_orig_hi_TB * TB),
            "used_opt": fmt_range(r.used_opt_lo_TB * TB, r.used_opt_hi_TB * TB),
            "sites_full": fmt_bytes(r.sites_full_GB * 1e9),
            "sites_meas": fmt_bytes(r.sites_meas_GB * 1e9),
            "n_src_used": int(r.n_src_used), "n_stored": int(r.n_stored), "data_frac": r.data_frac,
            "opt_bpv": r.opt_bytes_per_value, "basis": r.basis,
            "raw": {k: getattr(r, k) for k in ("all_orig_lo_TB", "all_orig_hi_TB", "used_orig_lo_TB",
                                                "used_orig_hi_TB", "used_opt_lo_TB", "used_opt_hi_TB",
                                                "sites_full_GB", "sites_meas_GB")},
        })
    return out


def totals(df: pd.DataFrame) -> dict:
    """Totals excluding GEOS-FP (per-year) — shown separately."""
    d = df[df.key != "geosfp"]
    return {
        "all_orig": fmt_range(d.all_orig_lo_TB.sum() * TB, d.all_orig_hi_TB.sum() * TB),
        "used_orig": fmt_range(d.used_orig_lo_TB.sum() * TB, d.used_orig_hi_TB.sum() * TB),
        "used_opt": fmt_range(d.used_opt_lo_TB.sum() * TB, d.used_opt_hi_TB.sum() * TB),
        "sites_full": fmt_bytes(d.sites_full_GB.sum() * 1e9),
        "sites_meas": fmt_bytes(df.sites_meas_GB.sum() * 1e9),
    }


def markdown(df: pd.DataFrame) -> str:
    lines = ["| Product | Record | 1. Complete, all vars (original) | 2. Complete, used vars (original) | "
             "3. Complete, used vars, optimized Icechunk | 4. As 3, sites only (complete record) | "
             "Measured: our site store |",
             "|---|---|---|---|---|---|---|"]
    for r in table_rows(df):
        lines.append(f"| {r['product']} | {r['record']} | {r['all_orig']} | {r['used_orig']} | {r['used_opt']} | "
                     f"{r['sites_full']} | {r['sites_meas']} |")
    t = totals(df)
    lines.append(f"| **Total** (excl. GEOS-FP) | | **{t['all_orig']}** | **{t['used_orig']}** | **{t['used_opt']}** | "
                 f"**{t['sites_full']}** | **{t['sites_meas']}** (incl. GEOS-FP) |")
    return "\n".join(lines)


def write_site_json(df: pd.DataFrame, path) -> None:
    fg = pd.read_csv(config.RESULTS / FULLGRID_CSV)
    path.write_text(json.dumps({
        "generated": pd.Timestamp.now("UTC").strftime("%Y-%m-%d"),
        "rows": table_rows(df), "totals": totals(df),
        "fullgrid": fg[["product", "boxes", "start", "bytes_per_value", "site_bpv_same_vars"]].to_dict("records"),
    }, indent=1, ensure_ascii=False) + "\n")


def run(measure: bool = False) -> pd.DataFrame:
    if measure or not (config.RESULTS / FULLGRID_CSV).exists():
        measure_all()
    df = estimate()
    write_site_json(df, config.ROOT / "site" / "src" / "storage.json")
    print(markdown(df))
    return df
