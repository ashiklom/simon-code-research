"""Explanatory diagrams for the analytic locator (Part A methods page).

Schematic figures, not data plots; numbers come from the calibrated constants in
results/analytic_models.json. Output: figures/diagram_*.png
"""

from __future__ import annotations

import json

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Arc, Circle, FancyArrowPatch, Polygon, Rectangle

from swathgeo import analytic as an
from swathgeo import config, plotstyle as ps

ps.apply()
M = json.loads((config.RESULTS / "analytic_models.json").read_text())
INK, INK2, MUTED = ps.INK, ps.INK2, ps.MUTED
BLUE, ORANGE, GREEN, RED, VIOLET = ps.CAT[0], ps.CAT[1], ps.CAT[2], ps.CAT[7], ps.CAT[6]
AXIS_C = ps.AXIS


def arrow(ax, p, q, color=INK, lw=1.6, style="-|>", ms=12, **kw):
    ax.add_patch(FancyArrowPatch(p, q, arrowstyle=style, mutation_scale=ms, color=color, lw=lw, **kw))


def bare(ax):
    ax.set_aspect("equal")
    ax.axis("off")


def label(ax, xy, text, color=INK, **kw):
    kw.setdefault("ha", "center")
    kw.setdefault("va", "center")
    ax.text(*xy, text, color=color, fontsize=kw.pop("fs", 10), **kw)


# --------------------------------------------------------------------------------------
def fig_ecef():
    """ECEF coordinates: what a position vector is, and lat/lon/h -> (X, Y, Z)."""
    fig, ax = plt.subplots(figsize=(6.4, 5.2))
    bare(ax)
    R = 1.0
    ax.add_patch(Circle((0, 0), R, facecolor="#eef4fb", edgecolor=AXIS_C, lw=1.2))
    ax.add_patch(Arc((0, 0), 2 * R, 0.55 * R, theta1=180, theta2=360, color=MUTED, lw=1))  # equator (front)
    ax.add_patch(Arc((0, 0), 2 * R, 0.55 * R, theta1=0, theta2=180, color=MUTED, lw=0.8, ls=(0, (1, 2))))
    # axes (oblique projection: X toward viewer-left, Y right, Z up)
    O = np.array([0.0, 0.0])
    ex, ey, ez = np.array([-0.55, -0.35]), np.array([1.0, 0.0]), np.array([0.0, 1.0])
    for v, name, off in [(ex, "X  (0°N, 0°E)", 1.62), (ey, "Y  (0°N, 90°E)", 1.85), (ez, "Z  (North Pole)", 1.62)]:
        arrow(ax, O, O + 1.45 * v, color=INK2, lw=1.2)
        label(ax, O + off * v, name, color=INK2, fs=9)
    # target T on the surface and satellite S above it
    T = 0.62 * ey + 0.55 * ez + 0.25 * ex
    S = 1.55 * (0.45 * ey + 0.62 * ez + 0.45 * ex) / np.linalg.norm(0.45 * ey + 0.62 * ez + 0.45 * ex)
    arrow(ax, O, T, color=GREEN, lw=2)
    arrow(ax, O, S, color=BLUE, lw=2)
    arrow(ax, S, T, color=ORANGE, lw=2)
    ax.plot(*T, "o", color=GREEN, ms=7, zorder=5)
    ax.plot(*S, "s", color=BLUE, ms=8, zorder=5)
    label(ax, T + [0.13, -0.08], "T  target", color=GREEN, ha="left")
    label(ax, S + [0.12, 0.05], "S  satellite", color=BLUE, ha="left")
    label(ax, (S + T) / 2 + [0.18, 0.06], "line of sight\nu = (T − S)/|T − S|", color=ORANGE, ha="left", fs=9)
    label(ax, O + [-0.05, -0.12], "Earth's centre", color=INK2, fs=8.5)
    ax.set_xlim(-1.35, 2.2)
    ax.set_ylim(-1.15, 1.8)
    ax.set_title("ECEF: Earth-Centred, Earth-Fixed coordinates (metres)", loc="left")
    fig.text(0.02, 0.01, "Axes rotate with the Earth. A point at geodetic latitude φ, longitude λ, height h:\n"
             "X = (N + h) cos φ cos λ,  Y = (N + h) cos φ sin λ,  Z = (N(1 − e²) + h) sin φ"
             "   (WGS84; N = a / √(1 − e² sin²φ))", fontsize=8.5, color=INK2)
    ps.save(fig, "diagram_ecef")


# --------------------------------------------------------------------------------------
def fig_scan_plane():
    """Cross-section in the scan plane: scan angle theta, view zenith eta, slant range r."""
    fig, ax = plt.subplots(figsize=(7.2, 5.0))
    bare(ax)
    R, h = 6.0, 1.6  # schematic, not to scale
    t = np.linspace(np.radians(60), np.radians(120), 200)
    ax.plot(R * np.cos(t), R * np.sin(t) - R, color=INK2, lw=1.5)
    ax.fill_between(R * np.cos(t), R * np.sin(t) - R, -1.6, color="#eef4fb", lw=0)
    S = np.array([0.0, h])
    N = np.array([0.0, 0.0])
    beta = np.radians(17)  # Earth-central angle to the target
    T = np.array([R * np.sin(beta), R * np.cos(beta) - R])
    up_T = T - np.array([0, -R])
    up_T /= np.linalg.norm(up_T)
    ax.plot(*S, "s", color=BLUE, ms=9, zorder=5)
    ax.plot(*T, "o", color=GREEN, ms=8, zorder=5)
    ax.plot(*N, "o", color=INK2, ms=5, zorder=5)
    ax.plot([0, 0], [h, 0], color=INK2, lw=1.2, ls=(0, (4, 3)))
    arrow(ax, S, T, color=ORANGE, lw=2)
    ax.plot([T[0], T[0] + 1.6 * up_T[0]], [T[1], T[1] + 1.6 * up_T[1]], color=INK2, lw=1.2, ls=(0, (4, 3)))
    # angles
    th = np.degrees(np.arctan2(T[0] - S[0], -(T[1] - S[1])))
    ax.add_patch(Arc(S, 1.3, 1.3, theta1=270, theta2=270 + th, color=VIOLET, lw=2))
    label(ax, S + [0.36, -0.85], "θ", color=VIOLET, fs=13)
    los_dir = (S - T) / np.linalg.norm(S - T)
    a1 = np.degrees(np.arctan2(up_T[1], up_T[0]))
    a2 = np.degrees(np.arctan2(los_dir[1], los_dir[0]))
    ax.add_patch(Arc(T, 1.2, 1.2, theta1=min(a1, a2), theta2=max(a1, a2), color=RED, lw=2))
    label(ax, T + [-0.15, 0.78], "η", color=RED, fs=13)
    label(ax, S + [-0.15, 0.3], "S  satellite (height h)", color=BLUE, ha="right")
    label(ax, N + [-0.15, -0.3], "nadir point", color=INK2, ha="right", fs=9)
    label(ax, T + [0.15, -0.3], "T  target", color=GREEN, ha="left")
    label(ax, (S + T) / 2 + [0.25, 0.15], "slant range r", color=ORANGE, ha="left", fs=9.5)
    label(ax, T + 1.75 * up_T + [-0.1, 0.05], "local vertical", color=INK2, ha="right", fs=8.5)
    label(ax, (3.6, 1.55), "θ  scan angle: LOS angle from nadir,\n    measured at the satellite\n"
                           "η  view zenith angle: the same LOS,\n    measured at the ground (η > θ:\n"
                           "    Earth curvature)", color=INK, ha="left", va="top", fs=9)
    ax.set_xlim(-3.2, 7.4)
    ax.set_ylim(-1.0, 2.3)
    ax.set_title("The scan plane (cross-track cross-section, not to scale)", loc="left")
    ps.save(fig, "diagram_scan_plane")


# --------------------------------------------------------------------------------------
def fig_scans_from_above():
    """Top view: along-track x, cross-track y, scans of N_det lines, line/sample indexing, phi."""
    fig, ax = plt.subplots(figsize=(8.4, 5.0))
    bare(ax)
    nd = 4  # detectors drawn per scan (MODIS has 10, VIIRS 16, ECOSTRESS 128)
    W, hgt = 9.0, 0.5
    for k in range(3):
        y0 = k * nd * hgt
        for d in range(nd):
            ax.add_patch(Rectangle((-W / 2, y0 + d * hgt), W, hgt, facecolor=[BLUE, ORANGE, GREEN][k],
                                   alpha=0.12 + 0.05 * (d % 2), edgecolor="white", lw=0.8))
        label(ax, (W / 2 + 0.25, y0 + nd * hgt / 2), f"scan k{'+' + str(k - 1) if k > 1 else ('' if k == 1 else '−1')}"
              .replace("k+0", "k"), color=[BLUE, ORANGE, GREEN][k], ha="left", fs=9.5)
    # sample ticks along one line
    for j in range(0, 19):
        x = -W / 2 + (j + 0.5) * W / 19
        ax.plot([x, x], [nd * hgt, nd * hgt + hgt * 0.25], color=INK2, lw=0.6)
    label(ax, (0, 3 * nd * hgt + 0.35), "sample j = 0, 1, …, N_samp−1  (across track, one mirror sweep)", fs=9)
    # detector labels for the middle scan
    for d in range(nd):
        label(ax, (-W / 2 - 0.15, nd * hgt + (d + 0.5) * hgt), f"d={d}", color=INK2, ha="right", fs=8.5)
    label(ax, (-W / 2 - 1.15, nd * hgt + nd * hgt / 2), "line\n= k·N_det + d", color=INK2, ha="right", fs=8.5)
    # axes
    arrow(ax, (-W / 2 - 2.6, -0.6), (-W / 2 - 2.6, 1.6), color=INK)
    arrow(ax, (-W / 2 - 2.6, -0.6), (-W / 2 - 0.4, -0.6), color=INK)
    label(ax, (-W / 2 - 2.6, 1.85), "x  along-track\n(direction of flight)", fs=8.5)
    label(ax, (-W / 2 - 1.5, -0.85), "y  cross-track", fs=8.5)
    # target and phi
    T = np.array([2.1, nd * hgt + 3.55 * hgt])
    c = np.array([2.1, nd * hgt + nd * hgt / 2])
    ax.plot(*T, "o", color=RED, ms=7, zorder=5)
    ax.plot([-W / 2, W / 2], [c[1], c[1]], color=ORANGE, lw=1.2, ls=(0, (4, 3)))
    arrow(ax, (c[0] - 0.35, c[1]), (c[0] - 0.35, T[1]), color=RED, lw=1.4, style="<|-|>", ms=8)
    label(ax, (c[0] - 0.5, (c[1] + T[1]) / 2 + 0.05), "φ − φ₀ (angle seen from the satellite)", color=RED,
          ha="right", fs=8.5)
    label(ax, T + [0.2, 0.0], "target", color=RED, ha="left", fs=9)
    label(ax, (-W / 2 + 0.2, c[1] - 0.14), "centre of scan k's detector array (φ = φ₀)", color=ORANGE, ha="left", fs=8)
    ax.set_xlim(-W / 2 - 4.0, W / 2 + 1.6)
    ax.set_ylim(-1.1, 3 * nd * hgt + 0.7)
    ax.set_title("From above: each mirror sweep (a scan) images N_det lines at once", loc="left")
    ps.save(fig, "diagram_scans")


# --------------------------------------------------------------------------------------
def fig_frames():
    """Orbital frame (x, y, z) and why inertial velocity, not ECEF velocity, defines x."""
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.3), gridspec_kw={"width_ratios": [1, 1.1]})
    ax = axes[0]
    bare(ax)
    S = np.array([0.0, 0.0])
    arrow(ax, S, (2.0, 0.0), color=BLUE)
    arrow(ax, S, (0.0, -2.0), color=ORANGE)
    arrow(ax, S, (-1.1, -0.9), color=GREEN)
    ax.plot(*S, "s", color=BLUE, ms=9)
    label(ax, (2.15, 0.15), "x  along-track\n(velocity direction)", color=BLUE, ha="left", fs=9)
    label(ax, (0.12, -2.15), "z  nadir (down)", color=ORANGE, ha="left", fs=9)
    label(ax, (-1.2, -1.05), "y = z × x\ncross-track", color=GREEN, ha="right", fs=9)
    ax.text(-2.4, 1.3, "Roll: rotation about x\nPitch: about y\nYaw: about z", color=INK2, fontsize=9, va="top")
    ax.set_xlim(-2.6, 4.0)
    ax.set_ylim(-2.6, 1.5)
    ax.set_title("The spacecraft frame used for the angles", loc="left")

    ax = axes[1]
    bare(ax)
    O = np.array([0.0, 0.0])
    v_ecef = np.array([2.6, 0.0])
    w = np.array([0.0, 0.6])  # omega x S, eastward Earth rotation term (exaggerated)
    arrow(ax, O, v_ecef, color=MUTED, lw=1.8)
    arrow(ax, v_ecef, v_ecef + w, color=RED, lw=1.8)
    arrow(ax, O, v_ecef + w, color=BLUE, lw=2.2)
    ang = np.degrees(np.arctan2(w[1], v_ecef[0]))
    ax.add_patch(Arc(O, 1.6, 1.6, theta1=0, theta2=ang, color=VIOLET, lw=1.6))
    label(ax, (0.95, 0.12), "≈3.5°", color=VIOLET, fs=9, ha="left")
    label(ax, (1.3, -0.25), "v_ECEF: velocity relative to\nthe rotating Earth (in the file)", color=INK2, fs=8.5, va="top")
    label(ax, v_ecef + w / 2 + [0.12, 0], "ω × S\n(Earth rotation)", color=RED, fs=8.5, ha="left")
    label(ax, (v_ecef + w) / 2 + [-0.35, 0.42], "v_inertial = v_ECEF + ω × S\n(the spacecraft is aligned with this)",
          color=BLUE, fs=8.5)
    ax.set_xlim(-0.4, 4.2)
    ax.set_ylim(-1.2, 1.6)
    ax.set_title("x must follow the inertial velocity", loc="left")
    fig.text(0.02, 0.01, "Using v_ECEF would yaw the frame by up to ~3.5° (at the equator) and shift swath-edge "
             "pixels by tens of km along-track.", fontsize=8.5, color=INK2)
    ps.save(fig, "diagram_frames")


# --------------------------------------------------------------------------------------
def fig_index_maps():
    """theta -> sample j (MODIS linear, VIIRS piecewise) and phi -> detector d."""
    fig, axes = plt.subplots(1, 3, figsize=(12.5, 3.9))
    th = np.radians(np.linspace(-56, 56, 500))
    for name, c in [("Aqua", BLUE), ("NOAA-20", ORANGE)]:
        m = M[name]
        model = an.SensorModel(**{k: (tuple(v) if k == "rpy" else v) for k, v in m.items() if k in
                                  an.SensorModel.__dataclass_fields__})
        lim = 55 if name == "Aqua" else 56.06
        t = th[np.abs(np.degrees(th)) <= lim]
        axes[0].plot(np.degrees(t), model.theta_to_sample(t), color=c,
                     label={"Aqua": "MODIS: j = j_c + s·θ/α (linear)", "NOAA-20": "VIIRS: through aggregation zones"}[name])
    for b in (31.59, 44.68):
        for sgn in (-1, 1):
            axes[0].axvline(sgn * b, color=AXIS_C, lw=0.8)
    axes[0].set_xlabel("scan angle θ (deg)")
    axes[0].set_ylabel("sample index j")
    axes[0].legend(fontsize=8, loc="upper right")
    axes[0].set_title("Sample from scan angle")

    # VIIRS native -> aggregated
    n = np.linspace(0, 6304, 600)
    axes[1].plot(n, an.viirs_native_to_agg(n), color=ORANGE)
    for e in an.VIIRS_NAT_EDGES[1:-1]:
        axes[1].axvline(e, color=AXIS_C, lw=0.8)
    for x, txt in [(320, "1:1"), (1008, "2:1"), (3152, "3:1"), (5296, "2:1"), (5984, "1:1")]:
        axes[1].text(x, 3300, txt, ha="center", fontsize=8.5, color=INK2)
    axes[1].set_xlabel("VIIRS native sample n (6304 per scan)")
    axes[1].set_ylabel("aggregated sample j (3200)")
    axes[1].set_ylim(0, 3500)
    axes[1].set_title("VIIRS on-board aggregation")

    m = M["Aqua"]
    phi = np.linspace(-9e-3, 9e-3, 100)
    d = m["d_c"] + (phi - m["phi0"]) / m["delta"]
    axes[2].plot(phi * 1e3, d, color=BLUE)
    axes[2].axhspan(-0.5, m["n_det"] - 0.5, color=BLUE, alpha=0.08)
    axes[2].axvline(m["phi0"] * 1e3, color=AXIS_C, lw=0.8)
    axes[2].text(m["phi0"] * 1e3 + 0.3, 11.3, "φ₀", color=INK2)
    axes[2].text(-8.5, 4.5, "inside this scan's\ndetector array\n(d = 0 … N_det−1)", fontsize=8.5, color=BLUE)
    axes[2].set_xlabel("along-track angle φ (mrad)")
    axes[2].set_ylabel("detector d")
    axes[2].set_title("Detector from along-track angle (MODIS)")
    fig.suptitle("Turning angles into array indices", x=0.01, ha="left", fontweight="bold", color=INK)
    fig.tight_layout()
    ps.save(fig, "diagram_index_maps")


# --------------------------------------------------------------------------------------
def fig_timing():
    """Why the satellite position is moved for each sample: t = t_scan + t_off + s*kappa*theta."""
    fig, ax = plt.subplots(figsize=(8.6, 2.9))
    fig.subplots_adjust(bottom=0.32)
    m = M["Aqua"]
    th = np.radians(np.linspace(-55, 55, 7))
    dt = m["t_off"] + m["s"] * m["kappa"] * th
    v = 6.7  # km/s ground speed of the sub-satellite point (approx.)
    ax.axhline(0, color=AXIS_C, lw=1)
    ax.plot(dt * v, np.zeros_like(dt), "o", color=BLUE, ms=7, zorder=3)
    for x, t, a in zip(dt * v, dt, np.degrees(th)):
        ax.annotate(f"θ={a:+.0f}°\nΔt={t:+.2f} s", (x, 0), xytext=(0, 14), textcoords="offset points",
                    ha="center", fontsize=8, color=INK2)
    ax.plot(0, 0, "s", color=ORANGE, ms=9, zorder=4)
    ax.annotate("satellite position\nat t_scan (from the file)", (0, 0), xytext=(0, -38), textcoords="offset points",
                ha="center", fontsize=8.5, color=ORANGE)
    span = (dt.max() - dt.min()) * v
    ax.set_xlabel("satellite position along its orbit relative to t_scan (km)")
    ax.set_yticks([])
    ax.set_ylim(-1.3, 1.1)
    ax.grid(False)
    ax.spines["left"].set_visible(False)
    ax.set_title(f"MODIS Aqua: the satellite moves ~{span:.1f} km while the mirror sweeps the Earth view", loc="left")
    fig.text(0.01, 0.02, f"Each sample is seen at t = t_scan + t_off + s·κ·θ, with t_off = {m['t_off']:+.3f} s and "
             f"κ = {m['kappa']:.3f} s/rad (calibrated). The position S is moved to that time before the angles "
             "are recomputed.", fontsize=8.5, color=INK2)
    ps.save(fig, "diagram_timing")


# --------------------------------------------------------------------------------------
def fig_refine():
    """Prediction, overlapping scans, and the refinement windows."""
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    bare(ax)
    nd, ns, kw = 5, 13, 2  # detectors drawn per scan, samples drawn, window half-width k
    scans = [(0.0, BLUE, "scan k"), (3.4, ORANGE, "scan k+1")]  # k+1 overlaps k (bow-tie)
    for dy, c, name in scans:
        for d in range(nd):
            for j in range(ns):
                ax.add_patch(Rectangle((j, dy + d), 1, 1, facecolor=c, alpha=0.13, edgecolor=c, lw=0.4))
        label(ax, (ns + 0.3, dy + nd / 2), name, color=c, ha="left", fs=9.5)
    label(ax, (ns + 0.3, 4.2), "overlap\n(bow-tie)", color=INK2, ha="left", fs=8)
    pred = np.array([6.4, 3.9])  # fractional (sample, line) prediction in scan k
    best = [(int(pred[0]) - kw, int(pred[1]) - kw), (int(pred[0]) - kw, 3.4)]
    for (x0, y0), (_, c, _) in zip(best, scans):
        ax.add_patch(Rectangle((x0, y0), 2 * kw + 1, 2 * kw + 1 if y0 < 3 else min(2 * kw + 1, nd),
                               facecolor="none", edgecolor=c, lw=2.2))
    ax.plot(*pred, "x", color=RED, ms=11, mew=2.5, zorder=5)
    ax.plot(5.5, 4.9, "o", color=GREEN, ms=8, zorder=5)
    ax.annotate("analytic prediction\n(fractional line, sample)", pred, xytext=(ns + 0.3, 1.0), color=RED,
                fontsize=8.5, ha="left", arrowprops=dict(arrowstyle="-", color=RED, lw=0.8))
    ax.annotate("nearest pixel centre\n(the answer)", (5.5, 4.9), xytext=(-3.3, 6.6), color=GREEN, fontsize=8.5,
                ha="left", arrowprops=dict(arrowstyle="-", color=GREEN, lw=0.8))
    ax.annotate(f"(2k+1) × (2k+1) window\nin scan k (here k = {kw})", (best[0][0], 2.0), xytext=(-3.3, 0.6),
                color=BLUE, fontsize=8.5, ha="left", arrowprops=dict(arrowstyle="-", color=BLUE, lw=0.8))
    label(ax, (ns / 2, -0.9), "Only these windows of the real latitude/longitude are read; the pixel whose centre is "
                              "closest\nto the target wins. Each scan that could contain the target gets its own window.",
          fs=8.5, color=INK2)
    ax.set_xlim(-3.4, ns + 3.2)
    ax.set_ylim(-1.6, 8.6)
    ax.set_title("Refinement: from a predicted position to the exact pixel", loc="left")
    ps.save(fig, "diagram_refine")


if __name__ == "__main__":
    fig_ecef()
    fig_scan_plane()
    fig_scans_from_above()
    fig_frames()
    fig_index_maps()
    fig_timing()
    fig_refine()
    print("ok")
