"""Incremental update: fetch only the missing span, skip up-to-date sites, same result as one shot."""

import numpy as np
import pandas as pd

from cpc import extract, store
from cpc.products import registry
from cpc.products.base import Block, Grid, Product, Var


class Fake(Product):
    name = "fake"
    freq = "1d"
    start = pd.Timestamp("2008-01-01")
    variables = {"tair": Var(["x"], "temp", "degC", None, {})}

    def __init__(self):
        self.end = pd.Timestamp("2008-03-31")
        self.calls = []

    def grid(self):
        return Grid(np.arange(20.0, 50.0, 1.0), np.arange(-130.0, -60.0, 1.0))

    def available_end(self):
        return self.end

    def fetch(self, sites, st, t0, t1):
        self.calls.append((t0, t1, len(sites)))
        t = pd.date_range(t0, t1, freq="D")
        base = (t - pd.Timestamp("2008-01-01")).days.values.astype(float)
        data = np.stack([np.stack([base + k + p / 10 for p in range(4)]) for k in range(len(sites))])
        yield Block(list(sites.site_id), t, {"tair": data})


def test_incremental(tmp_path):
    sites = pd.DataFrame({"site_id": ["a", "b"], "lat": [35.5, 40.2], "lon": [-100.3, -90.7]})
    root = f"file://{tmp_path}/s"
    f = Fake()
    registry._cache["fake"] = f
    extract.run("fake", sites, store_url=root, log=lambda *a: None)
    assert f.calls == [(pd.Timestamp("2008-01-01"), pd.Timestamp("2008-03-31"), 2)]
    # nothing new -> no fetch
    s = extract.run("fake", sites, store_url=root, log=lambda *a: None)
    assert s["sites_to_fetch"] == 0 and len(f.calls) == 1
    # new data available -> only the new span is fetched
    f.end = pd.Timestamp("2008-04-30")
    extract.run("fake", sites, store_url=root, log=lambda *a: None)
    assert f.calls[-1] == (pd.Timestamp("2008-04-01"), pd.Timestamp("2008-04-30"), 2)
    inc = store.read_group(store.readonly("products", "fake", root), "products/fake/1d")
    # one-shot extraction to compare
    g = Fake()
    g.end = pd.Timestamp("2008-04-30")
    registry._cache["fake"] = g
    extract.run("fake", sites, store_url=f"file://{tmp_path}/t", log=lambda *a: None)
    one = store.read_group(store.readonly("products", "fake", f"file://{tmp_path}/t"), "products/fake/1d")
    np.testing.assert_array_equal(inc.tair.values, one.tair.values)
    assert inc.sizes["time"] == 121
    del registry._cache["fake"]
