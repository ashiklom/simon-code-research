"""Readers for the swath geolocation + LST products used in this experiment.

Everything is returned as plain numpy arrays (float64 lat/lon, float32 LST in K with NaN fill)
so the locator/footprint code is reader-agnostic. The "read benchmark" code (Part C) uses its
own, deliberately different, readers; this module is the reference implementation.

Sensor conventions
------------------
MODIS (MOD03/MYD03 + M?D11_L2, HDF4): 1354 samples x (10 * n_scans) lines, 10 detectors/scan.
VIIRS (VNP03MOD/VJ103MOD + VNP21/VJ121, NetCDF4): 3200 samples x (16 * n_scans) lines.
ECOSTRESS (ECO_L1B_GEO + ECO_L2_LSTE + ECO_L1B_ATT, HDF5): 5400 samples x 5632 lines
    (44 scans x 128 lines), ISS ephemeris in a separate ATT file (ECI J2000).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import h5py
import numpy as np

LINES_PER_SCAN = {"modis": 10, "viirs": 16, "ecostress": 128}

# Epochs used by the products
TAI93 = np.datetime64("1993-01-01T00:00:00")  # MODIS/VIIRS (TAI seconds; leap secs ignored)
J2000 = np.datetime64("2000-01-01T12:00:00")  # ECOSTRESS (seconds since J2000)


@dataclass
class Nav:
    """Per-scan (MODIS/VIIRS) or per-sample (ECOSTRESS) spacecraft state in ECEF metres."""

    time: np.ndarray  # seconds (product epoch)
    pos: np.ndarray  # (n, 3) ECEF m
    vel: np.ndarray  # (n, 3) ECEF m/s
    rpy: np.ndarray | None = None  # (n, 3) roll/pitch/yaw radians, if available
    t_inst2ecr: np.ndarray | None = None  # (n, 3, 3) MODIS only
    att_time: np.ndarray | None = None  # ECOSTRESS: attitude sample times
    body2ecef: np.ndarray | None = None  # ECOSTRESS: (n, 3, 3) ISS body -> ECEF


@dataclass
class Swath:
    sensor: str
    platform: str
    geo_path: Path
    lat: np.ndarray
    lon: np.ndarray
    vza: np.ndarray  # view zenith, degrees
    line_time: np.ndarray | None = None  # per scan (MODIS/VIIRS) or per line (ECOSTRESS)
    nav: Nav | None = None
    lst: np.ndarray | None = None
    height: np.ndarray | None = None  # terrain height of pixel centres (m)
    l2_path: Path | None = None
    attrs: dict = field(default_factory=dict)

    @property
    def shape(self):
        return self.lat.shape

    @property
    def lines_per_scan(self):
        return LINES_PER_SCAN[self.sensor]

    @property
    def name(self):
        return self.geo_path.name


def sensor_of(path: Path) -> str:
    n = Path(path).name
    if re.match(r"M[OY]D(03|11_L2)", n):
        return "modis"
    if re.match(r"V(NP|J1)(03MOD|21)", n):
        return "viirs"
    if n.startswith("ECOv"):
        return "ecostress"
    raise ValueError(f"unknown sensor for {n}")


# --- MODIS ---------------------------------------------------------------------------


def _sds(sd, name, scaled=True):
    ds = sd.select(name)
    a = ds[:]
    attrs = ds.attributes()
    a = np.asarray(a)
    if scaled:
        a = a.astype(np.float64)
        fv = attrs.get("_FillValue")
        if fv is not None:
            a[a == fv] = np.nan
        a = a * attrs.get("scale_factor", 1.0) + attrs.get("add_offset", 0.0)
    return a


def read_modis_geo(path: Path, nav: bool = True) -> Swath:
    from pyhdf.SD import SD

    sd = SD(str(path))
    lat = _sds(sd, "Latitude")
    lon = _sds(sd, "Longitude")
    vza = _sds(sd, "SensorZenith")
    hgt = _sds(sd, "Height")
    n = None
    t = _sds(sd, "EV center time")
    if nav:
        n = Nav(
            time=t,
            pos=_sds(sd, "orb_pos"),
            vel=_sds(sd, "orb_vel"),
            rpy=_sds(sd, "attitude_angles"),
            t_inst2ecr=_sds(sd, "T_inst2ECR"),
        )
    platform = "Terra" if Path(path).name.startswith("MOD") else "Aqua"
    return Swath("modis", platform, Path(path), lat, lon, vza, line_time=t, nav=n, height=hgt)


def read_modis_lst(path: Path) -> np.ndarray:
    from pyhdf.SD import SD

    return _sds(SD(str(path)), "LST").astype(np.float32)


# --- VIIRS ---------------------------------------------------------------------------


def _h5(ds, sl=()):
    a = ds[sl] if sl != () else ds[()]
    a = np.asarray(a)
    fv = ds.attrs.get("_FillValue")
    sf = ds.attrs.get("scale_factor")
    off = ds.attrs.get("add_offset")
    if fv is not None or sf is not None:
        a = a.astype(np.float64)
        if fv is not None:
            a[a == np.asarray(fv).ravel()[0]] = np.nan
        if sf is not None:
            a = a * float(np.asarray(sf).ravel()[0])
        if off is not None:
            a = a + float(np.asarray(off).ravel()[0])
    return a


def read_viirs_geo(path: Path, nav: bool = True) -> Swath:
    with h5py.File(path) as h:
        g = h["geolocation_data"]
        lat = _h5(g["latitude"])
        lon = _h5(g["longitude"])
        vza = _h5(g["sensor_zenith"])
        hgt = _h5(g["height"])
        t = _h5(h["scan_line_attributes/ev_mid_time"])
        n = None
        if nav:
            nd = h["navigation_data"]
            n = Nav(
                time=t,
                pos=_h5(nd["orb_pos_ev_mid"]),
                vel=_h5(nd["orb_vel_ev_mid"]),
                rpy=np.radians(_h5(nd["att_ang_mid"])),
            )
        platform = h.attrs.get("platform", b"").decode() if "platform" in h.attrs else ""
    return Swath("viirs", platform, Path(path), lat, lon, vza, line_time=t, nav=n, height=hgt)


def read_viirs_lst(path: Path) -> np.ndarray:
    with h5py.File(path) as h:
        return _h5(h["VIIRS_Swath_LSTE/Data Fields/LST"]).astype(np.float32)


# --- ECOSTRESS -----------------------------------------------------------------------


def _astropy_time(t_j2000):
    from astropy import units as u
    from astropy.time import Time

    # ECOSTRESS time_j2000 = seconds since 2000-01-01T12:00:00; treated as TT.
    return Time(2451545.0, format="jd", scale="tt") + t_j2000 * u.s


def eci2ecef_matrices(t_j2000: np.ndarray) -> np.ndarray:
    """(n, 3, 3) rotation GCRS -> ITRS (columns: images of the GCRS basis vectors)."""
    from astropy import units as u
    from astropy.coordinates import GCRS, ITRS, CartesianRepresentation

    t = _astropy_time(t_j2000)
    cols = []
    for e in np.eye(3):
        rep = CartesianRepresentation(*(np.repeat(e[:, None] * 1e7, len(t_j2000), 1) * u.m))
        c = GCRS(rep, obstime=t).transform_to(ITRS(obstime=t)).cartesian
        v = np.stack([c.x.to_value(u.m), c.y.to_value(u.m), c.z.to_value(u.m)], -1)
        cols.append(v / np.linalg.norm(v, axis=-1, keepdims=True))
    return np.stack(cols, -1)


def quat_to_matrix(q: np.ndarray) -> np.ndarray:
    """Scalar-first unit quaternions (n, 4) -> rotation matrices (n, 3, 3)."""
    w, x, y, z = q.T
    return np.stack([
        np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)], -1),
        np.stack([2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)], -1),
        np.stack([2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)], -1),
    ], -2)


def eci_to_ecef(t_j2000: np.ndarray, pos: np.ndarray, vel: np.ndarray):
    """GCRS(~J2000) -> ITRS with astropy (precession, nutation, Earth rotation)."""
    from astropy import units as u
    from astropy.coordinates import GCRS, ITRS, CartesianDifferential, CartesianRepresentation
    from astropy.time import Time

    t = _astropy_time(t_j2000)
    rep = CartesianRepresentation(pos.T * u.m, differentials=CartesianDifferential(vel.T * u.m / u.s))
    itrs = GCRS(rep, obstime=t).transform_to(ITRS(obstime=t))
    c = itrs.cartesian
    p = np.stack([c.x.to_value(u.m), c.y.to_value(u.m), c.z.to_value(u.m)], -1)
    d = c.differentials["s"]
    v = np.stack([d.d_x.to_value(u.m / u.s), d.d_y.to_value(u.m / u.s), d.d_z.to_value(u.m / u.s)], -1)
    return p, v


def find_ecostress_att(geo_path: Path) -> Path | None:
    m = re.search(r"_(\d{5})_\d{3}_", Path(geo_path).name)
    if not m:
        return None
    hits = sorted(Path(geo_path).parent.glob(f"ECOv002_L1B_ATT_{m.group(1)}_*.h5"))
    return hits[-1] if hits else None


def read_ecostress_geo(path: Path, nav: bool = True, att_path: Path | None = None) -> Swath:
    with h5py.File(path) as h:
        g = h["Geolocation"]
        lat = g["latitude"][()]
        lon = g["longitude"][()]
        vza = g["view_zenith"][()].astype(np.float64)
        hgt = g["height"][()].astype(np.float64)
        t = g["line_start_time_j2000"][()]
        attrs = {
            "pixel_spacing": float(h["StandardMetadata/ImagePixelSpacing"][()]),
            "line_spacing": float(h["StandardMetadata/ImageLineSpacing"][()]),
        }
    for a in (lat, lon):
        a[(a < -900)] = np.nan
    n = None
    if nav:
        att_path = att_path or find_ecostress_att(path)
        if att_path is not None:
            with h5py.File(att_path) as a:
                te = a["Ephemeris/time_j2000"][()]
                sel = (te > t.min() - 30) & (te < t.max() + 30)
                pe, ve = eci_to_ecef(te[sel], a["Ephemeris/eci_position"][sel], a["Ephemeris/eci_velocity"][sel])
                tq = a["Attitude/time_j2000"][()]
                sq = (tq > t.min() - 30) & (tq < t.max() + 30)
                # quaternion = ISS body -> J2000 (scalar first); verified: body z within ~7 deg of nadir
                b2eci = quat_to_matrix(a["Attitude/quaternion"][sq])
                b2ecef = eci2ecef_matrices(tq[sq]) @ b2eci
                n = Nav(time=te[sel], pos=pe, vel=ve, att_time=tq[sq], body2ecef=b2ecef)
    return Swath("ecostress", "ISS", Path(path), lat, lon, vza, line_time=t, nav=n, height=hgt, attrs=attrs)


def read_ecostress_lst(path: Path) -> np.ndarray:
    with h5py.File(path) as h:
        lst = _h5(h["SDS/LST"]).astype(np.float32)
        cm = h["SDS/cloud_mask"][()]
    lst[cm == 1] = np.nan
    return lst


# --- dispatch ------------------------------------------------------------------------

GEO_READERS = {"modis": read_modis_geo, "viirs": read_viirs_geo, "ecostress": read_ecostress_geo}
LST_READERS = {"modis": read_modis_lst, "viirs": read_viirs_lst, "ecostress": read_ecostress_lst}


def read_geo(path, nav: bool = True) -> Swath:
    return GEO_READERS[sensor_of(path)](Path(path), nav=nav)


def read_swath(geo_path, l2_path=None, nav: bool = True) -> Swath:
    sw = read_geo(geo_path, nav=nav)
    if l2_path is not None:
        sw.lst = LST_READERS[sw.sensor](Path(l2_path))
        sw.l2_path = Path(l2_path)
        assert sw.lst.shape == sw.lat.shape, (sw.lst.shape, sw.lat.shape)
    return sw


def stack(swaths: list[Swath]) -> Swath:
    """Concatenate consecutive granules along-track (MODIS/VIIRS)."""
    if len(swaths) == 1:
        return swaths[0]
    s0 = swaths[0]
    cat = lambda xs: None if xs[0] is None else np.concatenate(xs, axis=0)  # noqa: E731
    nav = None
    if s0.nav is not None:
        nav = Nav(
            time=cat([s.nav.time for s in swaths]),
            pos=cat([s.nav.pos for s in swaths]),
            vel=cat([s.nav.vel for s in swaths]),
            rpy=cat([s.nav.rpy for s in swaths]),
            t_inst2ecr=cat([s.nav.t_inst2ecr for s in swaths]),
            att_time=cat([s.nav.att_time for s in swaths]),
            body2ecef=cat([s.nav.body2ecef for s in swaths]),
        )
    return Swath(
        s0.sensor, s0.platform, s0.geo_path,
        cat([s.lat for s in swaths]), cat([s.lon for s in swaths]), cat([s.vza for s in swaths]),
        line_time=cat([s.line_time for s in swaths]), nav=nav,
        lst=cat([s.lst for s in swaths]), height=cat([s.height for s in swaths]), l2_path=s0.l2_path,
        attrs={**s0.attrs, "granules": [s.geo_path.name for s in swaths]},
    )


def read_scene(name: str, nav: bool = True, lst: bool = True) -> Swath:
    from . import config

    p = config.scene_paths(name)
    sws = []
    for i, g in enumerate(p["geo"]):
        l2 = p["l2"][i] if lst else None
        if p["sensor"] == "ecostress":
            sw = read_ecostress_geo(g, nav=nav, att_path=p["att"][0] if nav else None)
            if l2 is not None:
                sw.lst = read_ecostress_lst(l2)
                sw.l2_path = l2
        else:
            sw = read_swath(g, l2, nav=nav)
        sws.append(sw)
    out = stack(sws)
    out.attrs["scene"] = name
    return out
