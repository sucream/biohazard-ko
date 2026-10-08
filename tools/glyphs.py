"""Render Hangul/ASCII glyphs into 14x14 cells in the game's outlined font style."""
import os
from bdf import load_bdf, render

GAL = os.path.join(os.path.dirname(__file__), '..', 'fonts')
FILL, OUTLINE = 1, 8
_cache = {}


def font(name='Galmuri11-Bold.bdf'):
    if name not in _cache:
        _cache[name] = load_bdf(os.path.join(GAL, name))
    return _cache[name]


def cell(ch, name='Galmuri11-Bold.bdf', fallback='Galmuri11.bdf'):
    """Return 14x14 list of palette indices (0 transparent, 1 fill, 8 outline, 6 shade)."""
    glyphs, asc, _ = font(name)
    g = glyphs.get(ord(ch))
    if g is None:
        glyphs, asc, _ = font(fallback)
        g = glyphs[ord(ch)]
    # body area 12x12 inside cell with 1px outline margin; center horizontally
    bw = g.w + g.xoff
    ox = 1 + max(0, (12 - bw) // 2) if ord(ch) >= 0x1100 else 1
    oy = 1 - (asc - 11 - 0) - 0  # put cap/hangul top near y=1
    bmp = render(g, asc, 14, 14, ox, 0)
    # shift so that hangul (yoff=0, h=11) sits at rows 1..11 (outline 0..12)
    top = min((y for y in range(14) if any(bmp[y])), default=0)
    if ord(ch) >= 0x1100:
        shift = 1 - top
    else:
        shift = (asc - 11 - 1)  # baseline-based for latin: baseline at row 12
        shift = -shift
    out = [[0] * 14 for _ in range(14)]
    for y in range(14):
        for x in range(14):
            if bmp[y][x]:
                ny = y + shift
                if 0 <= ny < 14:
                    out[ny][x] = FILL
    res = [row[:] for row in out]
    for y in range(14):
        for x in range(14):
            if out[y][x] == 0:
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        yy, xx = y + dy, x + dx
                        if 0 <= yy < 14 and 0 <= xx < 14 and out[yy][xx] == FILL:
                            res[y][x] = OUTLINE
    return res
