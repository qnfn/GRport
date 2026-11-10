# SPDX-License-Identifier: GPL-2.0-or-later
"""Resolution patches for sizes Junmin Lee's patch files do not have (4:3, 5:4, 3:2, ...),
made from his own 16:10 patches.

His 16:10 patches all write the same addresses; only the size changes, written as integers
(W, H, W/2, H/2, W/4, H/4, W-1, H-1, halves rounded up to 32), floats (W, H, W/2, H/2, W/960,
H/544, 1/W, 1/H, the aspect ratio) and, in Gravity Rush Remastered, words packed as
const ^ W ^ (H << 16). learn() finds each such field by comparing two of his patches (2560x1600
and 1280x800, whose values all differ); generate() writes them for another size. Both games'
models reproduce his other 16:10 sizes byte for byte (tests/test_respatch.py).
"""
import struct
import xml.etree.ElementTree as ET
from pathlib import Path

TEMPLATE = ("16:10 2560x1600", 2560, 1600)
REFERENCE = ("16:10 1280x800", 1280, 800)
TEMPLATE_ASPECT = 1.6
# Gravity Rush 2 above 2560x1600's pixel count: his 4K patch's larger GPU memory budget lines
# (and its note's extra direct memory) come along.
BIG_PATCH = "16:10 3840x2400"
BIG_PIXELS = 2560 * 1600

INTS = ("W", "H", "W2", "H2", "W4", "H4", "Wm1", "Hm1", "W2a32", "H2a32", "Wa32", "Ha32")


def quantities(w: int, h: int, aspect: float) -> dict:
    return {"W": w, "H": h, "W2": w / 2, "H2": h / 2, "W4": w / 4, "H4": h / 4,
            "Wm1": w - 1, "Hm1": h - 1, "W960": w / 960, "H544": h / 544,
            "iW": 1 / w, "iH": 1 / h, "A": aspect,
            "W2a32": -(-w // 64) * 32, "H2a32": -(-h // 64) * 32,
            "Wa32": -(-w // 32) * 32, "Ha32": -(-h // 32) * 32}


def _close(a: float, b: float) -> bool:
    return a == b or (b != 0 and abs(a - b) <= abs(b) * 2e-7)


def learn(a: bytes, qa: dict, b: bytes, qb: dict) -> "list | None":
    """The size fields of one patch line, from its bytes at two sizes; None if some changed
    byte is not explained."""
    diff = {i for i in range(len(a)) if a[i] != b[i]}
    covered, fields = set(), []
    for i in range(len(a)):
        if i in covered:
            continue
        found = None
        if i + 4 <= len(a):
            fa, fb = struct.unpack_from("<f", a, i)[0], struct.unpack_from("<f", b, i)[0]
            if fa != fb:
                found = next(((i, "f32", n, 4) for n in qa
                              if _close(fa, qa[n]) and _close(fb, qb[n])), None)
            if not found:
                na, nb = struct.unpack_from("<I", a, i)[0], struct.unpack_from("<I", b, i)[0]
                if na != nb:
                    found = next(((i, "i32", n, 4) for n in INTS
                                  if na == qa[n] and nb == qb[n]), None)
        if not found and i + 2 <= len(a):
            na, nb = struct.unpack_from("<H", a, i)[0], struct.unpack_from("<H", b, i)[0]
            if na != nb:
                found = next(((i, "i16", n, 2) for n in INTS if na == qa[n] and nb == qb[n]), None)
        if found and diff & set(range(i, i + found[3])):
            fields.append(found[:3])
            covered.update(range(i, i + found[3]))
    for start in sorted({i - i % 4 for i in diff - covered}):
        if start + 4 > len(a):
            return None
        da, db = struct.unpack_from("<I", a, start)[0], struct.unpack_from("<I", b, start)[0]
        hit = None
        for n1 in INTS:
            for n2 in INTS:
                for s in range(32):
                    xa = (int(qa[n1]) << s) & 0xFFFFFFFF
                    xb = (int(qb[n1]) << s) & 0xFFFFFFFF
                    for t in range(s + 1, 32):
                        if (da ^ xa ^ (int(qa[n2]) << t)) & 0xFFFFFFFF == \
                                (db ^ xb ^ (int(qb[n2]) << t)) & 0xFFFFFFFF:
                            hit = (start, "xor", (n1, s, n2, t))
                            break
                    if hit:
                        break
                if hit:
                    break
            if hit:
                break
        if not hit:
            return None
        fields.append(hit)
        covered.update(range(start, start + 4))
    return fields if not diff - covered else None


def _apply(data: bytes, fields: list, qt: dict, qn: dict) -> bytes:
    out = bytearray(data)
    for off, kind, name in fields:
        if kind == "f32":
            struct.pack_into("<f", out, off, qn[name])
        elif kind == "xor":
            n1, s, n2, t = name
            d = struct.unpack_from("<I", out, off)[0]
            d ^= ((int(qt[n1]) << s) ^ (int(qt[n2]) << t)) & 0xFFFFFFFF
            d ^= ((int(qn[n1]) << s) ^ (int(qn[n2]) << t)) & 0xFFFFFFFF
            struct.pack_into("<I", out, off, d)
        else:
            v = qn[name]
            if v != int(v):
                raise ValueError(f"{name} is not a whole number at this size")
            struct.pack_into("<I" if kind == "i32" else "<H", out, off, int(v))
    return bytes(out)


def _lines(root, name: str, app_version: str) -> list:
    metas = [m for m in root.iter("Metadata") if (m.get("Name") or "").startswith(name)
             and m.get("AppVer") == app_version]
    if not metas:
        raise ValueError(f"the patch file has no '{name}' patch for version {app_version}")
    return [(int(l.get("Address"), 16), bytes.fromhex(l.get("Value")))
            for l in metas[-1].iter("Line") if l.get("Type") == "bytes"]


def model(root, app_version: str) -> tuple:
    """(lines with their fields, the template's quantities) from the author's 16:10 patches."""
    t = _lines(root, TEMPLATE[0], app_version)
    r = _lines(root, REFERENCE[0], app_version)
    if [(a, len(d)) for a, d in t] != [(a, len(d)) for a, d in r]:
        raise ValueError("the 16:10 patches changed shape; resolution not available")
    qt = quantities(TEMPLATE[1], TEMPLATE[2], TEMPLATE_ASPECT)
    qr = quantities(REFERENCE[1], REFERENCE[2], TEMPLATE_ASPECT)
    out = []
    for (addr, a), (_, b) in zip(t, r):
        fields = learn(a, qt, b, qr)
        if fields is None:
            raise ValueError(f"the 16:10 patch line at {addr:#x} is not understood")
        out.append((addr, a, fields))
    return out, qt


def generate(root, app_version: str, w: int, h: int, aspect: float) -> list:
    """[(GoldHEN address, bytes)] of a resolution patch for w x h (multiples of 4)."""
    if w % 4 or h % 4 or not 640 <= w <= 7680 or not 360 <= h <= 4320:
        raise ValueError(f"{w}x{h} is not a size the game can draw")
    lines, qt = model(root, app_version)
    qn = quantities(w, h, aspect)
    out = [(addr, _apply(data, fields, qt, qn)) for addr, data, fields in lines]
    if w * h > BIG_PIXELS:
        big = dict(_lines(root, BIG_PATCH, app_version))
        small = dict(_lines(root, TEMPLATE[0], app_version))
        extra = {a: d for a, d in big.items() if a not in small or len(big[a]) != len(small[a])}
        out = [(a, d) for a, d in out if a not in extra] + sorted(extra.items())
    return out


def big_dmem_patch(w: int, h: int) -> "str | None":
    """The author's patch whose notes give this size's extra direct memory, if any."""
    return BIG_PATCH if w * h > BIG_PIXELS else None


def parse(prefix: str) -> "tuple | None":
    """'GRport 4:3 1440x1080' -> (1440, 1080, 4/3); None for the author's own patch names."""
    parts = prefix.split()
    if len(parts) != 3 or parts[0] != "GRport":
        return None
    num, den = (int(v) for v in parts[1].split(":"))
    w, h = (int(v) for v in parts[2].split("x"))
    return w, h, num / den


def load(xml: Path):
    return ET.parse(xml).getroot()
