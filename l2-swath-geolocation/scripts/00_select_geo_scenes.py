"""Select the geolocation-only scene set for the analytic-locator consistency test.

Diverse locations (equatorial, subtropical, high-latitude, southern mid-latitude,
near-dateline, CONUS), platforms and epochs (MODIS Terra/Aqua and VIIRS SNPP early in the
mission vs. after the 2021-2022 Terra/Aqua orbit lowering & drift; NOAA-20; ECOSTRESS across
ISS altitude changes). Picks the first granule (CMR order) whose bounding area contains the
location in a fixed date window. Writes config/geo_scenes.toml (committed).
"""

import tomli_w

from swathgeo import config, earthdata as ed

LOCS = {
    "amazon": (-3.0, -60.0),
    "sahara": (23.0, 10.0),
    "siberia": (65.0, 100.0),
    "argentina": (-35.0, -62.0),
    "fiji_dateline": (-17.5, 179.8),
    "california": (39.4, -122.2),
}
ISS_LOCS = ["amazon", "argentina", "california", "kazakhstan"]  # ISS inclination 51.6 deg
LOCS["kazakhstan"] = (49.0, 70.0)

PRODUCTS = [
    # (sensor, platform, short_name, version, epochs)
    ("modis", "Terra", "MOD03", "6.1", ["2013-06", "2024-06"]),
    ("modis", "Aqua", "MYD03", "6.1", ["2013-06", "2024-06"]),
    ("viirs", "SNPP", "VNP03MOD", "2", ["2013-06", "2024-06"]),
    ("viirs", "NOAA-20", "VJ103MOD", "2.1", ["2024-06"]),
    ("ecostress", "ISS", "ECO_L1B_GEO", "002", ["2019-06", "2024-06"]),
]

scenes = []
for sensor, platform, sn, ver, epochs in PRODUCTS:
    locs = ISS_LOCS if sensor == "ecostress" else [k for k in LOCS if k != "kazakhstan"]
    if sensor == "ecostress":
        locs = ["amazon", "california", "kazakhstan"]
    for epoch in epochs:
        for loc in locs:
            lat, lon = LOCS[loc]
            es = []
            y, m = map(int, epoch.split("-"))
            for k in range(6 if sensor == "ecostress" else 1):  # ECOSTRESS acquires sparsely: widen
                mm = f"{y}-{m + k:02d}"
                es = ed.search(sn, ver, point=(lon, lat), temporal=(f"{mm}-01T00:00:00Z", f"{mm}-20T00:00:00Z"),
                               page_size=50)
                if es:
                    break
            if sensor == "ecostress":  # prefer later-build duplicates; skip none
                es = [e for e in es if e["title"].endswith(("_02", "_03", "_01"))]
            if not es:
                print("none", sn, epoch, loc)
                continue
            # alternate day/night picks across locations for a mix of asc/desc orbits
            pick = es[len(scenes) % min(len(es), 4)]
            url = ed.data_urls(pick)[0]
            rec = {"sensor": sensor, "platform": platform, "product": sn, "epoch": epoch, "location": loc,
                   "lat": lat, "lon": lon, "time_start": pick["time_start"],
                   "day_night": pick.get("day_night_flag", ""), "url": url}
            if sensor == "ecostress":
                orbit = pick["title"].split("_")[3]
                att = [e for e in ed.search("ECO_L1B_ATT", "002", temporal=(pick["time_start"], pick["time_start"]))
                       if f"_{orbit}_" in e["title"]]
                if not att:
                    print("no ATT for", pick["title"])
                    continue
                rec["att"] = ed.data_urls(att[-1])[0]
            scenes.append(rec)
            print(sn, epoch, loc, pick["time_start"], rec["day_night"])

with open(config.CONFIG / "geo_scenes.toml", "wb") as f:
    tomli_w.dump({"scene": scenes}, f)
print(len(scenes), "scenes")
