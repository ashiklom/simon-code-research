import numpy as np
import pandas as pd

from aqc import analysis as A
from aqc import metrics as M
from aqc.grid import regular_stencil
from aqc.regions import region


def test_stencil_bilinear_weights():
    y = np.arange(-90, 90.1, 0.25)
    x = np.arange(-180, 180, 0.25)
    st = regular_stencil(y, x, np.array([10.1]), np.array([20.05]), x_periodic=360.0)
    assert np.isclose(st.w.sum(), 1.0)
    iy, ix = st.px_index()
    assert y[iy[0, 0]] == 10.0 and x[ix[0, 0]] == 20.0
    vals = np.array([[1.0], [2.0], [3.0], [4.0]])  # (y0,x0),(y0,x1),(y1,x0),(y1,x1)
    assert np.isclose(A.bilinear(vals, st.w[0])[0], 1 + 0.2 * 1 + 0.4 * 2)


def test_daily_lst_and_completeness():
    t = pd.date_range("2023-01-01 01:00", periods=48, freq="h")  # end-stamped UTC hours
    df = pd.DataFrame({"pm25": np.arange(48, dtype=float)}, index=t)
    d = A.daily(df, offset_h=-5)  # UTC-5: local day 2023-01-01 = UTC 05:00..05:00
    # first local day (2022-12-31 local) holds only 5 hours -> incomplete
    assert pd.isna(d.loc["2022-12-31", "pm25"])
    # hours ending 06..29 UTC belong to local 2023-01-01 (values 5..28)
    assert np.isclose(d.loc["2023-01-01", "pm25"], np.mean(np.arange(5, 29)))


def test_mda8_constant_and_peak():
    t = pd.date_range("2023-07-01 01:00", periods=72, freq="h")
    o3 = pd.Series(30.0, index=t)
    o3[(t.hour >= 18) & (t.hour <= 23)] = 80.0  # 6-h afternoon peak in UTC
    m = A.mda8(o3, offset_h=0)
    assert np.isclose(m.dropna().iloc[1], (6 * 80 + 2 * 30) / 8)


def test_monthly_needs_75pct():
    d = pd.DataFrame({"x": 1.0}, index=pd.date_range("2023-01-01", "2023-01-20", freq="D"))
    assert pd.isna(A.monthly(d).iloc[0, 0])  # 20/31 days < 75 %
    d = pd.DataFrame({"x": 1.0}, index=pd.date_range("2023-01-01", "2023-01-25", freq="D"))
    assert A.monthly(d).iloc[0, 0] == 1.0


def test_species_mapping():
    df = pd.DataFrame({"pm25_oc": [1.0], "pm25_su": [2.0], "pm25_soa": [0.5], "pm25_du": [3.0]})
    s = M.product_species(df, "geoscf_v2")
    assert s.om.iloc[0] == 1.5 and s.so4.iloc[0] == 2.0 and s.dust.iloc[0] == 3.0
    s = M.product_species(pd.DataFrame({"pm25_oc": [1.0]}), "merra2")
    assert np.isclose(s.om.iloc[0], 1.4)
    o = M.obs_species(pd.DataFrame({"pm25_oc": [1.0], "pm25_ec": [0.2]}))
    assert np.isclose(o.om.iloc[0], 1.8) and o.bc.iloc[0] == 0.2


def test_exceedance_and_aqi():
    o = np.array([10, 40, 50, 5.0])
    p = np.array([12, 30, 60, 40.0])
    m = M._exceed(o, p, "pm25")
    assert m["pod_35"] == 0.5 and m["far_35"] == 0.5


def test_regions():
    r = region([28.6, 15.5, 39.9, 40.7, -1.3], [77.2, 32.5, 116.4, -74.0, 36.8])
    assert list(r) == ["South Asia", "Africa", "East Asia", "North America", "Africa"]
