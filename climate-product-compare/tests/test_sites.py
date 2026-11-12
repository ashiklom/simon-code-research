import numpy as np

from cpc.grid import haversine_km
from cpc.sites import nearest_km


def test_nearest_km_matches_haversine():
    rng = np.random.default_rng(0)
    rl, ro = rng.uniform(25, 49, 500), rng.uniform(-125, -67, 500)
    pl, po = rng.uniform(25, 49, 20), rng.uniform(-125, -67, 20)
    brute = np.array([haversine_km(a, b, rl, ro).min() for a, b in zip(pl, po)])
    np.testing.assert_allclose(nearest_km(pl, po, rl, ro), brute, rtol=1e-6)
