"""Figures (figures/*.png) and small site data files (results/site/*) from results/.

Never re-runs analysis: reads only results/*.csv|json and results/vectors/*.fgb.
"""

from __future__ import annotations

import json

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from swathgeo import config, plotstyle as ps

ps.apply()
RES = config.RESULTS
SITE = RES / "site"
SITE.mkdir(exist_ok=True)

SCENE_LABEL = {"modis_aqua_nadir": "MODIS Aqua, near nadir", "modis_terra_mid": "MODIS Terra, mid-swath",
               "modis_aqua_edge": "MODIS Aqua, swath edge", "viirs_n20_nadir": "VIIRS NOAA-20, nadir",
               "viirs_snpp_edge": "VIIRS SNPP, swath edge", "ecostress": "ECOSTRESS"}
SCENE_SENSOR = {k: k.split("_")[0] for k in SCENE_LABEL}
LOC_LABEL = {"naive_full": "Naive: full haversine argmin", "naive_bbox": "Naive: lat/lon box + argmin",
             "kdtree_scipy": "KD-tree (scipy, xyz)", "kdtree_pykdtree": "KD-tree (pykdtree, xyz)",
             "xarray_ndpoint_scipy_degrees": "xarray NDPointIndex (default, degrees)",
             "xarray_ndpoint_xoak_geoballtree": "xarray NDPointIndex + xoak BallTree",
             "xarray_ndpoint_xoak_s2": "xarray NDPointIndex + xoak S2",
             "s2_pys2index": "S2 point index (pys2index)", "s2_sorted": "S2 sorted cell ids",
             "h3_sorted": "H3 sorted cell ids", "analytic": "Analytic (orbit + scan geometry)"}
SCHEME_LABEL = {"naive_center": "Centre in polygon", "naive_square": "Nominal square",
                "voronoi": "Voronoi cell", "footprint": "Trig footprint",
                "footprint_pou": "Trig footprint (overlap-aware)", "psf": "PSF", "psf_pou": "PSF (overlap-aware)",
                "psf_lsq": "PSF-optimal (NNLS)"}
SCHEME_COLOR = {"naive_center": ps.CAT[7], "naive_square": ps.CAT[3], "voronoi": ps.CAT[6],
                "footprint": ps.CAT[4], "footprint_pou": ps.CAT[0], "psf": ps.CAT[5], "psf_pou": ps.CAT[1],
                "psf_lsq": ps.CAT[2]}
SENSORS = ["modis", "viirs", "ecostress"]


# ---------------------------------------------------------------------------------- Part A
def locate_figs():
    d = pd.read_csv(RES / "locate_bench.csv")
    d = d[d.locator != "xarray_sel_default"]
    d["sensor"] = d.scene.map(SCENE_SENSOR)
    # one scene per sensor for the headline (nadir scenes)
    head = d[d.scene.isin(["modis_aqua_nadir", "viirs_n20_nadir", "ecostress"])]
    order = [k for k in LOC_LABEL if k in set(head.locator)]
    fig, axes = plt.subplots(1, 3, figsize=(12.5, 4.6), sharey=True)
    for ax, (col, title) in zip(axes, [("build_s", "Build index"), ("q_site_s", "Query: 1 point"),
                                       ("q_points100_s", "Query: 100 points")]):
        for k, s in enumerate(SENSORS):
            sub = head[head.sensor == s].set_index("locator").reindex(order)
            y = np.arange(len(order)) + (k - 1) * 0.22
            v = sub[col].clip(lower=1e-5)
            if col == "build_s":  # methods without an index: nothing to build
                v = v.where(~sub.index.str.startswith("naive"))
            ax.scatter(v, y, s=26, color=ps.SENSOR_COLOR[s], label=s.upper() if s != "ecostress" else "ECOSTRESS",
                       zorder=3, edgecolor=ps.SURFACE, linewidth=0.8)
        ax.set_xscale("log")
        ax.set_title(title)
        ax.set_xlabel("seconds (log scale)")
        ax.grid(axis="y", visible=False)
        if col == "build_s":
            for i, o in enumerate(order):
                if o.startswith("naive"):
                    ax.text(0.02, i, "no index", transform=ax.get_yaxis_transform(), va="center",
                            color=ps.MUTED, fontsize=8.5)
    axes[0].set_yticks(np.arange(len(order)), [LOC_LABEL[o] for o in order])
    axes[0].invert_yaxis()
    axes[2].legend(loc="lower right")
    fig.suptitle("Locating pixels: index build vs. query time (near-nadir scenes)", x=0.01, ha="left",
                 fontweight="bold", color=ps.INK)
    ps.save(fig, "locate_times")

    # polygon queries
    pol = head[head.locator.isin([o for o in order if not str(o).startswith(("xarray", "s2_pys"))])]
    porder = [o for o in order if o in set(pol.locator)]
    fig, ax = plt.subplots(figsize=(7.5, 3.8))
    for k, s in enumerate(SENSORS):
        sub = pol[pol.sensor == s].set_index("locator").reindex(porder)
        y = np.arange(len(porder)) + (k - 1) * 0.22
        ax.scatter(sub["q_colusa_county_s"].clip(lower=1e-5), y, s=26, color=ps.SENSOR_COLOR[s],
                   label=s.upper() if s != "ecostress" else "ECOSTRESS", zorder=3, edgecolor=ps.SURFACE, linewidth=0.8)
    ax.set_xscale("log")
    ax.set_yticks(np.arange(len(porder)), [LOC_LABEL[o] for o in porder])
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("seconds (log scale)")
    ax.set_title("Polygon query (Colusa County, candidate pixels)")
    ax.legend(loc="lower right")
    ps.save(fig, "locate_polygon")

    # summary table for the site
    cols = ["scene", "locator", "n_pixels", "load_s", "build_s", "index_mb", "q_site_s", "q_points100_s",
            "q_colusa_county_s", "q_colusa_county_n", "points100_exact_frac", "points100_max_excess_m",
            "colusa_county_same_set", "q_site_pixels_read", "q_colusa_county_pixels_read"]
    d[[c for c in cols if c in d]].to_csv(SITE / "locate_summary.csv", index=False)


def analytic_figs():
    d = pd.read_csv(RES / "analytic_consistency.csv")
    plats = ["Terra", "Aqua", "SNPP", "NOAA-20", "ISS"]
    models = [("spec", "Documented constants", ps.CAT[3]), ("reference", "Calibrated on one 2024 scene", ps.CAT[0]),
              ("self", "Calibrated on the scene itself", ps.CAT[2])]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.0), sharey=True)
    for ax, (hm, title) in zip(axes, [("dem", "With terrain height of the target"),
                                      ("h0", "Without terrain height (h = 0)")]):
        for k, (m, lab, c) in enumerate(models):
            sub = d[(d.height == hm) & (d.model == m)]
            for i, p in enumerate(plats):
                v = sub[sub.platform == p].win_max.values
                x = i + (k - 1) * 0.25 + np.random.default_rng(i).uniform(-0.06, 0.06, len(v))
                ax.scatter(x, np.maximum(v, 0.5), s=16, color=c, label=lab if i == 0 else None, alpha=0.85,
                           edgecolor=ps.SURFACE, linewidth=0.5, zorder=3)
        ax.set_yscale("log")
        ax.set_xticks(range(len(plats)), plats)
        ax.set_title(title)
        ax.grid(axis="x", visible=False)
    axes[0].set_ylabel("search half-window needed (pixels)\nto contain the true nearest pixel, all targets")
    axes[0].set_yticks([1, 2, 3, 5, 10, 20, 50, 100], ["1", "2", "3", "5", "10", "20", "50", "100"])
    axes[1].legend(loc="upper left")
    fig.suptitle("Analytic locator: refinement window across 53 scenes (2013-2024, 6 regions)", x=0.01,
                 ha="left", fontweight="bold", color=ps.INK)
    ps.save(fig, "analytic_window")

    s = pd.read_csv(RES / "analytic_selfcal_constants.csv")
    s.to_csv(SITE / "analytic_selfcal_constants.csv", index=False)
    d.to_csv(SITE / "analytic_consistency.csv", index=False)


# ---------------------------------------------------------------------------------- Part B
def footprint_figs():
    v = pd.read_csv(RES / "footprint_validation.csv")
    t = pd.read_csv(RES / "footprint_theory.csv")
    fig, axes = plt.subplots(1, 3, figsize=(12.5, 3.8))
    scen = {"modis": "modis_aqua_nadir", "viirs": "viirs_n20_nadir", "ecostress": "ecostress"}
    for ax, s in zip(axes, SENSORS):
        th = t[t.sensor == s]
        sub = v[v.scene == scen[s]]
        unit = 1e3 if s != "ecostress" else 1.0
        u = "km" if s != "ecostress" else "m"
        ax.plot(th.scan_angle, th.W_s / unit, color=ps.CAT[0], label="along-scan, model")
        ax.plot(th.scan_angle, th.W_t / unit, color=ps.CAT[1], label="along-track, model")
        ax.scatter(np.abs(sub.scan_angle), sub.emp_s / unit, s=6, color=ps.CAT[0], alpha=0.35, linewidth=0,
                   label="along-scan, centre spacing in file")
        ax.scatter(np.abs(sub.scan_angle), sub.emp_t / unit, s=6, color=ps.CAT[1], alpha=0.35, linewidth=0,
                   label="along-track, line spacing in file")
        ax.set_title({"modis": "MODIS (705 km)", "viirs": "VIIRS M-band (829 km)", "ecostress": "ECOSTRESS (ISS ~415 km)"}[s])
        ax.set_xlabel("scan angle (deg)")
        ax.set_ylabel(f"pixel size ({u})")
        ax.set_ylim(bottom=0)
    axes[0].legend(loc="upper left", fontsize=7.5)
    fig.suptitle("Pixel size grows with scan angle: spherical-Earth trigonometry vs. geolocation files", x=0.01,
                 ha="left", fontweight="bold", color=ps.INK)
    ps.save(fig, "footprint_size")
    t.to_csv(SITE / "footprint_theory.csv", index=False)

    # maps of footprints for the 10 km circle
    polys = gpd.read_file(config.CONFIG / "targets/polygons.geojson").set_index("name").geometry
    circle = polys["circle_10km"]
    scenes = ["modis_aqua_nadir", "modis_aqua_edge", "viirs_n20_nadir", "viirs_snpp_edge"]
    fig, axes = plt.subplots(2, 4, figsize=(14, 7.2))
    for j, sc in enumerate(scenes):
        f = RES / "vectors" / f"{sc}__circle_10km__footprints.fgb"
        vfile = RES / "vectors" / f"{sc}__circle_10km__voronoi.fgb"
        if not f.exists():
            continue
        g = gpd.read_file(f)
        vor = gpd.read_file(vfile)
        cen = circle.centroid
        crs = f"+proj=laea +lat_0={cen.y} +lon_0={cen.x}"
        g, vor = g.to_crs(crs), vor.to_crs(crs)
        cg = gpd.GeoSeries([circle], crs=4326).to_crs(crs)
        # share of each pixel's own footprint (or Voronoi cell) credited to the polygon:
        # 1 = fully inside and not shared; ~0.5 inside a bow-tie overlap
        g["share"] = (g["w_footprint_pou"] / (g["W_s_m"] * g["W_t_m"])).clip(0, 1)
        vor["share"] = (vor["w_voronoi"] / vor.area).clip(0, 1)
        for i, (gg, lab) in enumerate([(g, "trig footprints (overlap-aware share)"), (vor, "Voronoi cells (share inside)")]):
            ax = axes[i, j]
            gg.plot(ax=ax, column="share", cmap=ps.seq_cmap, vmin=0, vmax=1, edgecolor=ps.INK2, linewidth=0.2,
                    alpha=0.9)
            cg.boundary.plot(ax=ax, color=ps.CAT[7], linewidth=1.5)
            ax.set_xlim(-16000, 16000)
            ax.set_ylim(-16000, 16000)
            ax.set_aspect("equal")
            ax.set_xticks([])
            ax.set_yticks([])
            ax.set_xlabel("")
            ax.set_ylabel("")
            ax.grid(False)
            for sp in ax.spines.values():
                sp.set_visible(False)
            if i == 0:
                ax.set_title(SCENE_LABEL[sc], fontsize=10)
            if j == 0:
                ax.set_ylabel(lab)
    sm = plt.cm.ScalarMappable(cmap=ps.seq_cmap, norm=plt.Normalize(0, 1))
    fig.colorbar(sm, ax=axes, shrink=0.5, label="share of the pixel credited to the polygon")
    fig.suptitle("Pixels around the 10 km circle (red). At the MODIS edge, overlapping scans share the ground (~0.5).",
                 x=0.01, ha="left", fontweight="bold", color=ps.INK)
    ps.save(fig, "footprint_maps")
    # small GeoJSON for the interactive map
    for sc in scenes + ["ecostress"]:
        for kind in ("footprints", "voronoi"):
            for pname in ("box_3km", "circle_10km"):
                f = RES / "vectors" / f"{sc}__{pname}__{kind}.fgb"
                if f.exists():
                    g = gpd.read_file(f)
                    if len(g) > 6000:
                        continue
                    g = g[["row", "col", "vza", "W_s_m", "W_t_m", "lst_K", "w_naive_center", "w_voronoi",
                           "w_footprint_pou", "w_psf_pou", "geometry"]]
                    g["geometry"] = g.geometry.set_precision(1e-6)
                    g.to_file(SITE / f"{sc}__{pname}__{kind}.geojson", driver="GeoJSON")


def areal_figs():
    a = pd.read_csv(RES / "areal_means.csv")
    schemes = ["naive_center", "naive_square", "voronoi", "footprint", "footprint_pou", "psf", "psf_lsq"]
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2), sharey=True)
    for ax, pname in zip(axes, ["box_3km", "circle_10km", "colusa_county"]):
        sub = a[a.polygon == pname].set_index("scene")
        scenes = [s for s in SCENE_LABEL if s in sub.index]
        for k, s in enumerate(schemes):
            dlt = sub.loc[scenes, f"mean_{s}"] - sub.loc[scenes, "mean_psf_pou"]
            y = np.arange(len(scenes)) + (k - 3) * 0.11
            ax.scatter(dlt, y, s=18, color=SCHEME_COLOR[s], label=SCHEME_LABEL[s], zorder=3,
                       edgecolor=ps.SURFACE, linewidth=0.5)
        ax.axvline(0, color=ps.AXIS, linewidth=1)
        ax.set_title({"box_3km": "3 km square", "circle_10km": "10 km circle", "colusa_county": "Colusa County (~3000 km²)"}[pname])
        ax.set_xlabel("mean LST minus PSF (overlap-aware) mean (K)")
        ax.grid(axis="y", visible=False)
    axes[0].set_yticks(np.arange(len(scenes)), [SCENE_LABEL[s] for s in scenes])
    axes[0].invert_yaxis()
    axes[2].legend(loc="lower right", fontsize=7.5)
    fig.suptitle("Real LST: how much does the pixel model change an areal mean?", x=0.01, ha="left",
                 fontweight="bold", color=ps.INK)
    ps.save(fig, "areal_real")
    a.to_csv(SITE / "areal_means.csv", index=False)


def synthetic_figs():
    s = pd.read_csv(RES / "synthetic_errors.csv")
    schemes = ["naive_center", "naive_square", "voronoi", "footprint", "footprint_pou", "psf_pou", "psf_lsq"]
    scenes = [x for x in SCENE_LABEL if x in set(s.scene)]
    fig, axes = plt.subplots(1, len(scenes), figsize=(14, 3.9), sharey=True)
    for ax, sc in zip(np.atleast_1d(axes), scenes):
        sub = s[s.scene == sc]
        for k, m in enumerate(schemes):
            r = sub.groupby("size_m")[f"err_{m}"].apply(lambda x: np.sqrt(np.nanmean(x ** 2)))
            ax.plot(r.index / 1e3, r.values, marker="o", markersize=4, color=SCHEME_COLOR[m], label=SCHEME_LABEL[m],
                    linewidth=1.6)
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xticks([2, 5, 10, 20], ["2", "5", "10", "20"])
        ax.set_title(SCENE_LABEL[sc], fontsize=9.5)
        ax.set_xlabel("polygon size (km)")
    np.atleast_1d(axes)[0].set_ylabel("RMSE of polygon mean LST (K)")
    np.atleast_1d(axes)[-1].legend(loc="upper right", fontsize=7)
    fig.suptitle("Synthetic truth (70 m ECOSTRESS field seen through each sensor's geometry + PSF)", x=0.01,
                 ha="left", fontweight="bold", color=ps.INK)
    ps.save(fig, "areal_synthetic")
    s.to_csv(SITE / "synthetic_errors.csv", index=False)


# ---------------------------------------------------------------------------------- Part C
PROFILE_LABEL = {"local": "Local disk", "zero_s3": "Proxy only (S3 API)", "zero_http": "Proxy only (HTTP)",
                 "s3_in_region": "S3 in-region", "s3_cross_region": "S3 cross-region",
                 "https_earthdata": "Earthdata HTTPS", "nccs_portal": "NCCS portal"}
READER_COLOR = {"h5py": ps.CAT[0], "h5py_blockcache": ps.CAT[6], "h5py_ros3": "#52514e", "xarray_h5netcdf": ps.CAT[2],
                "gdal": ps.CAT[3], "gdal_tuned": ps.CAT[1], "pyhdf": ps.CAT[4], "download_then_read": ps.CAT[7],
                "icechunk_virtual": ps.CAT[5], "icechunk_virtual_retry": "#0d366b"}


def read_figs():
    if not (RES / "read_bench.csv").exists():
        return
    r = pd.read_csv(RES / "read_bench.csv")
    ok = r[r.seconds.notna()]
    profs = [p for p in PROFILE_LABEL if p in set(r.profile) and not p.startswith("zero")]
    for task, title in [("window_site", "33 × 33 pixel window (one site)"),
                        ("window_poly", "County-sized window"), ("full", "Full granule (lat, lon, LST)")]:
        fig, axes = plt.subplots(1, 3, figsize=(13.5, 3.9), sharey=True)
        for ax, s in zip(axes, SENSORS):
            sub = ok[(ok.task == task) & (ok.sensor == s)]
            readers = [x for x in READER_COLOR if x in set(sub.reader)]
            for k, rd in enumerate(readers):
                for i, p in enumerate(profs):
                    v = sub[(sub.reader == rd) & (sub.profile == p)].seconds.values
                    if len(v) == 0:
                        continue
                    y = i + (k - (len(readers) - 1) / 2) * 0.1
                    ax.scatter(v, np.full(len(v), y), s=9, color=READER_COLOR[rd], alpha=0.35, linewidth=0)
                    ax.scatter(np.median(v), y, s=26, color=READER_COLOR[rd], edgecolor=ps.SURFACE, linewidth=0.6,
                               zorder=3, label=rd if i == 0 else None)
            ax.set_xscale("log")
            ax.set_title({"modis": "MODIS (HDF4)", "viirs": "VIIRS (NetCDF4/HDF5)", "ecostress": "ECOSTRESS (HDF5)"}[s])
            ax.set_xlabel("seconds (log)")
            ax.grid(axis="y", visible=False)
            ax.legend(loc="lower right", fontsize=7)
        axes[0].set_yticks(range(len(profs)), [PROFILE_LABEL[p] for p in profs])
        axes[0].invert_yaxis()
        fig.suptitle(f"Read time: {title}. Big dots = median, small = repetitions; failures omitted", x=0.01,
                     ha="left", fontweight="bold", color=ps.INK)
        ps.save(fig, f"read_{task}")
    r.to_csv(SITE / "read_bench.csv", index=False)
    if (RES / "virtual_build.csv").exists():
        pd.read_csv(RES / "virtual_build.csv").to_csv(SITE / "virtual_build.csv", index=False)
    (SITE / "net_profiles.json").write_text(json.dumps(config.load_toml("net_profiles.toml")["profile"]))


if __name__ == "__main__":
    import sys

    steps = sys.argv[1:] or ["locate", "analytic", "footprint", "areal", "synthetic", "read"]
    for st in steps:
        try:
            {"locate": locate_figs, "analytic": analytic_figs, "footprint": footprint_figs, "areal": areal_figs,
             "synthetic": synthetic_figs, "read": read_figs}[st]()
            print("ok", st)
        except FileNotFoundError as e:
            print("skip", st, e)
