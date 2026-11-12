"""Static figures for the README (results/figures/*.png)."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from . import config  # noqa: E402
from . import sites as sitesmod  # noqa: E402
from .products import registry  # noqa: E402

OUT = config.RESULTS / "figures"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e8e7e2"
TIER_COLORS = {1: "#2a78d6", 2: "#eb6834", 3: "#1baf7a"}
TIER_LABELS = {1: "USCRN", 2: "Other high-quality stations", 3: "Station-remote points"}


def _style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=INK2, labelsize=9)


def site_map(name: str = "all"):
    df = sitesmod.load(name)
    fig, ax = plt.subplots(figsize=(9, 5.2), dpi=150)
    conus = df[(df.lon > -126) & (df.lon < -65) & (df.lat > 24) & (df.lat < 50)]
    for tier in (3, 2, 1):
        d = conus[conus.tier == tier]
        ax.scatter(d.lon, d.lat, s=22 if tier == 1 else 18, c=TIER_COLORS[tier], edgecolors="white", linewidths=0.8,
                   label=f"{TIER_LABELS[tier]} ({(df.tier == tier).sum()})", zorder=3)
    ax.set_xlim(-126, -66)
    ax.set_ylim(24, 50)
    ax.set_aspect(1.25)
    ax.grid(color=GRID, lw=0.6)
    _style(ax)
    ax.legend(frameon=False, fontsize=9, loc="lower left")
    ak_hi = (df.lon < -126) | (df.lat > 50)
    ax.set_title(f"Comparison sites (CONUS shown; {ak_hi.sum()} more in Alaska and Hawaii)", fontsize=11, color=INK, loc="left")
    fig.tight_layout()
    fig.savefig(OUT / "sites_map.png")
    plt.close(fig)


def skill_heatmap(metrics: pd.DataFrame, metric: str = "r", window: str = "common", network: str = "USCRN"):
    obs_vars = ["tair", "tmax", "tmin", "pr", "sw", "rh", "tdew", "vpd", "tsurf", "wind", "sm05", "ts05"]
    m = metrics[(metrics.network == network) & (metrics.scale == "daily") & (metrics.window == window) & (metrics.method == "bilinear")
                & ~metrics["var"].str.endswith("_adj") & metrics.obs_var.isin(obs_vars)]
    col = "anom_r" if metric == "anom_r" else metric
    t = m.pivot_table(index="product", columns="obs_var", values=col, aggfunc="median")
    t = t.reindex(columns=[c for c in obs_vars if c in t.columns])
    order = [p for p in registry.names() if p in t.index]
    t = t.reindex(order)
    titles = {p: registry.get(p).title for p in order}
    fig, ax = plt.subplots(figsize=(1.0 + 0.62 * t.shape[1], 0.6 + 0.36 * t.shape[0]), dpi=150)
    vals = t.values.astype(float)
    if metric == "bias":
        lim = np.nanmax(np.abs(vals), axis=0)
        norm = vals / np.where(lim > 0, lim, 1)
        cmap = matplotlib.colors.LinearSegmentedColormap.from_list("div", ["#2a78d6", "#f0efec", "#e34948"])
        im = ax.imshow(norm, cmap=cmap, vmin=-1, vmax=1, aspect="auto")
    else:
        cmap = matplotlib.colors.LinearSegmentedColormap.from_list("seq", ["#f0efec", "#2a78d6", "#104281"])
        im = ax.imshow(vals, cmap=cmap, vmin=0.5, vmax=1.0, aspect="auto")
    for i in range(vals.shape[0]):
        for j in range(vals.shape[1]):
            if np.isfinite(vals[i, j]):
                v = im.norm(im.get_array()[i, j])
                ax.text(j, i, f"{vals[i, j]:.2f}", ha="center", va="center", fontsize=7.5, color="white" if v > 0.75 or (metric == "bias" and abs(norm[i, j]) > 0.75) else INK)
    ax.set_xticks(range(t.shape[1]), t.columns, fontsize=8.5, color=INK2)
    ax.set_yticks(range(t.shape[0]), [titles[p] for p in t.index], fontsize=8.5, color=INK2)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title(f"Median daily {metric} at {network} sites ({window} window, bilinear)", fontsize=10, color=INK, loc="left")
    fig.tight_layout()
    fig.savefig(OUT / f"heatmap_{metric}_{network}_{window}.png")
    plt.close(fig)


def bias_distributions(metrics: pd.DataFrame, network: str = "USCRN", window: str = "common"):
    m = metrics[(metrics.network == network) & (metrics.scale == "daily") & (metrics.window == window) & (metrics.method == "bilinear")]
    vars_ = [("tmax", "Daily max temperature bias (°C)"), ("tmin", "Daily min temperature bias (°C)"), ("pr", "Precipitation total ratio (product / station)")]
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.6), dpi=150, sharey=True)
    order = [p for p in registry.names() if p in set(m["product"])]
    for ax, (v, title) in zip(axes, vars_):
        d = m[(m.obs_var == v) & (m["var"] == v)]
        col = "ratio" if v == "pr" else "bias"
        data = [d[d["product"] == p][col].dropna().values for p in order]
        ax.boxplot(data, vert=False, widths=0.55, showfliers=False, medianprops={"color": "#2a78d6", "lw": 2},
                   boxprops={"color": INK2}, whiskerprops={"color": INK2}, capprops={"color": INK2})
        ax.axvline(1 if v == "pr" else 0, color=INK, lw=0.8)
        ax.set_yticks(range(1, len(order) + 1), [registry.get(p).title for p in order], fontsize=8)
        ax.set_title(title, fontsize=9.5, color=INK, loc="left")
        ax.grid(axis="x", color=GRID, lw=0.6)
        _style(ax)
    fig.suptitle(f"Distribution across {network} sites ({window} window); boxes = interquartile range", fontsize=10, x=0.01, ha="left")
    fig.tight_layout()
    fig.savefig(OUT / f"bias_{network}_{window}.png")
    plt.close(fig)


def run(metrics_name: str = "all"):
    OUT.mkdir(parents=True, exist_ok=True)
    site_map("all")
    f = config.DATA / "results" / f"metrics_{metrics_name}.parquet"
    if f.exists():
        m = pd.read_parquet(f)
        for metric in ("r", "bias"):
            skill_heatmap(m, metric)
        bias_distributions(m)
    return sorted(OUT.glob("*.png"))
