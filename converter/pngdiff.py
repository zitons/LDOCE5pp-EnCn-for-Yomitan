"""Decode a PNG produced by CDP and compare two of them pixel by pixel.

Node in this environment has neither `ws` nor `createImageBitmap`, and Pillow is
absent, so decode the PNG directly: Chrome emits 8-bit RGBA, non-interlaced, so
the format is a signature + IHDR + concatenated IDAT (zlib) + IEND, and each
scanline is filter byte + width*4 bytes. Only the five filter types Chrome's
encoder can emit need handling (it uses 0/1/2/3/4).
"""
import struct
import sys
import zlib


def read_png(path):
    d = open(path, "rb").read()
    assert d[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    pos = 8
    idat = b""
    w = h = bd = ct = None
    while pos < len(d):
        ln, typ = struct.unpack(">I4s", d[pos:pos + 8])
        body = d[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w, h, bd, ct = struct.unpack(">IIBB", body[:10])
        elif typ == b"IDAT":
            idat += body
        elif typ == b"IEND":
            break
        pos += 12 + ln
    assert bd == 8, f"unsupported PNG: bit depth {bd}"
    # CDP emits colour type 2 (RGB) or 6 (RGBA) depending on the page; support both
    nch = {2: 3, 6: 4}.get(ct)
    assert nch, f"unsupported PNG: colour type {ct}"
    raw = zlib.decompress(idat)
    stride = w * nch
    out = bytearray(w * h * nch)
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        f = raw[p]; p += 1
        line = bytearray(raw[p:p + stride]); p += stride
        if f == 0:
            pass
        elif f == 1:      # Sub
            for i in range(4, stride):
                line[i] = (line[i] + line[i - 4]) & 0xFF
        elif f == 2:      # Up
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif f == 3:      # Average
            for i in range(stride):
                a = line[i - 4] if i >= 4 else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif f == 4:      # Paeth
            for i in range(stride):
                a = line[i - 4] if i >= 4 else 0
                b = prev[i]
                c = prev[i - 4] if i >= 4 else 0
                pp = a + b - c
                pa, pb, pc = abs(pp - a), abs(pp - b), abs(pp - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        else:
            raise ValueError(f"unknown filter {f}")
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return w, h, out, nch


def main():
    wa, ha, a, nch = read_png(sys.argv[1])
    wb, hb, b, _ = read_png(sys.argv[2])
    print(f"A: {wa}x{ha}")
    print(f"B: {wb}x{hb}")
    if (wa, ha) != (wb, hb):
        print("SIZE DIFFERS -- not directly comparable")
        return
    changed = 0
    minx = miny = 1 << 30
    maxx = maxy = -1
    bands = {}
    for y in range(ha):
        base = y * wa * nch
        for x in range(wa):
            i = base + x * nch
            same = a[i] == b[i] and a[i + 1] == b[i + 1] and a[i + 2] == b[i + 2]
            if not same:
                changed += 1
                if x < minx: minx = x
                if x > maxx: maxx = x
                if y < miny: miny = y
                if y > maxy: maxy = y
                k = y // 40
                bands[k] = bands.get(k, 0) + 1
    total = wa * ha
    print()
    if not changed:
        print("PIXEL DIFF: NONE -- the two renders are pixel-identical")
    else:
        print(f"PIXEL DIFF: {changed:,} / {total:,} ({changed*100.0/total:.4f}%)")
        print(f"bbox: x {minx}..{maxx}, y {miny}..{maxy}")
        print("changed pixels per 40px band:")
        for k in sorted(bands):
            print(f"   y {k*40:>5}-{k*40+39:<5}  {bands[k]:>7,}")


main()
