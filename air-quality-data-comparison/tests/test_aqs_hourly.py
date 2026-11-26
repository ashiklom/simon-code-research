"""AQS hourly ingest on a tiny synthetic zip (no network)."""

import io
import zipfile

import pandas as pd

from aqc.obs import aqs

HDR = "State Code,County Code,Site Num,POC,Date GMT,Time GMT,Sample Measurement,Units of Measure,Method Name\n"
ROWS = [
    # site 36-005-0110: raw and corrected T640 in the same hour -> keep only the corrected
    "36,005,0110,1,2022-06-01,10:00,10.0,Micrograms/cubic meter (LC),Teledyne T640 at 5.0 LPM\n",
    "36,005,0110,2,2022-06-01,10:00,8.0,Micrograms/cubic meter (LC),Teledyne T640 at 5.0 LPM - Corrected\n",
    # two non-T640 POCs in one hour -> averaged
    "06,067,0010,1,2022-06-01,10:00,4.0,Micrograms/cubic meter (LC),Met One BAM-1020\n",
    "06,067,0010,3,2022-06-01,10:00,6.0,Micrograms/cubic meter (LC),Met One BAM-1022\n",
    # a site we do not want
    "01,001,0001,1,2022-06-01,10:00,99.0,Micrograms/cubic meter (LC),Met One BAM-1020\n",
]


def test_hourly_year_prefers_corrected_t640(tmp_path, monkeypatch):
    p = tmp_path / "hourly_88101_2022.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("hourly_88101_2022.csv", HDR + "".join(ROWS))
    monkeypatch.setattr(aqs, "download", lambda name: p)
    d = aqs._hourly_year(88101, 2022, {"AQS:36-005-0110", "AQS:06-067-0010"})
    got = dict(zip(d.site_id.astype(str), d.value))
    assert got == {"AQS:36-005-0110": 8.0, "AQS:06-067-0010": 5.0}
    assert (d.time == pd.Timestamp("2022-06-01 11:00")).all()  # stamped at the end of the hour
