"""Biohazard (PC) RDT room file helpers: message block access."""
import struct

HDR_OFFS = 0x48  # 19 dword section offsets
TEXT_IDX = 11


def offsets(d):
    return list(struct.unpack_from('<19I', d, HDR_OFFS))


def is_room(d):
    return len(d) >= 0x100


def split_messages(blk):
    if len(blk) < 2:
        return []
    n = struct.unpack_from('<H', blk, 0)[0] // 2
    tab = struct.unpack_from('<%dH' % n, blk, 0)
    return [blk[tab[i]:(tab[i + 1] if i + 1 < n else len(blk))] for i in range(n)]


def text_block(d):
    o = offsets(d)
    return d[o[TEXT_IDX]:o[TEXT_IDX + 1]]


def messages(d):
    return split_messages(text_block(d))


def build_block(msgs):
    n = len(msgs)
    out = bytearray(2 * n)
    pos = 2 * n
    for i, m in enumerate(msgs):
        struct.pack_into('<H', out, 2 * i, pos)
        out += m
        pos += len(m)
    if pos > 0xFFFF:
        raise ValueError('text block too large')
    return bytes(out)


def replace_text(d, msgs):
    """Append a new text block at the end of the file and point the header at it.

    Other sections contain absolute file offsets, so nothing else is moved; the
    old block stays as dead data.
    """
    blk = build_block(msgs)
    d = bytearray(d)
    while len(d) % 4:
        d.append(0)
    new_off = len(d)
    d += blk
    while len(d) % 4:
        d.append(0)
    struct.pack_into('<I', d, HDR_OFFS + 4 * TEXT_IDX, new_off)
    return bytes(d)


EN_TABLE = (' ■▶①②③④△○×□▼0123456789:;,"!?⁉ABCDEFGHIJKLMNOPQRSTUVWXYZ(/)\'-·'
            'abcdefghijklmnopqrstuvwxyzÄäÖöÜüßÀàÂâÈèÉéÊêÏïÎîÔôÙùÛûÇçSTAR".…—+=')


def decode_en(m):
    out = []
    i = 0
    while i < len(m):
        b = m[i]
        if b == 1:
            out.append('<END:%d>' % (m[i + 1] if i + 1 < len(m) else 0)); i += 2
        elif b == 2:
            out.append('\n'); i += 1
        elif b in (3, 4, 5, 6, 8):
            out.append('<%s:%d>' % ({3: 'PAGE', 4: 'C4', 5: 'COL', 6: 'ITEM', 8: 'YESNO'}[b], m[i + 1])); i += 2
        elif b == 7:
            out.append('<RET>'); i += 1
        else:
            out.append(EN_TABLE[b] if b < len(EN_TABLE) else '{%02X}' % b); i += 1
    return ''.join(out)
