"""Render Korean versions of the image-based texts.

Documents (Item_m2/TEXTM_*.TIM, 256x256 8bpp) hold two 256x128 screens each
(top and bottom half). translations/documents.json gives the Korean text of
every half page:

  {"file": "TEXTM_N1", "half": 0, "jp": "...", "ko": "..."}

Line markup in 'ko': a line starting with '^' is centred, '>' right-aligned,
an empty line is a paragraph gap. Text is drawn with NanumMyeongjo (OFL).

Output: build/JPN/Item_m2/TEXTM_*.TIM
"""
import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(__file__))
import tim

ROOT = os.path.join(os.path.dirname(__file__), '..')
FONT = os.path.join(ROOT, 'fonts', 'NanumMyeongjo.ttf')
FONT_TITLE = os.path.join(ROOT, 'fonts', 'NanumMyeongjoBold.ttf')
SIZE = 12
PITCH = 15
GAP = 7
TOP = 6
LEFT, RIGHT = 10, 246
HALF_H = 128


def font(title=False):
    return ImageFont.truetype(FONT_TITLE if title else FONT, SIZE + (1 if title else 0))


def text_width(s, title=False):
    return font(title).getlength(s)


def layout(text):
    """Yield (y, x, string, title) for a half page; raises if it overflows."""
    y = TOP
    out = []
    for raw in text.split('\n'):
        if not raw.strip():
            y += GAP
            continue
        title = raw.startswith('#')
        line = raw.lstrip('#')
        align = 'l'
        if line[:1] in '^>':
            align, line = line[0], line[1:]
        w = text_width(line, title)
        if w > RIGHT - LEFT:
            raise ValueError('line too wide (%dpx): %s' % (w, line))
        x = LEFT if align == 'l' else (RIGHT - w if align == '>' else (256 - w) / 2)
        out.append((y, x, line, title))
        y += PITCH
    if y - PITCH + SIZE + 2 > HALF_H:
        raise ValueError('page too long (%d px)' % y)
    return out


def render_half(text):
    im = Image.new('L', (256, HALF_H), 0)
    d = ImageDraw.Draw(im)
    for y, x, line, title in layout(text):
        d.text((x, y), line, fill=255, font=font(title))
    return im


def to_indices(im, ramp):
    """Map 0..255 grey to the palette ramp (list of (level, index))."""
    px = im.load()
    out = []
    for y in range(im.height):
        for x in range(im.width):
            v = px[x, y]
            best = min(ramp, key=lambda r: abs(r[0] - v))
            out.append(best[1])
    return out


def palette_ramp(t):
    """Grey ramp of a document TIM: (brightness 0..255, index) for its greys."""
    ramp = []
    for i, c in enumerate(t.clut[:16]):
        r, g, b = c & 31, (c >> 5) & 31, (c >> 10) & 31
        if i == 0 or (r == g == b):
            ramp.append(((r * 255) // 31, i))
    lo = min(ramp)[0]
    hi = max(ramp)[0]
    return [(int((v - lo) * 255 / max(1, hi - lo)), i) for v, i in ramp]


# ------------------------------------------------------------ UI images --

UI_FONT = os.path.join(ROOT, 'fonts', 'NanumGothicExtraBold.ttf')
UI_FONT_REG = os.path.join(ROOT, 'fonts', 'NanumGothicBold.ttf')

# inventory menu buttons in STATUS.TIM: (top row of button, label)
STATUS_BUTTONS = [(2, '장비'), (26, '사용'), (50, '조사'), (74, '조합')]

# key-config help (OPTKEY03.TIM): one text box drawn from two strips;
# strip A = x 0..171, y 107..139 (3 lines), strip B = x 0..124, y 141..164
# (right halves of lines 1-2)
OPTKEY_LINES = [
    '설정을 바꿀 항목에 커서를 맞추고 버튼을 누른 뒤 방향키',
    '좌우로 바꿀 수 있습니다. 결정할 때는 다시 키를 누르세요.',
    'EXIT를 선택하면 종료합니다.',
]


def rgb15(c):
    return ((c & 31) << 3, ((c >> 5) & 31) << 3, ((c >> 10) & 31) << 3)


def to15(rgb):
    r, g, b = rgb
    v = (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10)
    return v if v else 0x8000  # 0 is transparent on the PSX


def outlined_text(size, text, fontpath, fill, outline, width_px, height_px):
    """RGBA image of centred text with a 1px outline."""
    f = ImageFont.truetype(fontpath, size)
    im = Image.new('RGBA', (width_px, height_px), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    w = f.getlength(text)
    bb = f.getbbox(text)
    x = (width_px - w) / 2
    y = (height_px - (bb[3] - bb[1])) / 2 - bb[1]
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx or dy:
                d.text((x + dx, y + dy), text, font=f, fill=outline)
    d.text((x, y), text, font=f, fill=fill)
    return im


def edit_status(raw):
    t = tim.Tim(raw)
    pal = [rgb15(c) for c in t.clut[:256]]
    img = t.to_image().convert('RGB')
    for top, label in STATUS_BUTTONS:
        x0, x1, y0, y1 = 50, 94, top + 2, top + 18
        for y in range(y0, y1):
            for x in range(x0, x1):
                r, g, b = img.getpixel((x, y))
                if r == g == b:
                    img.putpixel((x, y), (8, 0, 80))
        lab = outlined_text(15, label, UI_FONT, (248, 248, 248, 255), (24, 24, 24, 255), x1 - x0, y1 - y0)
        img.paste(lab, (x0, y0), lab)
    idx = t.indices()
    cache = {}
    for y in range(0, 96):
        for x in range(48, 96):
            c = img.getpixel((x, y))
            if c not in cache:
                cache[c] = min(range(len(pal)), key=lambda i: sum((a - b) ** 2 for a, b in zip(pal[i], c)))
            idx[y * t.width + x] = cache[c]
    t.set_indices(idx)
    return raw[:t.end - len(t.pix)] + bytes(t.pix) + raw[t.end:]


def edit_optkey(raw):
    t = tim.Tim(raw)
    img = t.to_image().convert('RGB')
    w = t.width
    # erase dark text pixels with the paper colour of their neighbourhood
    for (x0, y0, x1, y1) in ((0, 107, 172, 140), (0, 141, 125, 165)):
        px = [[img.getpixel((x, y)) for x in range(x0, x1)] for y in range(y0, y1)]
        def light(c):
            return sum(c) > 380
        for yy in range(y1 - y0):
            for xx in range(x1 - x0):
                if not light(px[yy][xx]):
                    acc = [0, 0, 0]
                    n = 0
                    for r in range(1, 12):
                        for dy, dx in ((0, r), (0, -r), (r, 0), (-r, 0)):
                            ny, nx = yy + dy, xx + dx
                            if 0 <= ny < y1 - y0 and 0 <= nx < x1 - x0 and light(px[ny][nx]):
                                c = px[ny][nx]
                                acc = [a + b for a, b in zip(acc, c)]
                                n += 1
                        if n >= 4:
                            break
                    if n:
                        img.putpixel((x0 + xx, y0 + yy), tuple(a // n for a in acc))
    # draw the 3 lines on a 297 px canvas and cut it into the two strips
    f = ImageFont.truetype(UI_FONT_REG, 10)
    canvas = Image.new('RGBA', (297, 3 * 11), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    for i, line in enumerate(OPTKEY_LINES):
        if f.getlength(line) > (297 if i < 2 else 172) - 6:
            raise ValueError('OPTKEY line too long: ' + line)
        d.text((5, i * 11), line, font=f, fill=(40, 28, 24, 255))
    a = canvas.crop((0, 0, 172, 33))
    b = canvas.crop((172, 0, 297, 22))
    img.paste(a, (0, 107), a)
    img.paste(b, (0, 141), b)
    vals = [to15(img.getpixel((x, y))) for y in range(t.h) for x in range(w)]
    pix = bytearray(t.pix)
    for y in range(100, 170):
        for x in range(0, 176):
            o = (y * w + x) * 2
            orig = pix[o] | (pix[o + 1] << 8)
            v = vals[y * w + x] | (orig & 0x8000)
            pix[o], pix[o + 1] = v & 0xff, v >> 8
    return raw[:t.end - len(t.pix)] + bytes(pix) + raw[t.end:]


def build_ui(game_dir):
    src = os.path.join(game_dir, 'japanese', 'JPN', 'Data')
    out = os.path.join(ROOT, 'build', 'JPN', 'Data')
    os.makedirs(out, exist_ok=True)
    for name, fn in (('STATUS.TIM', edit_status), ('OPTKEY03.TIM', edit_optkey)):
        real = [f for f in os.listdir(src) if f.upper() == name][0]
        open(os.path.join(out, real), 'wb').write(fn(open(os.path.join(src, real), 'rb').read()))
    print('ui images: STATUS.TIM, OPTKEY03.TIM')


def main(game_dir):
    build_ui(game_dir)
    path = os.path.join(ROOT, 'translations', 'documents.json')
    if not os.path.exists(path):
        return
    docs = json.load(open(path, encoding='utf-8'))
    src = os.path.join(game_dir, 'japanese', 'JPN', 'Item_m2')
    out = os.path.join(ROOT, 'build', 'JPN', 'Item_m2')
    os.makedirs(out, exist_ok=True)
    pages = {}
    for e in docs:
        if e.get('ko') is None:
            continue
        pages.setdefault(e['file'], {})[e['half']] = (e['ko'], e.get('keep', []))
    n = 0
    for name, halves in sorted(pages.items()):
        fn = [f for f in os.listdir(src) if f.upper() == name.upper() + '.TIM'][0]
        raw = open(os.path.join(src, fn), 'rb').read()
        t = tim.Tim(raw)
        idx = t.indices()
        ramp = palette_ramp(t)
        for half, (text, keep) in halves.items():
            sub = to_indices(render_half(text), ramp)
            base = half * HALF_H * 256
            # 'keep' boxes (x0, y0, x1, y1) retain original pixels, e.g. pictograms
            for x0, y0, x1, y1 in keep:
                for y in range(y0, y1):
                    for x in range(x0, x1):
                        sub[y * 256 + x] = idx[base + y * 256 + x]
            idx[base:base + HALF_H * 256] = sub
        t.set_indices(idx)
        hdr_end = len(raw) - len(t.pix)
        open(os.path.join(out, fn), 'wb').write(raw[:t.end - len(t.pix)] + bytes(t.pix) + raw[t.end:])
        n += 1
    print('documents: %d pages rendered' % n)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, '4249100_Biohazard'))
