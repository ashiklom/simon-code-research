import numpy as np
import pandas as pd

from cpc import analysis as A
from cpc.metrics import pairs_for, wind_factor


def test_daily_window_prism_style():
    # hourly end-stamped series = hour number; PRISM day D = (D-1 12Z, D 12Z]
    t = pd.date_range("2020-01-01 01:00", "2020-01-04 00:00", freq="h")
    df = pd.DataFrame({"pr": np.ones(len(t)), "tair": np.arange(len(t), dtype=float)}, index=t)
    d = A.daily(df, 12, 24)
    # 2020-01-02 covers 2020-01-01 13:00 .. 2020-01-02 12:00 -> 24 complete hours
    assert d.loc["2020-01-02", "pr"] == 24
    assert d.loc["2020-01-02", "tair"] == np.mean(np.arange(12, 36))
    # first label (2020-01-01) only has hours 01..12 -> incomplete precip -> NaN
    assert np.isnan(d.loc["2020-01-01", "pr"])


def test_daily_utc_and_gridmet():
    t = pd.date_range("2020-01-01 01:00", periods=72, freq="h")
    df = pd.DataFrame({"tmax": np.arange(72.0)}, index=t)
    d = A.daily(df, 24, 24)
    assert d.loc["2020-01-01", "tmax"] == 23  # hour ending 2020-01-02 00:00 belongs to Jan 1
    g = A.daily(df, 31, 24)  # gridMET: day D ends D+1 07 UTC
    assert g.loc["2020-01-01", "tmax"] == 30


def test_to_hourly_and_bilinear():
    t = pd.date_range("2020-01-01 00:30", periods=4, freq="30min")
    h = A.to_hourly(pd.DataFrame({"pr": [1.0, 2.0, 3.0, 4.0]}, index=t))
    assert h.loc["2020-01-01 01:00", "pr"] == 3 and h.loc["2020-01-01 02:00", "pr"] == 7
    v = np.array([[1.0], [np.nan], [3.0], [5.0]])
    w = np.array([0.25, 0.25, 0.25, 0.25])
    assert A.bilinear(v, w)[0] == 3.0
    assert A.nearest(v, np.array([0.1, 0.2, 0.6, 0.1]))[0] == 3.0


def test_pairs():
    assert pairs_for("soilm1", {"depth_top_cm": 0, "depth_bot_cm": 7}) == [("sm05", "sm")]
    assert [o for o, _ in pairs_for("tsoil2", {"depth_top_cm": 7, "depth_bot_cm": 28})] == ["ts10", "ts20"]
    assert pairs_for("wet_root", {"depth_top_cm": 0, "depth_bot_cm": 100, "wetness": True})[-1] == ("sm100", "anom")
    assert 0.6 < wind_factor(10) < 0.75
