import json
import os
import subprocess
import sys
import time

import numpy as np
import pytest
import shapely

from swathgeo import analytic as an
from swathgeo import config, footprint as fp, geom, locate as L, psf as P


def test_s2_leaf_ids_match_s2sphere():
    import s2sphere as s2

    rng = np.random.default_rng(0)
    lat = rng.uniform(-89, 89, 500)
    lon = rng.uniform(-180, 180, 500)
    ours = L._s2_leaf_ids(lat, lon)
    ref = [s2.CellId.from_lat_lng(s2.LatLng.from_degrees(a, b)).id() for a, b in zip(lat, lon)]
    assert (ours == np.array(ref, np.uint64)).all()


def test_footprint_theory_modis_viirs_edges():
    # MODIS: 1.418 mrad at 705 km -> ~1 km nadir, ~2.0 x 4.8 km at 55 deg
    t = fp.theory(np.radians([0.0, 55.0]), 705e3, 1.418e-3, 1.418e-3)
    assert abs(t["W_s"][0] - 1000) < 30 and abs(t["W_t"][0] - 1000) < 30
    assert 4.6e3 < t["W_s"][1] < 5.0e3 and 1.9e3 < t["W_t"][1] < 2.1e3
    # VIIRS M band edge (1:1 aggregation): ~1.6 km along-track, ~1.6 km along-scan
    t = fp.theory(np.radians([56.0]), 829e3, 0.3104e-3, 0.891e-3)
    assert 1.4e3 < t["W_t"][0] < 1.8e3


def test_viirs_aggregation_roundtrip():
    j = np.linspace(0, 3199.9, 1000)
    assert np.allclose(an.viirs_native_to_agg(an.viirs_agg_to_native(j)), j)
    assert an.VIIRS_NAT_EDGES[-1] == 6304 and an.VIIRS_AGG_EDGES[-1] == 3200


@pytest.mark.parametrize("comp", [[{"type": "rect", "width": 1}],
                                  [{"type": "rect", "width": 1}, {"type": "rect", "width": 1}],
                                  [{"type": "rect", "width": 1}, {"type": "gauss", "fwhm": 0.8}]])
def test_kernel_normalised(comp):
    u, f, du = P.kernel_1d(comp)
    assert abs(f.sum() - 1) < 1e-9
    U, V, M = P.quadrature({"s": comp, "t": comp}, 9)
    assert abs(M.sum() - 1) < 1e-9


def test_triangle_fwhm_is_one_sample():
    assert abs(P.fwhm([{"type": "rect", "width": 1}, {"type": "rect", "width": 1}]) - 1.0) < 0.02


def test_partition_of_unity_weights_tile_area():
    """Box PSF on a regular grid of 1 km pixels: weights = area inside polygon."""
    xs, ys = np.meshgrid(np.arange(-10, 11) * 1000.0, np.arange(-10, 11) * 1000.0)
    n = xs.size
    pg = fp.PixelGeom(np.zeros(n, int), np.zeros(n, int), np.zeros(n), np.zeros(n), xs.ravel(), ys.ravel(),
                      np.tile([1.0, 0.0], (n, 1)), np.tile([0.0, 1.0], (n, 1)), np.full(n, 1000.0),
                      np.full(n, 1000.0), np.zeros(n), np.full(n, 7e5), (0, 0))
    poly = shapely.box(-3300, -2700, 4100, 5200)
    w = P.psf_weights(pg, poly, P.BOX, cell=100, pou=True)
    assert abs(w.sum() - poly.area) / poly.area < 0.01
    exact = P.area_weights(fp.local_polygons(pg, "model"), poly)
    assert np.abs(w - exact).max() < 0.06 * 1e6


def test_netsim_latency_and_bandwidth(tmp_path):
    f = tmp_path / "x.bin"
    f.write_bytes(os.urandom(4_000_000))
    cfg = tmp_path / "p.toml"
    cfg.write_text('[profile.t]\nkind="http"\nttfb_median_ms=100\nbw_MBps=20\n')
    p = subprocess.Popen([sys.executable, "-m", "swathgeo.netsim", "--config", str(cfg), "--profiles", "t",
                          "--files-root", str(tmp_path), "--base-port", "18950"], stdout=subprocess.PIPE, text=True)
    try:
        assert p.stdout.readline().startswith("READY")
        import requests

        s = requests.Session()
        s.trust_env = False
        t = time.time()
        r = s.get("http://127.0.0.1:18950/x.bin", headers={"Range": "bytes=0-99"})
        assert r.status_code == 206 and len(r.content) == 100
        assert 0.09 < time.time() - t < 0.3
        t = time.time()
        r = s.get("http://127.0.0.1:18950/x.bin")
        dt = time.time() - t
        assert len(r.content) == 4_000_000
        assert 0.1 + 0.2 * 0.8 < dt < 0.1 + 0.2 * 1.5  # 4 MB at 20 MB/s = 0.2 s
        st = s.get("http://127.0.0.1:18950/__stats").json()
        assert st["requests"] == 2 and st["bytes"] == 4_000_100
    finally:
        p.terminate()
