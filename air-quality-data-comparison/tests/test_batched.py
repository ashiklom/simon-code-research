import numpy as np
import pandas as pd

from aqc.extract import _batched
from aqc.products.base import Block


def _blk(sites, t0, n):
    times = pd.date_range(t0, periods=n, freq="1h")
    return Block(list(sites), times, {"pm25": np.ones((len(sites), 4, n))})


def test_time_blocks_merge_within_a_chunk():
    o = pd.Timestamp("2018-01-01")
    out = list(_batched([_blk(["a"], o, 24), _blk(["a"], o + pd.Timedelta(hours=24), 24)], "1h", o))
    assert len(out) == 1 and len(out[0].times) == 48 and out[0].data["pm25"].shape == (1, 4, 48)


def test_single_site_blocks_stack_and_new_sites_split():
    o = pd.Timestamp("2018-01-01")
    out = list(_batched([_blk(["a"], o, 24), _blk(["b"], o, 24), _blk(["c"], o + pd.Timedelta(days=200), 24)], "1h", o))
    assert [b.site_ids for b in out] == [["a", "b"], ["c"]]
