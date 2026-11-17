"""Write long-format observations (site_id, time, value) into obs-<network> Icechunk repos."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import config, store

KIND = {"pm25": "pm", "pm10": "pm", "pm25_frm": "pm", "o3": "ppb", "no2": "ppb", "co": "ppb",
        "temp": "temp", "rh": "rh"}
UNITS = {"pm": "ug m-3", "ppb": "ppb", "temp": "degC", "rh": "%", "spec": "ug m-3"}


def write(network: str, freq: str, frames: dict[str, pd.DataFrame], attrs: dict | None = None,
          store_url: str | None = None, log=print):
    """frames[var]: long frame with site_id, time (end of interval, UTC; daily: the date), value."""
    repo = store.open_repo(store.repo_name("obs", network), store_url)
    path = store.group_path("obs", network, freq)
    dt = pd.Timedelta(seconds=store.FREQ_SECONDS[freq])
    frames = {k: v.dropna(subset=["value"]) for k, v in frames.items() if len(v)}
    if not frames:
        return
    t0 = min(v.time.min() for v in frames.values())
    t1 = max(v.time.max() for v in frames.values())
    t0 = max(pd.Timestamp(t0).floor(dt), config.START)
    times = pd.date_range(t0, pd.Timestamp(t1).floor(dt), freq=dt)
    sites = sorted(set().union(*[set(v.site_id) for v in frames.values()]))
    session = repo.writable_session("main")
    w = store.GroupWriter(session, path, freq, has_px=False, attrs={"network": network, **(attrs or {})},
                          t_origin=config.START)
    specs = {}
    data = {}
    for var, df in frames.items():
        df = df[(df.time >= times[0]) & (df.time <= times[-1])]
        si = pd.Index(sites).get_indexer(df.site_id)
        ti = ((df.time - times[0]) // dt).astype(int).values
        arr = np.full((len(sites), len(times)), np.nan, dtype="f4")
        arr[si, ti] = df.value.values
        data[var] = arr
        kind = "spec" if var.startswith("pm25_") and var != "pm25_frm" else KIND.get(var, "pm")
        specs[var] = store.VarSpec(var, kind, UNITS[kind], {})
    # write in site batches to bound memory of the per-site region writes
    for i in range(0, len(sites), 200):
        sl = slice(i, i + 200)
        w.write(sites[sl], times, {k: v[sl] for k, v in data.items()}, specs)
    w.set_extracted_end(times[-1])
    session.commit(f"obs {network} {freq}: {len(sites)} sites, {list(frames)}")
    log(f"[obs] {network}/{freq}: {len(sites)} sites, {times[0]} .. {times[-1]}, vars {list(frames)}")
