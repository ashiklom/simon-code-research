"""Markdown key-result tables for the README, from data/results/metrics_all.parquet.

Writes results/key_tables.md. All numbers are medians over sites, bilinear interpolation.
Usage: uv run python scripts/key_tables.py
"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
m = pd.read_parquet(ROOT / "data" / "results" / "metrics_all.parquet")
b = m[m.method == "bilinear"]

ORDER = ["ghap", "acag", "merra2_cnn", "naqfc_bc", "haqes", "naqfc", "hrrr_smoke", "geoscf_v1", "geoscf_v2",
         "geosfp_aer", "merra2", "merra2_gmi"]
LABEL = {"ghap": "GHAP ¹", "acag": "ACAG V6 ¹", "merra2_cnn": "MERRA-2 CNN ¹", "naqfc_bc": "NAQFC bias-corr. ¹",
         "haqes": "HAQES ¹", "naqfc": "NAQFC raw", "hrrr_smoke": "HRRR-Smoke", "geoscf_v1": "GEOS-CF v1",
         "geoscf_v2": "GEOS-CF v2", "geosfp_aer": "GEOS-FP", "merra2": "MERRA-2", "merra2_gmi": "MERRA-2 GMI"}


def cell(df, prod, var, stat, fmt="{:.2f}", scale="daily"):
    d = df[(df["product"] == prod) & (df["var"] == var) & (df.scale == scale)][stat].dropna()
    if len(d) < 5:
        return "–"
    s = fmt.format(d.median())
    return s if not s.startswith("-0.00") else "0.00"


def table(df, cols, title):
    lines = [f"**{title}**", "", "| Product | n | " + " | ".join(c[0] for c in cols) + " |",
             "|---|---|" + "---|" * len(cols)]
    for p in ORDER:
        row = [cell(df, p, var, stat, fmt, scale) for _, var, stat, fmt, scale in cols]
        if all(r == "–" for r in row):
            continue
        k = max(df[(df["product"] == p) & (df["var"] == var) & (df.scale == scale)][stat].notna().sum()
                for _, var, stat, _, scale in cols)
        lines.append(f"| {LABEL[p]} | {k} | " + " | ".join(row) + " |")
    n = df[df["var"] == cols[0][1]].site.nunique()
    return "\n".join(lines) + (f"\n\n_n: sites scored (largest over the columns; {n} sites with {cols[0][1]} in total); "
                                f"¹ uses surface monitors (see Dependence)._\n")


pct = "{:+.0%}"
out = []
t1 = b[(b.tier == 1) & (b.window == "common")]
out.append(table(t1, [
    ("PM2.5 r", "pm25", "r", "{:.2f}", "daily"), ("PM2.5 NMB", "pm25", "nmb", pct, "daily"),
    ("PM2.5 RMSE", "pm25", "rmse", "{:.1f}", "daily"), ("CSI >35", "pm25", "csi_35", "{:.2f}", "daily"),
    ("AQI cat. agree", "pm25", "aqi_agree", "{:.2f}", "daily"), ("Monthly PM2.5 r", "pm25", "r", "{:.2f}", "monthly"),
    ("O3 MDA8 r", "o3_mda8", "r", "{:.2f}", "daily"), ("O3 MDA8 NMB", "o3_mda8", "nmb", pct, "daily"),
    ("NO2 r", "no2", "r", "{:.2f}", "daily"), ("NO2 NMB", "no2", "nmb", pct, "daily")],
    "Tier 1 (US reference monitors), daily, common window 2018–2023"))
rec = b[(b.tier == 1) & (b.window == "recent")]
out.append(table(rec, [
    ("PM2.5 r", "pm25", "r", "{:.2f}", "daily"), ("PM2.5 NMB", "pm25", "nmb", pct, "daily"),
    ("PM10 r", "pm10", "r", "{:.2f}", "daily"), ("PM10 NMB", "pm10", "nmb", pct, "daily"),
    ("O3 MDA8 r", "o3_mda8", "r", "{:.2f}", "daily"), ("O3 MDA8 NMB", "o3_mda8", "nmb", pct, "daily"),
    ("NO2 r", "no2", "r", "{:.2f}", "daily"), ("NO2 NMB", "no2", "nmb", pct, "daily")],
    "Tier 1, daily, recent window 2025-08..2026-10"))
sm = b[(b.tier == 1) & (b.window == "smoke")]
out.append(table(sm, [
    ("r", "pm25", "r", "{:.2f}", "daily"), ("NMB", "pm25", "nmb", pct, "daily"),
    ("POD >35", "pm25", "pod_35", "{:.2f}", "daily"), ("FAR >35", "pm25", "far_35", "{:.2f}", "daily"),
    ("CSI >35", "pm25", "csi_35", "{:.2f}", "daily")],
    "Tier 1, smoke days (HRRR-Smoke daily ≥ 20 µg m⁻³), daily PM2.5, full window"))
t2 = b[(b.tier == 2) & (b.window == "full")]
T2COLS = [("PM2.5 r", "pm25", "r", "{:.2f}", "daily"), ("PM2.5 NMB", "pm25", "nmb", pct, "daily"),
          ("PM2.5 RMSE", "pm25", "rmse", "{:.1f}", "daily"), ("Monthly r", "pm25", "r", "{:.2f}", "monthly")]
out.append(table(t2[t2.network.isin(["Embassy", "SPARTAN"])], T2COLS,
                 "Tier 2a (US embassies, SPARTAN), daily, full window"))
oaq = t2[t2.network == "OpenAQ"]
out.append(table(oaq, T2COLS + [
    ("O3 MDA8 r", "o3_mda8", "r", "{:.2f}", "daily"), ("O3 MDA8 NMB", "o3_mda8", "nmb", pct, "daily"),
    ("NO2 r", "no2", "r", "{:.2f}", "daily"), ("NO2 NMB", "no2", "nmb", pct, "daily")],
    "Tier 2b (OpenAQ reference monitors outside the US), daily, full window"))
t3 = b[(b.tier == 3) & (b.window == "full")]
T3COLS = [("PM2.5 r", "pm25", "r", "{:.2f}", "daily"), ("PM2.5 NMB", "pm25", "nmb", pct, "daily")]
out.append(table(t3[t3.network == "SensorCommunity"], T3COLS,
                 "Tier 3a (Sensor.Community SDS011 low-cost sensors), daily, 2023–2024"))
out.append(table(t3[t3.network == "OpenAQ-LC"], T3COLS,
                 "Tier 3b (OpenAQ low-cost sensors: AirGradient, AirQo), daily, 2023-11 → 2026-11"))
t4 = b[(b.tier == 4) & (b.window == "common")]
out.append(table(t4, [
    ("r vs others", "pm25", "r", "{:.2f}", "monthly"), ("NMB vs others", "pm25", "nmb", pct, "monthly")],
    "Tier 4 (station-remote points): monthly PM2.5 vs the median of the other products, common window"))
spec = b[(b.window == "full") & b["var"].str.startswith("spec_") & (b.scale == "daily")]
sp = ["so4", "no3", "nh4", "om", "bc", "dust", "ss"]
out.append(table(spec, [(f"{s.upper()} NMB", f"spec_{s}", "nmb", pct, "daily") for s in sp],
                 "PM2.5 components vs IMPROVE/CSN 24-h filters, daily, full window"))
(ROOT / "results" / "key_tables.md").write_text("\n".join(out))
print("\n".join(out))
