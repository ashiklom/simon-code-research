import numpy as np
import pandas as pd

from cpc import store


def test_roundtrip(tmp_path):
    repo = store.open_repo(f"file://{tmp_path}/r.icechunk")
    s = repo.writable_session("main")
    w = store.GroupWriter(s, "products/x/1h", "1h", has_px=True, attrs={"product": "x"})
    t = pd.date_range("2020-01-01 01:00", periods=48, freq="h")
    spec = {"tair": store.VarSpec("tair", "temp", "degC", {})}
    w.write_stencil(["a", "b"], np.zeros((2, 4)), np.zeros((2, 4)), np.full((2, 4), 0.25))
    d = np.random.default_rng(0).normal(size=(2, 4, 48)) * 10
    w.write(["a", "b"], t, {"tair": d}, spec)
    # append later times for a new site and extend the time axis
    t2 = pd.date_range("2020-01-02 13:00", periods=24, freq="h")
    w.write(["c"], t2, {"tair": np.ones((1, 4, 24))}, spec)
    w.set_extracted_end(t2[-1])
    s.commit("test")
    ds = store.read_group(repo.readonly_session("main"), "products/x/1h")
    assert list(ds.site.values) == ["a", "b", "c"]
    assert ds.sizes["time"] == 60
    np.testing.assert_allclose(ds.tair.isel(site=0, time=slice(0, 48)), np.round(d[0] * 100) / 100, atol=1e-4)
    assert np.isnan(ds.tair.isel(site=0, time=-1)).all()
    assert np.isnan(ds.tair.isel(site=2, time=0)).all()
    assert (ds.tair.isel(site=2, time=slice(36, 60)) == 1).all()
    assert ds.attrs["extracted_end"].startswith("2020-01-03")
