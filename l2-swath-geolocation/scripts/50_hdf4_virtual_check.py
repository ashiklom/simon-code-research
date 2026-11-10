"""Check virtual-Zarr access to MODIS HDF4 (and the string-fill-value VNP21 case) end to end:
parse -> ManifestStore -> xarray/zarr read -> compare with pyhdf/h5py.

Run with the stock packages:      pixi run python scripts/50_hdf4_virtual_check.py
Run with the vendored/patched ones: PYTHONPATH=vendor/VirtualiZarr:vendor/kerchunk pixi run python ...
"""

import sys
import traceback
import warnings

import h5py
import numpy as np
import xarray as xr
from pyhdf.SD import SD

import virtualizarr
from virtualizarr.parsers import DMRPPParser, HDF4Parser, HDFParser
from swathgeo import config
from swathgeo import readers as R

warnings.filterwarnings("ignore")
print("virtualizarr from", virtualizarr.__file__)
reg = R.obstore_registry(R.Access("local"))
RAW = config.RAW


def hdf4_ref(key, var):
    return np.asarray(SD(str(RAW / key)).select(var)[:])


CASES = [
    ("MYD03 HDF4Parser", "modis/MYD03.A2023154.2125.061.2023155150831.hdf", HDF4Parser(),
     ["Latitude", "Longitude", "SensorZenith", "Height", "orb_pos", "T_inst2ECR", "EV center time", "Scan Type"], hdf4_ref),
    ("MYD11_L2 HDF4Parser", "modis/MYD11_L2.A2023154.2125.061.2023155175206.hdf", HDF4Parser(),
     ["LST", "QC", "Latitude"], hdf4_ref),
    ("MOD11_L2 HDF4Parser", "modis/MOD11_L2.A2023154.1825.061.2023155151846.hdf", HDF4Parser(),
     ["LST", "QC"], hdf4_ref),
    ("MOD11_L2 DMR++", "modis/MOD11_L2.A2023154.1825.061.2023155151846.hdf.dmrpp",
     DMRPPParser(group="/MOD_Swath_LST/Data_Fields"), ["LST", "QC"],
     lambda k, v: hdf4_ref(k.removesuffix(".dmrpp"), v)),
    ("VNP21 HDFParser (string _FillValue)", "viirs/VNP21.A2023154.2012.002.2023156230312.nc",
     HDFParser(group="VIIRS_Swath_LSTE/Data Fields"), ["LST", "QC", "PWV"],
     lambda k, v: np.asarray(h5py.File(RAW / k)["VIIRS_Swath_LSTE/Data Fields/" + v][()])),
]

ok_all = True
for label, key, parser, vars_, ref in CASES:
    try:
        store = parser("file://" + str(RAW / key), registry=reg)
        ds = xr.open_zarr(store, consolidated=False, zarr_format=3, mask_and_scale=False, decode_times=False,
                             concat_characters=False)
        names = [v for v in vars_ if v in ds]
        missing = [v for v in vars_ if v not in ds]
        res = []
        for v in names:
            a = ds[v].values
            b = ref(key, v)
            same = a.shape == b.shape and np.array_equal(a, b, equal_nan=a.dtype.kind == "f")
            res.append(f"{v}:{'OK' if same else 'MISMATCH'}")
            ok_all &= same
        print(f"[{label}] {len(ds.data_vars)} vars; " + " ".join(res) + (f" missing={missing}" if missing else ""))
        ok_all &= not missing
    except Exception as e:  # noqa: BLE001
        ok_all = False
        tb = traceback.format_exc().strip().splitlines()
        print(f"[{label}] FAIL {type(e).__name__}: {str(e)[:200]}  @ {tb[-3].strip()[:160]}")
print("ALL OK" if ok_all else "SOME FAILED")
sys.exit(0 if ok_all else 1)
