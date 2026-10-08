"""Korean text <-> Biohazard (PC JP) byte encoding.

Text format (same as jptable.decode output):
  <END:n> <PAGE:n> <C4:n> <COL:n> <ITEM:n> <YESNO:n> <RET>   control codes
  '\n'  new line,  '　' (U+3000) full-width space (one cell),
  ' '   half-width space (byte FF, half a cell)
Everything else is a glyph. ASCII digits/letters and a few symbols use the
game's fixed cells; all other glyphs come from the generated charmap.

Code space for allocated glyphs (see build_font.py):
  single byte  0x57..0xF7          -> page0 cells 87..247
  F8 xx        xx=0x1E..0x35       -> page0 cells 264..287
  F9 xx / FA xx                    -> page1 cells 0..251 / 252..323
  FC/FD/FE xx  E=(p-FC)*256+xx     -> page2 (E<324) / page3 (E-324)
"""
import json
import os
import re
import unicodedata

TAG_RE = re.compile(r'<(END|PAGE|C4|COL|ITEM|YESNO):(\d+)>|<RET>')
TAG_CODE = {'END': 1, 'PAGE': 3, 'C4': 4, 'COL': 5, 'ITEM': 6, 'YESNO': 8}

FIXED = {}
for i, c in enumerate('0123456789'):
    FIXED[c] = bytes([12 + i])
for i in range(26):
    FIXED[chr(65 + i)] = bytes([29 + i])
    FIXED[chr(97 + i)] = bytes([61 + i])
FIXED.update({
    ':': b'\x16', ',': b'\x17', '.': b'\x18', '"': b'\x19', '”': b'\x19', '“': b'\x19',
    '!': b'\x1a', '?': b'\x1b', '⁉': b'\x1c', '[': b'\x37', '/': b'\x38', ']': b'\x39',
    "'": b'\x3a', '’': b'\x3a', '‘': b'\x3a', '-': b'\x3b', 'ー': b'\x3b', '·': b'\x3c', '・': b'\x3c',
    '■': b'\x01', '▶': b'\x02', '△': b'\x07', '○': b'\x08', '×': b'\x09', '□': b'\x0a', '▼': b'\x0b',
    '―': b'\xf8\x0f', '「': b'\xf8\x10', '」': b'\xf8\x11', '(': b'\xf8\x16', ')': b'\xf8\x17',
    '『': b'\xf8\x18', '』': b'\xf8\x19',
    '　': b'\x00', ' ': b'\xff',
})
STARS = ('S.T.A.R.S.', b'\xf8\x12\xf8\x13\xf8\x14\xf8\x15\xf8\x12')

LINE_CELLS = 20      # message window width in cells
CENTER_CELLS = 18    # subtitles are block-centred in this width


DYN_CELLS = 200      # page-1 cells 0..199 are refilled per message by the DLL


def cell_to_code(cell):
    """Static glyph cell index (global) -> byte code."""
    if 87 <= cell <= 247:
        return bytes([cell])
    if 264 <= cell <= 287:
        return bytes([0xF8, cell - 234])
    c = cell - 288
    if DYN_CELLS <= c < 252:
        return bytes([0xF9, c])
    if 252 <= c < 324:
        return bytes([0xFA, c - 252])
    raise ValueError(cell)


class Codec:
    def __init__(self, charmap_path=None):
        if charmap_path is None:
            charmap_path = os.path.join(os.path.dirname(__file__), '..', 'build', 'charmap.json')
        cm = json.load(open(charmap_path, encoding='utf-8'))
        self.cells = cm['static']
        self.codes = {ch: cell_to_code(c) for ch, c in self.cells.items()}
        self.atlas = {ch: i for i, ch in enumerate(cm['dynamic'])}

    def encode(self, text, dynamic=True):
        """Encode text. Returns (bytes, dyn) where dyn lists the atlas ids
        of glyphs placed in the dynamic page area (cell i = dyn[i])."""
        out = bytearray()
        dyn = []
        i = 0
        while i < len(text):
            m = TAG_RE.match(text, i)
            if m:
                if m.group(0) == '<RET>':
                    out.append(7)
                else:
                    out += bytes([TAG_CODE[m.group(1)], int(m.group(2))])
                i = m.end()
                continue
            if text.startswith(STARS[0], i):
                out += STARS[1]
                i += len(STARS[0])
                continue
            ch = text[i]
            i += 1
            if ch == chr(10):
                out.append(2)
            elif ch in FIXED:
                out += FIXED[ch]
            elif ch in self.codes:
                out += self.codes[ch]
            elif ch in self.atlas:
                if not dynamic:
                    raise KeyError('glyph %r is not in the static set' % ch)
                gid = self.atlas[ch]
                if gid not in dyn:
                    dyn.append(gid)
                k = dyn.index(gid)
                if k >= DYN_CELLS:
                    raise ValueError('too many distinct glyphs in one message')
                out += bytes([0xF9, k])
            else:
                raise KeyError('no glyph for %r (U+%04X)' % (ch, ord(ch)))
        return bytes(out), dyn


def glyph_chars(text):
    """Characters of text that need an allocated glyph."""
    text = TAG_RE.sub('', text).replace(STARS[0], '')
    return [c for c in text if c not in FIXED and c != '\n']


def width(line):
    """Display width of a line in cells (half-width space = 0.5)."""
    s = TAG_RE.sub('', line).replace(STARS[0], 'SSSSS')
    return sum(0.5 if c == ' ' else 1 for c in s)


def normalize(text):
    return unicodedata.normalize('NFC', text)


# ---------------------------------------------------------------- layout --

def _split_pages(text):
    """Split into pages at PAGE/END tags; returns list of (body, terminator_tag)."""
    parts = []
    pos = 0
    for m in re.finditer(r'<(PAGE|END):\d+>', text):
        parts.append((text[pos:m.start()], m.group(0)))
        pos = m.end()
    parts.append((text[pos:], ''))
    return parts


_LEAD_RE = re.compile(r'^((?:<C4:\d+>|<COL:\d+>)*)([　]*)')


def _line_info(line):
    m = _LEAD_RE.match(line)
    return m.group(1), len(m.group(2)), line[m.end():]


def layout(ko, jp):
    """Re-create the original's centring for a Korean message.

    For each page, if the Japanese page indents its lines with full-width
    spaces, the Korean page is block-centred in CENTER_CELLS using full and
    half-width spaces. Leading spaces typed in the Korean text are discarded.
    """
    jp_pages = _split_pages(jp)
    ko_pages = _split_pages(ko)
    out = []
    for pi, (body, term) in enumerate(ko_pages):
        jbody = jp_pages[pi][0] if pi < len(jp_pages) else ''
        jlines = jbody.split('\n')
        jcent = [_line_info(l)[1] > 0 and bool(_line_info(l)[2].strip('　')) for l in jlines]
        lines = body.split('\n')
        infos = [_line_info(l) for l in lines]
        texts = [t.strip(' 　') for _, _, t in infos]
        if len(lines) == len(jlines):
            cent = jcent
        else:
            cent = [any(jcent)] * len(lines)
            if 'YESNO' in term or 'YESNO' in body:
                cent[-1] = False
        if any(cent):
            w = max([width(t) for t, c in zip(texts, cent) if t and c] or [0])
            pad = max(0, int(CENTER_CELLS - w))  # indent in half cells
            sp = '　' * (pad // 2) + (' ' if pad % 2 else '')
            new = []
            for (pre, _, _), t, c in zip(infos, texts, cent):
                new.append(pre + (sp if c and t else '') + t)
            body = '\n'.join(new)
        out.append(body + term)
    return ''.join(out)


def check(ko, max_cells=LINE_CELLS):
    """Return list of problems for a laid-out Korean message."""
    probs = []
    # bytes between <YESNO:n> and <END:n> are choice parameters, not text
    ko = re.sub(r'(<YESNO:\d+>).*?(<END:\d+>)', r'\1\2', ko, flags=re.S)
    for body, _ in _split_pages(ko):
        lines = body.split('\n')
        if len(lines) > 2:
            probs.append('page has %d lines' % len(lines))
        for l in lines:
            if width(l) > max_cells:
                probs.append('line too wide (%.1f): %s' % (width(l), TAG_RE.sub('', l)))
    return probs
