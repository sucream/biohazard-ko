"""Minimal BDF bitmap font parser."""


class Glyph:
    __slots__ = ('w', 'h', 'xoff', 'yoff', 'dwidth', 'rows')


def load_bdf(path):
    glyphs = {}
    ascent = descent = 0
    with open(path, encoding='utf-8', errors='replace') as f:
        lines = iter(f.read().splitlines())
    cur = None
    enc = None
    for line in lines:
        if line.startswith('FONT_ASCENT'):
            ascent = int(line.split()[1])
        elif line.startswith('FONT_DESCENT'):
            descent = int(line.split()[1])
        elif line.startswith('STARTCHAR'):
            cur = Glyph()
            enc = None
        elif line.startswith('ENCODING'):
            enc = int(line.split()[1])
        elif line.startswith('DWIDTH'):
            cur.dwidth = int(line.split()[1])
        elif line.startswith('BBX'):
            _, w, h, xo, yo = line.split()
            cur.w, cur.h, cur.xoff, cur.yoff = int(w), int(h), int(xo), int(yo)
        elif line.startswith('BITMAP'):
            rows = []
            for _ in range(cur.h):
                hx = next(lines).strip()
                v = int(hx, 16) if hx else 0
                nbits = len(hx) * 4
                rows.append([(v >> (nbits - 1 - i)) & 1 for i in range(cur.w)])
            cur.rows = rows
            if enc is not None and enc >= 0:
                glyphs[enc] = cur
    return glyphs, ascent, descent


def render(glyph, ascent, size_w, size_h, ox=0, oy=0):
    """Place glyph on a size_w x size_h grid using baseline=ascent. Returns 2D list of 0/1."""
    g = [[0] * size_w for _ in range(size_h)]
    top = ascent - glyph.yoff - glyph.h
    for r in range(glyph.h):
        for c in range(glyph.w):
            if glyph.rows[r][c]:
                x, y = glyph.xoff + c + ox, top + r + oy
                if 0 <= x < size_w and 0 <= y < size_h:
                    g[y][x] = 1
    return g
