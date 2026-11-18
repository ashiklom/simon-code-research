"""Site tables (results/sites/*.csv) and the combined list used by every step.

Columns: site_id, network, tier, name, lat, lon, elev, country, region, setting, utc_offset,
params (comma-separated observed variables), note.
Tiers: 1 = US reference (AQS), 2 = global reference (embassies, SPARTAN, OpenAQ reference),
3 = low-cost sensors, 4 = station-remote points (no observations).
"""

from __future__ import annotations

import pandas as pd

from . import config
from .regions import region

DIR = config.RESULTS / "sites"
NETWORKS = ["aqs", "speciation", "embassy", "spartan", "openaq", "lowcost", "remote"]


def build(networks=("aqs", "embassy", "spartan"), log=print) -> pd.DataFrame:
    DIR.mkdir(parents=True, exist_ok=True)
    for n in networks:
        if n == "aqs":
            from .obs import aqs as m
            df = m.select_sites()
        elif n == "speciation":
            from .obs import speciation as m
            df = m.sites(log=log)
        elif n == "lowcost":
            from .obs import lowcost as m
            ref = load()
            df = m.sites(ref[ref.tier.isin([1, 2])], log=log)
        elif n == "remote":
            from . import remote as m
            df = m.sample(load(), log=log)
        elif n == "openaq":
            from .obs import openaq as m
            ref = load()
            df = m.sites(ref[ref.tier.isin([1, 2]) & ~ref.network.str.startswith("OpenAQ")], log=log)
        elif n == "embassy":
            from .obs import embassy as m
            df = m.sites(log=log)
        elif n == "spartan":
            from .obs import spartan as m
            df = m.sites(log=log)
        else:
            raise ValueError(n)
        if n != "remote":
            df["region"] = region(df.lat, df.lon)
        df.to_csv(DIR / f"{n}.csv", index=False)
        log(f"[sites] {n}: {len(df)}")
    return load()


def load(which: str | list[str] = "all") -> pd.DataFrame:
    parts = []
    for n in NETWORKS:
        p = DIR / f"{n}.csv"
        if p.exists():
            parts.append(pd.read_csv(p, dtype={"site_id": str}))
    df = pd.concat(parts, ignore_index=True).drop_duplicates("site_id")
    df["region"] = region(df.lat.values, df.lon.values)
    if which == "all":
        return df
    if isinstance(which, str):
        which = which.split(",")
    keep = pd.Series(False, index=df.index)
    for w in which:
        if w.startswith("tier"):
            keep |= df.tier == int(w[4:])
        elif w == "pilot":
            keep |= df.site_id.isin(PILOT)
        else:
            keep |= df.network.str.lower() == w.lower()
    return df[keep].reset_index(drop=True)


PILOT = [  # 18 sites: 10 AQS (West smoke, East, rural), 5 embassies, 3 SPARTAN
    "AQS:06-037-1103", "AQS:06-019-0011", "AQS:41-051-0080", "AQS:08-031-0002", "AQS:48-201-1039",
    "AQS:04-013-0019", "AQS:23-005-0029", "AQS:18-097-0078", "AQS:56-009-0010", "AQS:37-199-0004",
    "EMB:NewDelhi", "EMB:Beijing", "EMB:Kampala", "EMB:Lima", "EMB:Accra",
    "SPARTAN:INKA", "SPARTAN:ZAPR", "SPARTAN:SGSU",
]
