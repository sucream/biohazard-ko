"""Helpers for writing generated C headers."""

DYN_TYPEDEF = ['#ifndef KO_DYN_T', '#define KO_DYN_T',
               'typedef struct { uint32_t off; uint16_t start, count; } ko_dyn;', '#endif']


def byte_array(name, data, const=True):
    lines = ['static %suint8_t %s[%d] = {' % ('const ' if const else '', name, max(1, len(data)))]
    for i in range(0, len(data), 24):
        lines.append('  ' + ','.join('0x%02x' % x for x in data[i:i + 24]) + ',')
    if not data:
        lines.append('  0')
    lines.append('};')
    return lines


def dyn_tables(prefix, dyns):
    """dyns: list of (blob offset, [atlas ids]) for messages that use the
    dynamic glyph area. Emits <prefix>_dyn (sorted) and <prefix>_dyn_list."""
    dyns = sorted((o, l) for o, l in dyns if l)
    flat = []
    rows = []
    for off, ids in dyns:
        rows.append('  {%d, %d, %d},' % (off, len(flat), len(ids)))
        flat += ids
    lines = ['#define KO_NUM_%s_DYN %d' % (prefix.upper().replace('KO_', ''), len(rows)),
             'static const uint16_t %s_dyn_list[%d] = {%s};' % (prefix, max(1, len(flat)),
                                                              ','.join(map(str, flat)) or '0'),
             'static const ko_dyn %s_dyn[%d] = {' % (prefix, max(1, len(rows)))]
    lines += rows or ['  {0xffffffff, 0, 0}']
    lines.append('};')
    return lines
