import numpy as np

from cpc.grid import regular_stencil


def test_ascending_and_descending():
    lat = np.arange(20.0, 50.0, 0.25)
    lon = np.arange(-130.0, -60.0, 0.25)
    s = regular_stencil(lat, lon, np.array([40.1]), np.array([-100.05]))
    assert lat[s.iy[0, 0]] == 40.0 and lat[s.iy[0, 1]] == 40.25
    assert lon[s.ix[0, 0]] == -100.25 and lon[s.ix[0, 1]] == -100.0
    np.testing.assert_allclose(s.w.sum(1), 1)
    # fy = 0.4, fx = 0.8 -> largest weight at (y0, x1)
    assert s.w[0].argmax() == 1
    s2 = regular_stencil(lat[::-1], lon, np.array([40.1]), np.array([-100.05]))
    assert lat[::-1][s2.iy[0, 0]] == 40.0
    np.testing.assert_allclose(s2.w, s.w)


def test_periodic_lon():
    lat = np.arange(90, -90.1, -0.25)
    lon = np.arange(0, 360, 0.25)
    s = regular_stencil(lat, lon, np.array([40.1]), np.array([-100.05]), x_periodic=360)
    assert lon[s.ix[0, 0]] == 259.75 and lon[s.ix[0, 1]] == 260.0
    s = regular_stencil(lat, lon, np.array([0.0]), np.array([-0.1]), x_periodic=360)
    assert lon[s.ix[0, 0]] == 359.75 and s.ix[0, 1] == 0
    np.testing.assert_allclose(s.w.sum(1), 1)


def test_outside():
    lat = np.arange(25.0, 50.0, 0.125)
    lon = np.arange(-125.0, -67.0, 0.125)
    s = regular_stencil(lat, lon, np.array([61.0, 30.0]), np.array([-150.0, -90.0]))
    assert not s.inside[0] and s.inside[1]
