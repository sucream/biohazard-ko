"""PlayStation TIM image read/write (used by Biohazard PC)."""
import struct
from PIL import Image


def c15_to_rgba(c):
    r = (c & 31) << 3
    g = ((c >> 5) & 31) << 3
    b = ((c >> 10) & 31) << 3
    stp = c >> 15
    a = 0 if c == 0 else 255
    return (r, g, b, a)


class Tim:
    def __init__(self, data):
        magic, flags = struct.unpack_from('<II', data, 0)
        assert magic == 0x10, 'not a TIM'
        self.bpp_mode = flags & 7
        self.has_clut = bool(flags & 8)
        p = 8
        self.clut = None
        if self.has_clut:
            ln, cx, cy, cw, ch = struct.unpack_from('<IHHHH', data, p)
            self.clut_xy = (cx, cy)
            self.clut_w, self.clut_h = cw, ch
            self.clut = list(struct.unpack_from('<%dH' % (cw * ch), data, p + 12))
            p += ln
        ln, ix, iy, iw, ih = struct.unpack_from('<IHHHH', data, p)
        self.img_xy = (ix, iy)
        self.vram_w, self.h = iw, ih
        self.pix = bytearray(data[p + 12:p + ln])
        self.end = p + ln
        self.width = iw * {0: 4, 1: 2, 2: 1, 3: 1}[self.bpp_mode]
        if self.bpp_mode == 3:
            self.width = iw * 2 // 3

    def indices(self):
        """Return list of pixel index values (4/8 bit modes)."""
        if self.bpp_mode == 0:
            out = []
            for b in self.pix:
                out.append(b & 15)
                out.append(b >> 4)
            return out
        if self.bpp_mode == 1:
            return list(self.pix)
        raise ValueError

    def set_indices(self, idx):
        if self.bpp_mode == 0:
            self.pix = bytearray((idx[i] & 15) | ((idx[i + 1] & 15) << 4) for i in range(0, len(idx), 2))
        else:
            self.pix = bytearray(idx)

    def to_image(self, clut_row=0):
        w, h = self.width, self.h
        im = Image.new('RGBA', (w, h))
        if self.bpp_mode in (0, 1):
            n = 16 if self.bpp_mode == 0 else 256
            pal = self.clut[clut_row * self.clut_w:clut_row * self.clut_w + n]
            pal = [c15_to_rgba(c) for c in pal] + [(0, 0, 0, 0)] * (n - len(pal))
            im.putdata([pal[i] for i in self.indices()])
        elif self.bpp_mode == 2:
            im.putdata([c15_to_rgba(c) for c in struct.unpack('<%dH' % (w * h), bytes(self.pix[:w * h * 2]))])
        return im


def load(path):
    return Tim(open(path, 'rb').read())


def build_4bpp(width, height, clut_rows, indices, img_xy=(0, 0), clut_xy=(256, 480)):
    """Serialize a 4bpp TIM with the given CLUT rows (list of 16-entry lists)."""
    clut = b''.join(struct.pack('<16H', *row) for row in clut_rows)
    out = struct.pack('<II', 0x10, 8)
    out += struct.pack('<IHHHH', 12 + len(clut), clut_xy[0], clut_xy[1], 16, len(clut_rows)) + clut
    pix = bytes((indices[i] & 15) | ((indices[i + 1] & 15) << 4) for i in range(0, len(indices), 2))
    out += struct.pack('<IHHHH', 12 + len(pix), img_xy[0], img_xy[1], width // 4, height) + pix
    return out
