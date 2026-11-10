"""Shared matplotlib style (validated reference palette from the dataviz guidelines).

Categorical hues are assigned in fixed order and follow the entity (e.g. a sensor or a
method always gets the same colour across figures)."""

from __future__ import annotations

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
DIV_MID = "#f0efec"

SENSOR_COLOR = {"modis": CAT[0], "viirs": CAT[1], "ecostress": CAT[2]}

seq_cmap = LinearSegmentedColormap.from_list("seq_blue", SEQ)
div_cmap = LinearSegmentedColormap.from_list("div_bluered", ["#184f95", "#6da7ec", DIV_MID, "#ec835a", "#b32f2f"])


def apply():
    mpl.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "axes.titlecolor": INK,
        "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
        "grid.color": GRID, "grid.linewidth": 0.6, "grid.linestyle": "-",
        "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelcolor": INK2, "ytick.labelcolor": INK2,
        "font.family": "sans-serif", "font.size": 9.5, "axes.titlesize": 11, "axes.titleweight": "bold",
        "axes.titlelocation": "left", "legend.frameon": False, "legend.fontsize": 8.5,
        "lines.linewidth": 2.0, "lines.markersize": 5, "axes.prop_cycle": mpl.cycler(color=CAT),
        "figure.dpi": 110, "savefig.dpi": 160, "savefig.bbox": "tight",
    })


def save(fig, name):
    from . import config

    config.FIGURES.mkdir(exist_ok=True)
    fig.savefig(config.FIGURES / f"{name}.png")
    plt.close(fig)
