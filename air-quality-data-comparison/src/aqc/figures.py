"""Static figures for the README (results/figures/*.png), from the merged metrics table.

Colours follow the site's validated palette (site/src/style.css): sequential = one blue hue,
diverging = blue / warm-grey / red; values are printed in every heatmap cell.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

from . import config, sites as S

FIG = config.RESULTS / "figures"
BLUE, MID, RED = "#2a78d6", "#f0efec", "#e34948"
SEQ = LinearSegmentedColormap.from_list("seq", [MID, BLUE])
DIV = LinearSegmentedColormap.from_list("div", [BLUE, MID, RED])
TIER_COL = {1: "#2a78d6", 2: "#eb6834", 3: "#1baf7a", 4: "#6250d6"}
TIER_LAB = {1: "Tier 1: US reference (AQS, IMPROVE, CSN)", 2: "Tier 2: embassies, SPARTAN, OpenAQ reference",
            3: "Tier 3: low-cost sensors (Sensor.Community, AirGradient, AirQo)", 4: "Tier 4: station-remote points"}
ORDER = ["geoscf_v1", "geoscf_v2", "merra2", "merra2_cnn", "cams_eac4", "cams_fcst", "geosfp_aer", "merra2_gmi",
         "acag", "ghap", "ghap_m", "hrrr_smoke", "naqfc", "naqfc_bc", "haqes"]
VARS = ["pm25", "pm25_frm", "pm10", "o3", "o3_mda8", "no2"]
SPEC = ["spec_so4", "spec_no3", "spec_nh4", "spec_om", "spec_bc", "spec_dust", "spec_ss"]
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 110})


def _heat(ax, tab: pd.DataFrame, cmap, norm, fmt="{:.2f}", ncount=None):
    im = ax.imshow(tab.values.astype(float), cmap=cmap, norm=norm, aspect="auto")
    ax.set_xticks(range(tab.shape[1]), tab.columns, rotation=30, ha="right")
    ax.set_yticks(range(tab.shape[0]), tab.index)
    ax.tick_params(length=0)
    for sp in ax.spines.values():
        sp.set_visible(False)
    for i in range(tab.shape[0]):
        for j in range(tab.shape[1]):
            v = tab.values[i, j]
            if np.isfinite(v):
                txt = fmt.format(v)
                if ncount is not None and np.isfinite(ncount.values[i, j]):
                    txt += f"\n({int(ncount.values[i, j])})"
                ax.text(j, i, txt, ha="center", va="center", fontsize=7, color="#0b0b0b")
    return im


def sites_map(log=print):
    s = S.load()
    fig, ax = plt.subplots(figsize=(11, 5.2))
    try:
        from global_land_mask import globe
        lat = np.linspace(-60, 80, 281)
        lon = np.linspace(-180, 180, 721)
        LON, LAT = np.meshgrid(lon, lat)
        ax.contourf(LON, LAT, globe.is_land(LAT, LON).astype(float), levels=[0.5, 1.5], colors=["#e4e2dc"])
    except Exception:
        pass
    for t in (1, 4, 2, 3):
        d = s[s.tier == t]
        ax.scatter(d.lon, d.lat, s=6 if t == 1 else 16, c=TIER_COL[t], edgecolor="white", linewidth=0.4,
                   label=f"{TIER_LAB[t]} ({len(d)})", zorder=3)
    ax.set_xlim(-180, 180); ax.set_ylim(-58, 75); ax.set_aspect("equal")
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)
    h, lab = ax.get_legend_handles_labels()
    order = sorted(range(len(lab)), key=lambda i: lab[i])
    ax.legend([h[i] for i in order], [lab[i] for i in order], loc="lower left", frameon=False, fontsize=8)
    ax.set_title(f"Comparison sites ({len(s)})", loc="left")
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / "sites_map.png", bbox_inches="tight", dpi=150)
    plt.close(fig)


def heatmaps(m: pd.DataFrame, window: str = "common", log=print):
    m = m[(m.method == "bilinear") & (m.window == window)]
    for tier, scale in ((1, "daily"), (2, "daily"), (3, "daily"), (4, "monthly")):
        d = m[(m.tier == tier) & (m.scale == scale)]
        if d.empty:
            continue
        vars_ = [v for v in VARS if v in set(d["var"])]
        prods = [p for p in ORDER if p in set(d["product"])]
        r = d.groupby(["product", "var"])["r"].median().unstack().reindex(index=prods, columns=vars_)
        nmb = d.groupby(["product", "var"])["nmb"].median().unstack().reindex(index=prods, columns=vars_)
        n = d.groupby(["product", "var"]).size().unstack().reindex(index=prods, columns=vars_)
        fig, axes = plt.subplots(1, 2, figsize=(4 + 1.6 * len(vars_), 0.45 * len(prods) + 1.6))
        _heat(axes[0], r, SEQ, plt.Normalize(0.2, 0.95), ncount=n)
        axes[0].set_title(f"Median r ({scale})", loc="left")
        _heat(axes[1], nmb, DIV, TwoSlopeNorm(0, -1, 1))
        axes[1].set_title("Median normalized mean bias", loc="left")
        axes[1].set_yticklabels([])
        ref = "median of the other products" if tier == 4 else "observations"
        fig.suptitle(f"{TIER_LAB[tier]}: products vs {ref}, {window} window (n sites in brackets)", x=0.01,
                     ha="left", fontsize=10)
        fig.tight_layout()
        fig.savefig(FIG / f"heatmap_tier{tier}_{window}.png", bbox_inches="tight", dpi=150)
        plt.close(fig)
        log(f"[figures] heatmap tier {tier}")


def species(m: pd.DataFrame, window: str = "full", log=print):
    d = m[(m.method == "bilinear") & (m.window == window) & m["var"].isin(SPEC) & (m.scale == "daily")]
    if d.empty:
        return
    prods = [p for p in ORDER if p in set(d["product"])]
    vars_ = [v for v in SPEC if v in set(d["var"])]
    nmb = d.groupby(["product", "var"])["nmb"].median().unstack().reindex(index=prods, columns=vars_)
    r = d.groupby(["product", "var"])["r"].median().unstack().reindex(index=prods, columns=vars_)
    fig, axes = plt.subplots(1, 2, figsize=(4 + 1.3 * len(vars_) * 2, 0.45 * len(prods) + 1.6))
    _heat(axes[0], nmb.rename(columns=lambda c: c[5:]), DIV, TwoSlopeNorm(0, -1, 1.5))
    axes[0].set_title("Median normalized mean bias", loc="left")
    _heat(axes[1], r.rename(columns=lambda c: c[5:]), SEQ, plt.Normalize(0.2, 0.9))
    axes[1].set_title("Median r", loc="left"); axes[1].set_yticklabels([])
    fig.suptitle(f"PM2.5 components vs IMPROVE/CSN 24-h filters ({window} window, daily)", x=0.01, ha="left", fontsize=10)
    fig.tight_layout()
    fig.savefig(FIG / f"species_{window}.png", bbox_inches="tight", dpi=150)
    plt.close(fig)
    log("[figures] species")


def run(log=print):
    m = pd.read_parquet(config.DATA / "results" / "metrics_all.parquet")
    sites_map(log)
    heatmaps(m, "common", log)
    heatmaps(m, "full", log)
    species(m, "full", log)
