"""Small committed result tables from data/results/metrics_all.parquet.

    results/summary_by_tier.csv      medians over sites: tier x product x var x scale x window x method
    results/summary_by_region.csv    medians for Tiers 2-4 by world region (bilinear)
    results/summary_by_network.csv   medians by network (bilinear)
    results/geoscf_v1_vs_v2.csv      GEOS-CF v1 and v2 over their overlap (v1v2 window)
    results/sensor_vs_monitor.csv    low-cost sensors vs co-located monitors
    results/summary_by_setting.csv   Tier 1 AQS medians by AQS location setting (urban/suburban/rural; bilinear)
"""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
m = pd.read_parquet(ROOT / "data" / "results" / "metrics_all.parquet")
out = ROOT / "results"
VALS = [c for c in ("n", "mean_obs", "mean_prod", "bias", "nmb", "rmse", "r", "kge", "csi_15", "csi_35", "csi_70",
                    "aqi_agree") if c in m]


def med(df, keys):
    g = df.groupby(keys)
    s = g[VALS].median().round(3)
    s.insert(0, "n_sites", g.size())
    return s.reset_index()


st = m[m.method != "point"]
med(st, ["tier", "product", "var", "scale", "window", "method"]).to_csv(out / "summary_by_tier.csv", index=False)
b = st[st.method == "bilinear"]
med(b[b.tier >= 2], ["tier", "region", "product", "var", "scale", "window"]).to_csv(out / "summary_by_region.csv", index=False)
med(b, ["network", "product", "var", "scale", "window"]).to_csv(out / "summary_by_network.csv", index=False)
g = b[b["product"].str.startswith("geoscf") & (b.window == "v1v2")]
if len(g):
    med(g, ["tier", "product", "var", "scale"]).to_csv(out / "geoscf_v1_vs_v2.csv", index=False)
aqs = pd.read_csv(out / "sites" / "aqs.csv", usecols=["site_id", "setting"]).rename(columns={"site_id": "site"})
a = b[b.network == "AQS"].merge(aqs, on="site", how="left")
a["setting"] = a.setting.fillna("unknown").str.split(" ").str[0].str.lower()
med(a, ["setting", "product", "var", "scale", "window"]).to_csv(out / "summary_by_setting.csv", index=False)
p = m[m.method == "point"]
if len(p):
    cols = ["site", "reference_site", "product", "scale", "n", "mean_obs", "mean_prod", "bias", "nmb", "r"]
    p[[c for c in cols if c in p]].round(3).to_csv(out / "sensor_vs_monitor.csv", index=False)
print(f"summaries written from {len(m)} metric rows", file=sys.stderr)
