"""Pure-Python QR Code encoder (ISO/IEC 18004, byte mode, versions 1-10) + Tk Canvas renderer.

No PIL and no third-party code: the matrix is built here and drawn as Canvas rectangles. It is enough for
pairing URIs (`aiwb://pair?...`, well under 100 bytes). Correctness is checked by decoding the output with
a reference decoder (zbar on the desktop CI, ZXing in the Android JVM tests).
"""
from __future__ import annotations

from typing import Any

# (ec codewords per block, [(block count, data codewords per block), ...]) per version and level
_BLOCKS: dict[int, dict[str, tuple[int, list[tuple[int, int]]]]] = {
    1: {"L": (7, [(1, 19)]), "M": (10, [(1, 16)]), "Q": (13, [(1, 13)]), "H": (17, [(1, 9)])},
    2: {"L": (10, [(1, 34)]), "M": (16, [(1, 28)]), "Q": (22, [(1, 22)]), "H": (28, [(1, 16)])},
    3: {"L": (15, [(1, 55)]), "M": (26, [(1, 44)]), "Q": (18, [(2, 17)]), "H": (22, [(2, 13)])},
    4: {"L": (20, [(1, 80)]), "M": (18, [(2, 32)]), "Q": (26, [(2, 24)]), "H": (16, [(4, 9)])},
    5: {"L": (26, [(1, 108)]), "M": (24, [(2, 43)]), "Q": (18, [(2, 15), (2, 16)]), "H": (22, [(2, 11), (2, 12)])},
    6: {"L": (18, [(2, 68)]), "M": (16, [(4, 27)]), "Q": (24, [(4, 19)]), "H": (28, [(4, 15)])},
    7: {"L": (20, [(2, 78)]), "M": (18, [(4, 31)]), "Q": (18, [(2, 14), (4, 15)]), "H": (26, [(4, 13), (1, 14)])},
    8: {"L": (24, [(2, 97)]), "M": (22, [(2, 38), (2, 39)]), "Q": (22, [(4, 18), (2, 19)]), "H": (26, [(4, 14), (2, 15)])},
    9: {"L": (30, [(2, 116)]), "M": (22, [(3, 36), (2, 37)]), "Q": (20, [(4, 16), (4, 17)]), "H": (24, [(4, 12), (4, 13)])},
    10: {"L": (18, [(2, 68), (2, 69)]), "M": (26, [(4, 43), (1, 44)]), "Q": (24, [(6, 19), (2, 20)]), "H": (28, [(6, 15), (2, 16)])},
}
_ALIGN = {1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34], 7: [6, 22, 38], 8: [6, 24, 42],
          9: [6, 26, 46], 10: [6, 28, 50]}
_LEVEL_BITS = {"L": 1, "M": 0, "Q": 3, "H": 2}
MAX_VERSION = 10


class QrError(ValueError):
    pass


# -- Reed-Solomon over GF(256), polynomial 0x11D
_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _gmul(a: int, b: int) -> int:
    return 0 if a == 0 or b == 0 else _EXP[_LOG[a] + _LOG[b]]


def _rs_generator(degree: int) -> list[int]:
    g = [1]
    for i in range(degree):
        nxt = [0] * (len(g) + 1)
        for j, c in enumerate(g):
            nxt[j] ^= c
            nxt[j + 1] ^= _gmul(c, _EXP[i])
        g = nxt
    return g


def rs_remainder(data: list[int], degree: int) -> list[int]:
    gen = _rs_generator(degree)
    rem = list(data) + [0] * degree
    for i in range(len(data)):
        coef = rem[i]
        if coef:
            for j in range(1, len(gen)):
                rem[i + j] ^= _gmul(gen[j], coef)
    return rem[len(data):]


def _capacity(version: int, level: str) -> int:
    return sum(n * d for n, d in _BLOCKS[version][level][1])


def _bch(value: int, poly: int, poly_bits: int) -> int:
    v = value << (poly_bits - 1)
    for i in range(v.bit_length() - 1, poly_bits - 2, -1):
        if v >> i & 1:
            v ^= poly << (i - poly_bits + 1)
    return v


def _format_bits(level: str, mask: int) -> int:
    data = _LEVEL_BITS[level] << 3 | mask
    return ((data << 10) | _bch(data, 0x537, 11)) ^ 0x5412


def _version_bits(version: int) -> int:
    return (version << 12) | _bch(version, 0x1F25, 13)


def _encode_data(payload: bytes, version: int, level: str) -> list[int]:
    bits: list[int] = []

    def put(val: int, n: int) -> None:
        bits.extend((val >> (n - 1 - i)) & 1 for i in range(n))

    put(0b0100, 4)
    put(len(payload), 8 if version <= 9 else 16)
    for b in payload:
        put(b, 8)
    cap_bits = _capacity(version, level) * 8
    put(0, min(4, cap_bits - len(bits)))
    if len(bits) % 8:
        put(0, 8 - len(bits) % 8)
    pad = 0xEC
    while len(bits) < cap_bits:
        put(pad, 8)
        pad ^= 0xEC ^ 0x11
    return [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]


def _interleave(data: list[int], version: int, level: str) -> list[int]:
    ec_len, groups = _BLOCKS[version][level]
    blocks: list[list[int]] = []
    pos = 0
    for count, size in groups:
        for _ in range(count):
            blocks.append(data[pos:pos + size])
            pos += size
    ecs = [rs_remainder(b, ec_len) for b in blocks]
    out: list[int] = []
    for i in range(max(len(b) for b in blocks)):
        out.extend(b[i] for b in blocks if i < len(b))
    for i in range(ec_len):
        out.extend(e[i] for e in ecs)
    return out


class _Matrix:
    def __init__(self, version: int) -> None:
        self.v = version
        self.n = 17 + 4 * version
        self.m = [[False] * self.n for _ in range(self.n)]
        self.fixed = [[False] * self.n for _ in range(self.n)]

    def set(self, x: int, y: int, dark: bool) -> None:
        self.m[y][x] = dark
        self.fixed[y][x] = True

    def function_patterns(self) -> None:
        n = self.n
        for i in range(n):
            self.set(6, i, i % 2 == 0)
            self.set(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < n and 0 <= y < n:
                        d = max(abs(dx), abs(dy))
                        self.set(x, y, d not in (2, 4))
        al = _ALIGN[self.v]
        for i, ax in enumerate(al):
            for j, ay in enumerate(al):
                if (i == 0 and j == 0) or (i == 0 and j == len(al) - 1) or (i == len(al) - 1 and j == 0):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self.set(ax + dx, ay + dy, max(abs(dx), abs(dy)) != 1)
        self.format_area(0, "L")  # reserve
        if self.v >= 7:
            vb = _version_bits(self.v)
            for i in range(18):
                bit = bool(vb >> i & 1)
                a, b = n - 11 + i % 3, i // 3
                self.set(a, b, bit)
                self.set(b, a, bit)

    def format_area(self, mask: int, level: str) -> None:
        n = self.n
        fb = _format_bits(level, mask)
        bit = [bool(fb >> i & 1) for i in range(15)]
        for i in range(6):
            self.set(8, i, bit[i])
        self.set(8, 7, bit[6])
        self.set(8, 8, bit[7])
        self.set(7, 8, bit[8])
        for i in range(9, 15):
            self.set(14 - i, 8, bit[i])
        for i in range(8):
            self.set(n - 1 - i, 8, bit[i])
        for i in range(8, 15):
            self.set(8, n - 15 + i, bit[i])
        self.set(8, n - 8, True)  # dark module

    def place(self, codewords: list[int]) -> None:
        n = self.n
        i = 0
        total = len(codewords) * 8
        right = n - 1
        while right >= 1:
            if right == 6:
                right = 5
            for vert in range(n):
                for j in range(2):
                    x = right - j
                    upward = ((right + 1) & 2) == 0
                    y = n - 1 - vert if upward else vert
                    if not self.fixed[y][x] and i < total:
                        self.m[y][x] = bool(codewords[i >> 3] >> (7 - (i & 7)) & 1)
                        i += 1
            right -= 2

    def apply_mask(self, mask: int) -> None:
        for y in range(self.n):
            for x in range(self.n):
                if self.fixed[y][x]:
                    continue
                if mask == 0:
                    inv = (x + y) % 2 == 0
                elif mask == 1:
                    inv = y % 2 == 0
                elif mask == 2:
                    inv = x % 3 == 0
                elif mask == 3:
                    inv = (x + y) % 3 == 0
                elif mask == 4:
                    inv = (x // 3 + y // 2) % 2 == 0
                elif mask == 5:
                    inv = x * y % 2 + x * y % 3 == 0
                elif mask == 6:
                    inv = (x * y % 2 + x * y % 3) % 2 == 0
                else:
                    inv = ((x + y) % 2 + x * y % 3) % 2 == 0
                if inv:
                    self.m[y][x] = not self.m[y][x]

    def penalty(self) -> int:
        n, m = self.n, self.m
        score = 0
        lines = [m[y] for y in range(n)] + [[m[y][x] for y in range(n)] for x in range(n)]
        pat1 = [True, False, True, True, True, False, True, False, False, False, False]
        pat2 = pat1[::-1]
        for line in lines:
            run, prev = 0, None
            for c in line:
                if c == prev:
                    run += 1
                else:
                    if run >= 5:
                        score += 3 + run - 5
                    run, prev = 1, c
            if run >= 5:
                score += 3 + run - 5
            for k in range(n - 10):
                seg = line[k:k + 11]
                if seg == pat1 or seg == pat2:
                    score += 40
        for y in range(n - 1):
            for x in range(n - 1):
                c = m[y][x]
                if c == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                    score += 3
        dark = sum(sum(r) for r in m)
        total = n * n
        k = abs(dark * 20 - total * 10) // total
        score += k * 10
        return score


def encode(text: str | bytes, level: str = "M", *, min_version: int = 1, mask: int | None = None) -> list[list[bool]]:
    """Returns the module matrix (True = dark), without the quiet zone."""
    if level not in _LEVEL_BITS:
        raise QrError("level must be L, M, Q or H")
    payload = text.encode("utf-8") if isinstance(text, str) else bytes(text)
    for version in range(max(1, min_version), MAX_VERSION + 1):
        header = 4 + (8 if version <= 9 else 16)
        if header + 8 * len(payload) <= _capacity(version, level) * 8:
            break
    else:
        raise QrError(f"payload of {len(payload)} bytes does not fit QR version {MAX_VERSION}-{level}")
    codewords = _interleave(_encode_data(payload, version, level), version, level)
    best: tuple[int, list[list[bool]]] | None = None
    for mk in ([mask] if mask is not None else range(8)):
        mx = _Matrix(version)
        mx.function_patterns()
        mx.place(codewords)
        mx.apply_mask(mk)
        mx.format_area(mk, level)
        p = mx.penalty()
        if best is None or p < best[0]:
            best = (p, mx.m)
    assert best is not None
    return best[1]


def to_rows(matrix: list[list[bool]]) -> list[str]:
    return ["".join("1" if c else "0" for c in row) for row in matrix]


def draw(canvas: Any, matrix: list[list[bool]], *, x: int = 0, y: int = 0, module: int = 6, quiet: int = 4,
         dark: str = "#000000", light: str = "#ffffff", tag: str = "qr") -> int:
    """Draws the code on a Tk Canvas (always dark-on-light, also in the dark theme, so phones can scan it).
    Horizontal runs of dark modules are merged into one rectangle. Returns the drawn side length in pixels."""
    n = len(matrix)
    side = (n + 2 * quiet) * module
    canvas.delete(tag)
    canvas.create_rectangle(x, y, x + side, y + side, fill=light, outline=light, tags=(tag,))
    for r, row in enumerate(matrix):
        c = 0
        while c < n:
            if row[c]:
                s = c
                while c < n and row[c]:
                    c += 1
                x0 = x + (quiet + s) * module
                y0 = y + (quiet + r) * module
                canvas.create_rectangle(x0, y0, x + (quiet + c) * module - 1, y0 + module - 1,
                                        fill=dark, outline=dark, tags=(tag,))
            else:
                c += 1
    return side
