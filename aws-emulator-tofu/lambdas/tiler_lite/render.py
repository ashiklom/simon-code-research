"""Turn raw COG tile samples into a PNG, titiler-style (rescale, colormap_name, bidx, alpha mask).

Pure standard library. The uint8 paths use bytes.translate/slicing and big-int bit tricks instead
of per-pixel Python loops, because RustPython (aws-emulator's Lambda runtime) is slow at loops.
"""
import math
import struct
import zlib

from colormaps import COLORMAPS


def png(width, height, channels, data):
    """Encode 8-bit PNG. channels: 1=L, 2=LA, 3=RGB, 4=RGBA; data is pixel-interleaved bytes."""
    color_type = {1: 0, 2: 4, 3: 2, 4: 6}[channels]
    stride = width * channels
    raw = b"".join(b"\x00" + data[r * stride:(r + 1) * stride] for r in range(height))

    def chunk(tag, payload):
        body = tag + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 6))
            + chunk(b"IEND", b""))


def _interleave(chans):
    n = len(chans)
    out = bytearray(len(chans[0]) * n)
    for i, c in enumerate(chans):
        out[i::n] = c
    return bytes(out)


def _or_bytes(parts, n):
    acc = 0
    for p in parts:
        acc |= int.from_bytes(p, "big")
    return acc.to_bytes(n, "big")


def _rescale_table(lo, hi):
    """256-entry translate table implementing rio-tiler linear_rescale + clip + uint8 truncation."""
    out = bytearray(256)
    span = (hi - lo) or 1.0
    for v in range(256):
        s = (v - lo) / span * 255.0
        out[v] = 0 if s <= 0 else 255 if s >= 255 else int(s)
    return bytes(out)


def render(cog, data, width, height, bidx=None, rescale=None, colormap_name=None):
    """Return PNG bytes. bidx: 1-based band list; rescale: list of (min, max) per band or one for all."""
    spp = cog.spp
    bands = bidx or list(range(1, min(spp, 4) + 1))
    for b in bands:
        if not 1 <= b <= spp:
            raise ValueError(f"Invalid band index {b}")
    n = width * height
    nod = cog.nodata

    if cog.dtype == "uint8":
        chans = [data[b - 1::spp] for b in bands] if spp > 1 else [data]
        # mask: valid where any *dataset* band differs from nodata (GDAL dataset mask semantics)
        if nod is None or not (0 <= nod <= 255):
            alpha = b"\xff" * n
        else:
            t = bytearray(b"\xff" * 256)
            t[int(nod)] = 0
            t = bytes(t)
            all_chans = [data[i::spp] for i in range(spp)] if spp > 1 else [data]
            alpha = _or_bytes([c.translate(t) for c in all_chans], n)
        if rescale:
            chans = [c.translate(_rescale_table(*rescale[min(i, len(rescale) - 1)])) for i, c in enumerate(chans)]
    else:
        vals = cog.samples(data)
        chans = []
        valid = None
        for i, b in enumerate(bands):
            band = vals[b - 1::spp] if spp > 1 else vals
            lo, hi = rescale[min(i, len(rescale) - 1)] if rescale else (0.0, 255.0)
            span = (hi - lo) or 1.0
            k = 255.0 / span
            if valid is None:
                valid = bytes(0 if (v == nod or v != v) else 255 for v in band) if nod is not None \
                    else bytes(0 if v != v else 255 for v in band)
            chans.append(bytes(0 if s <= 0 else 255 if s >= 255 else int(s)
                               for s in ((v - lo) * k if v == v else 0.0 for v in band)))
        alpha = valid

    if colormap_name:
        cm = COLORMAPS.get(colormap_name.lower())
        if cm is None:
            raise KeyError(colormap_name)
        idx = chans[0]
        out = _interleave([idx.translate(cm[0::3]), idx.translate(cm[1::3]), idx.translate(cm[2::3]), alpha])
        return png(width, height, 4, out)
    if len(chans) == 1:
        return png(width, height, 2, _interleave([chans[0], alpha]))
    if len(chans) == 2:
        return png(width, height, 2, _interleave([chans[0], alpha]))
    return png(width, height, 4, _interleave(chans[:3] + [alpha]))


def statistics(cog, data):
    """Per-band min/max/mean over valid pixels of a block (used by /cog/info-like summaries)."""
    vals = cog.samples(data)
    out = []
    for b in range(cog.spp):
        band = [v for v in vals[b::cog.spp] if v == v and v != cog.nodata]
        if not band:
            out.append(None)
            continue
        out.append({"min": min(band), "max": max(band), "mean": math.fsum(band) / len(band)})
    return out
