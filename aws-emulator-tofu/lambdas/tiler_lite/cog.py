"""Tiny pure-Python reader for WebMercatorQuad-aligned Cloud-Optimized GeoTIFFs.

Scope (deliberately small; see README): EPSG:3857 COGs written with
`gdal_translate -of COG -co TILING_SCHEME=GoogleMapsCompatible`, tiled, DEFLATE or uncompressed,
predictor none/2, chunky or planar, integer/float samples. Each internal tile at each overview
is exactly one XYZ tile, so a native tile costs one range read.

Only the standard library is used (struct, zlib, array, math) because aws-emulator runs Lambda
handlers on RustPython, which cannot load numpy/GDAL.
"""
import array
import math
import struct
import sys
import zlib
from operator import itemgetter

ORIGIN = 20037508.342789244          # half the WebMercator world width (m)
WORLD = 2 * ORIGIN
TYPES = {1: ("B", 1), 2: ("s", 1), 3: ("H", 2), 4: ("I", 4), 5: ("II", 8), 6: ("b", 1), 7: ("B", 1),
         8: ("h", 2), 9: ("i", 4), 10: ("ii", 8), 11: ("f", 4), 12: ("d", 8), 16: ("Q", 8), 17: ("q", 8)}
DTYPES = {  # (SampleFormat, BitsPerSample) -> (numpy-style name, array typecode)
    (1, 8): ("uint8", "B"), (1, 16): ("uint16", "H"), (1, 32): ("uint32", "I"),
    (2, 8): ("int8", "b"), (2, 16): ("int16", "h"), (2, 32): ("int32", "i"),
    (3, 32): ("float32", "f"), (3, 64): ("float64", "d"),
}


class COGError(Exception):
    def __init__(self, status, detail):
        super().__init__(detail)
        self.status = status
        self.detail = detail


class Level:
    """One IFD (full resolution or overview)."""

    def __init__(self, tags, cog):
        self.width = tags[256][0]
        self.height = tags[257][0]
        self.tile_w = tags[322][0]
        self.tile_h = tags[323][0]
        self.offsets = tags[324]
        self.counts = tags[325]
        self.compression = tags.get(259, [1])[0]
        self.predictor = tags.get(317, [1])[0]
        self.across = -(-self.width // self.tile_w)
        self.down = -(-self.height // self.tile_h)
        self.cog = cog


class COG:
    def __init__(self, fetch, header_bytes=32768):
        """fetch(start, length) -> bytes (may return fewer bytes at EOF)."""
        self._fetch = fetch
        self.buf = fetch(0, header_bytes)
        if self.buf[:2] == b"II":
            self.bo = "<"
        elif self.buf[:2] == b"MM":
            self.bo = ">"
        else:
            raise COGError(400, "Not a TIFF file")
        magic = self._unpack("H", 2)[0]
        if magic == 42:
            self.big = False
            ifd = self._unpack("I", 4)[0]
        elif magic == 43:
            self.big = True
            ifd = self._unpack("Q", 8)[0]
        else:
            raise COGError(400, "Not a TIFF file")
        ifds = []
        while ifd:
            tags, ifd = self._read_ifd(ifd)
            ifds.append(tags)
        main = ifds[0]
        if 322 not in main:
            raise COGError(400, "Only tiled GeoTIFFs are supported")
        self.levels = [Level(t, self) for t in ifds
                       if not (t.get(254, [0])[0] & 4) and 322 in t]  # skip mask IFDs
        self.levels.sort(key=lambda lv: -lv.width)
        self.spp = main.get(277, [1])[0]
        self.planar = main.get(284, [1])[0]
        bits = main.get(258, [8])[0]
        fmt = main.get(339, [1])[0]
        if (fmt, bits) not in DTYPES:
            raise COGError(400, f"Unsupported sample type {fmt}/{bits}")
        self.dtype, self.typecode = DTYPES[(fmt, bits)]
        self.bytes_per_sample = bits // 8
        self.photometric = main.get(262, [1])[0]
        nod = main.get(42113)
        self.nodata = float(nod.rstrip("\x00")) if nod else None
        self._georef(main)

    # --- low-level TIFF parsing ---------------------------------------------------------------
    def _ensure(self, end):
        if end > len(self.buf):
            more = self._fetch(len(self.buf), max(end - len(self.buf), 65536))
            self.buf += more

    def _unpack(self, fmt, off):
        size = struct.calcsize(self.bo + fmt)
        self._ensure(off + size)
        return struct.unpack_from(self.bo + fmt, self.buf, off)

    def _read_ifd(self, off):
        n_fmt, n_size, e_size = ("Q", 8, 20) if self.big else ("H", 2, 12)
        n = self._unpack(n_fmt, off)[0]
        tags = {}
        pos = off + n_size
        inline = 8 if self.big else 4
        for _ in range(n):
            if self.big:
                tag, typ, count = self._unpack("HHQ", pos)
                voff = pos + 12
            else:
                tag, typ, count = self._unpack("HHI", pos)
                voff = pos + 8
            code, size = TYPES.get(typ, ("B", 1))
            total = size * count
            if total > inline:
                voff = self._unpack("Q" if self.big else "I", voff)[0]
            if typ == 2:
                self._ensure(voff + count)
                val = self.buf[voff:voff + count].decode("latin-1")
            else:
                val = list(self._unpack(f"{count * len(code)}{code[0]}", voff))
            tags[tag] = val
            pos += e_size
        nxt = self._unpack("Q" if self.big else "I", pos)[0]
        return tags, nxt

    # --- georeferencing -----------------------------------------------------------------------
    def _georef(self, tags):
        if 33550 not in tags or 33922 not in tags:
            raise COGError(400, "COG has no georeferencing")
        sx, sy = tags[33550][0], tags[33550][1]
        tp = tags[33922]
        self.x0 = tp[3] - tp[0] * sx
        self.y0 = tp[4] + tp[1] * sy
        self.res = sx
        geokeys = tags.get(34735, [])
        epsg = None
        for i in range(4, len(geokeys), 4):
            if geokeys[i] in (3072, 2048):
                epsg = geokeys[i + 3]
            if geokeys[i] == 1025 and geokeys[i + 3] == 2:  # RasterPixelIsPoint: tiepoint is a centre
                self.x0 -= sx / 2
                self.y0 += sy / 2
        if epsg != 3857:
            raise COGError(400, f"Only EPSG:3857 (WebMercatorQuad-aligned) COGs are supported, got EPSG:{epsg}")
        self.maxzoom = round(math.log2(WORLD / (256 * self.res)))
        self.native_minzoom = self.maxzoom - (len(self.levels) - 1)
        # Advertised minzoom follows rio-tiler: halve until the *smaller* side fits in one tile.
        lvl, w, h = 0, self.levels[0].width, self.levels[0].height
        while min(w, h) / 2 ** lvl > 256:
            lvl += 1
        self.minzoom = self.maxzoom - lvl
        full = self.levels[0]
        self.bounds = (self.x0, self.y0 - full.height * self.res, self.x0 + full.width * self.res, self.y0)

    # --- tile reads -------------------------------------------------------------------------
    def _nodata_plane(self, lv):
        n = lv.tile_w * lv.tile_h
        if self.nodata is None:
            return bytes(n * self.bytes_per_sample)
        return array.array(self.typecode, [_cast(self.nodata, self.typecode)] * n).tobytes()

    def _level_index(self, z):
        return self.maxzoom - z

    def _read_level_block(self, li, bx, by):
        """Block (bx, by) of level index li in that level's own tile grid, or None."""
        lv = self.levels[li]
        if not (0 <= bx < lv.across and 0 <= by < lv.down):
            return None
        idx = by * lv.across + bx
        planes = range(self.spp) if self.planar == 2 else [0]
        n_tiles = lv.across * lv.down
        per = self.bytes_per_sample * lv.tile_w * lv.tile_h * (1 if self.planar == 2 else self.spp)
        parts = []
        for p in planes:
            k = idx + p * n_tiles
            off, cnt = lv.offsets[k], lv.counts[k]
            if cnt == 0:
                parts.append(None)
                continue
            raw = self._fetch(off, cnt)
            if lv.compression in (8, 32946):
                raw = zlib.decompress(raw)
            elif lv.compression != 1:
                raise COGError(400, f"Unsupported TIFF compression {lv.compression}")
            if len(raw) < per:
                raw = raw + bytes(per - len(raw))
            if lv.predictor == 2:
                raw = _undo_predictor2(raw, lv.tile_w, 1 if self.planar == 2 else self.spp,
                                       self.bytes_per_sample, self.typecode, self.bo)
            elif lv.predictor != 1:
                raise COGError(400, f"Unsupported TIFF predictor {lv.predictor}")
            parts.append(raw)
        if all(p is None for p in parts):
            return None
        if self.planar == 2:
            parts = [p if p is not None else self._nodata_plane(lv) for p in parts]
            return _interleave(parts, self.bytes_per_sample)
        return parts[0]

    def read_tile(self, z, x, y, tilesize=256):
        """Return (data_bytes, width, height) pixel-interleaved for an output XYZ tile.

        Picks the overview whose resolution matches the request (titiler/GDAL pick similarly),
        then copies blocks when the tile grid is aligned, else samples nearest-neighbour.
        Missing/outside pixels are filled with nodata.
        """
        if tilesize not in (256, 512):
            raise COGError(400, "tilesize must be 256 or 512")
        lz = z + (1 if tilesize == 512 else 0)  # zoom whose 256-px tiles match the requested resolution
        src = min(max(lz, self.native_minzoom), self.maxzoom)
        if lz - src > 8 or src - lz > 3:
            raise COGError(404, f"Tile(x={x}, y={y}, z={z}) is outside bounds")
        li = self._level_index(src)
        lv = self.levels[li]
        res = self.res * 2 ** li
        bpp = self.spp * self.bytes_per_sample
        tile_m = WORLD / 2 ** z
        tx0 = -ORIGIN + x * tile_m
        ty0 = ORIGIN - y * tile_m
        step = tile_m / tilesize
        # Level pixel column/row of each output pixel centre (may be outside the level).
        cols = [int(math.floor((tx0 + (i + 0.5) * step - self.x0) / res)) for i in range(tilesize)]
        rows = [int(math.floor((self.y0 - (ty0 - (j + 0.5) * step)) / res)) for j in range(tilesize)]
        vcols = [c for c in cols if 0 <= c < lv.width]
        vrows = [r for r in rows if 0 <= r < lv.height]
        if not vcols or not vrows:
            raise COGError(404, f"Tile(x={x}, y={y}, z={z}) is outside bounds")
        bx0, bx1 = vcols[0] // lv.tile_w, vcols[-1] // lv.tile_w
        by0, by1 = vrows[0] // lv.tile_h, vrows[-1] // lv.tile_h
        blocks = {}
        for by in range(by0, by1 + 1):
            for bx in range(bx0, bx1 + 1):
                blocks[(bx, by)] = self._read_level_block(li, bx, by)
        if all(b is None for b in blocks.values()):
            raise COGError(404, f"Tile(x={x}, y={y}, z={z}) is outside bounds")
        nod_px = array.array(self.typecode, [_cast(self.nodata or 0, self.typecode)] * self.spp).tobytes()
        empty = nod_px * (lv.tile_w * lv.tile_h)
        # Fast path: output tile == one aligned block.
        if (tilesize == lv.tile_w and cols[0] % lv.tile_w == 0 and rows[0] % lv.tile_h == 0
                and cols[-1] - cols[0] == tilesize - 1 and rows[-1] - rows[0] == tilesize - 1):
            b = blocks.get((cols[0] // lv.tile_w, rows[0] // lv.tile_h))
            return (b if b is not None else empty), tilesize, tilesize
        stride = lv.tile_w * bpp
        nb = bx1 - bx0 + 1
        sentinel = nb * lv.tile_w  # index of the appended nodata pixel
        idx = [(c - bx0 * lv.tile_w) if 0 <= c < lv.width else sentinel for c in cols]
        getter = itemgetter(*[i * bpp + k for i in idx for k in range(bpp)])
        nod_row = nod_px * tilesize
        out = []
        cache = {}
        for r in rows:
            if not 0 <= r < lv.height:
                out.append(nod_row)
                continue
            if r not in cache:
                by, wr = divmod(r, lv.tile_h)
                strip = b"".join((blocks.get((bx, by)) or empty)[wr * stride:(wr + 1) * stride]
                                 for bx in range(bx0, bx1 + 1)) + nod_px
                cache[r] = bytes(getter(strip))
            out.append(cache[r])
        return b"".join(out), tilesize, tilesize

    def read_point(self, mx, my):
        """Values at a WebMercator point from the full-resolution level (None if outside)."""
        lv = self.levels[0]
        c = int(math.floor((mx - self.x0) / self.res))
        r = int(math.floor((self.y0 - my) / self.res))
        if not (0 <= c < lv.width and 0 <= r < lv.height):
            return None
        block = self._read_level_block(0, c // lv.tile_w, r // lv.tile_h)
        if block is None:
            return None
        n = self.spp * self.bytes_per_sample
        i = (r % lv.tile_h) * lv.tile_w + c % lv.tile_w
        return list(self.samples(block[i * n:(i + 1) * n]))

    def samples(self, data):
        """bytes -> array of samples in native byte order."""
        a = array.array(self.typecode)
        a.frombytes(data)
        if self.bo != _native_bo():
            a.byteswap()
        return a


def _native_bo():
    return "<" if sys.byteorder == "little" else ">"


def _cast(v, typecode):
    return float(v) if typecode in "fd" else int(v)


def _interleave(planes, bps):
    n = len(planes)
    out = bytearray(len(planes[0]) * n)
    if bps == 1:
        for i, p in enumerate(planes):
            out[i::n] = p
        return bytes(out)
    for i, p in enumerate(planes):
        for k in range(bps):
            out[i * bps + k::n * bps] = p[k::bps]
    return bytes(out)


def _undo_predictor2(raw, width, spp, bps, typecode, bo):
    a = array.array(typecode)
    a.frombytes(raw)
    if bo != _native_bo():
        a.byteswap()
    rows = len(a) // (width * spp)
    mask = (1 << (8 * bps)) - 1
    for r in range(rows):
        base = r * width * spp
        for i in range(base + spp, base + width * spp):
            a[i] = (a[i] + a[i - spp]) & mask if typecode in "BHI" else a[i] + a[i - spp]
    if bo != _native_bo():
        a.byteswap()
    return a.tobytes()


# --- coordinate helpers --------------------------------------------------------------------------
def merc_to_lonlat(x, y):
    lon = x / ORIGIN * 180.0
    lat = math.degrees(2 * math.atan(math.exp(y / 6378137.0)) - math.pi / 2)
    return lon, lat


def lonlat_to_merc(lon, lat):
    x = lon * ORIGIN / 180.0
    lat = max(min(lat, 85.0511287798066), -85.0511287798066)
    y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * 6378137.0
    return x, y
