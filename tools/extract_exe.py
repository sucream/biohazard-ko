"""Extract the Japanese strings embedded in Biohazard.exe (from an unpacked
memory dump) together with every place that references them.

Writes translations/exe_strings.json. Existing 'ko' values are preserved.
"""
import json
import os
import pickle
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
import jptable

B = 0x400000
DUMP, INS, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
d = open(DUMP, 'rb').read()
ins = pickle.load(open(INS, 'rb'))  # [(addr, mnemonic, op_str, size)]


def rd(a):
    return struct.unpack_from('<I', d, a - B)[0]


def str_bytes(a, kind):
    """Raw bytes of a string, including its terminator."""
    i = a - B
    if kind == 'ascii':
        return d[i:d.index(0, i) + 1]
    while True:
        b = d[i]
        if kind == 'item' and b == 7:
            return d[a - B:i + 1]
        if kind != 'item' and b == 1:
            return d[a - B:i + 2] if kind == 'msg' else d[a - B:i + 1]
        if kind == 'menu' and b == 0xFB:
            i += 1
        elif b >= 0xF8 or (kind == 'msg' and b in (3, 4, 5, 6, 8)):
            i += 2
        else:
            i += 1


def code_refs(addr):
    """Operand addresses in code that hold the immediate/displacement addr."""
    out = []
    needle = struct.pack('<I', addr)
    h = hex(addr)
    for a, m, o, s in ins:
        if h in o.split() or ('+ ' + h + ']') in o or o.endswith(h) or ('[' + h + ']') in o:
            raw = d[a - B:a - B + s]
            k = raw.find(needle)
            if k >= 0:
                out.append(a + k)
    return out


entries = []
by_key = {}


def add(kind, addr, site, group, fixed=None):
    key = (kind, addr)
    if key not in by_key:
        raw = str_bytes(addr, kind)
        body = raw[:-1] if kind == 'item' else (raw[:-1].replace(bytes([0xFB]), b'') if kind == 'menu' else raw)
        jp = raw[:-1].decode('ascii') if kind == 'ascii' else jptable.decode(body, ctrl=(kind == 'msg'))
        e = {'id': '%s_%06x' % (kind, addr), 'group': group, 'kind': kind, 'addr': '%06x' % addr,
             'jp': jp, 'ko': '', 'sites': []}
        if fixed:
            e['fixed_len'] = fixed
        by_key[key] = e
        entries.append(e)
    by_key[key]['sites'].append(['%06x' % site, '%06x' % addr])


# item names: 128-entry pointer table
for k in range(128):
    add('item', rd(0x4cd388 + 4 * k), 0x4cd388 + 4 * k, 'item_name')
# alternate item names table (same strings, separate slots)
for k in range(16):
    add('item', rd(0x4cd548 + 4 * k), 0x4cd548 + 4 * k, 'item_name')
# item descriptions
for k in range(79):
    add('msg', rd(0x4c9370 + 4 * k), 0x4c9370 + 4 * k, 'item_desc')
# system messages
for k in range(63):
    add('msg', rd(0x4cde58 + 4 * k), 0x4cde58 + 4 * k, 'system_msg')
# menus referenced from code
MENU = [0x4aa1e0, 0x4aa1f0, 0x4aa200, 0x4aa208, 0x4aa218, 0x4aa228, 0x4aa230, 0x4aa238, 0x4aa248,
        0x4cbba8, 0x4cbbb8, 0x4cbbc0, 0x4cbbc8, 0x4cbbd0, 0x4cbbd8,
        0x4b1130, 0x4b1148, 0x4b1028, 0x4b0ff8]
for a in MENU:
    refs = code_refs(a)
    if not refs:
        print('no code ref for', hex(a))
    for s in refs:
        add('menu', a, s, 'menu')
# save/load labels (pointer table)
for k in range(2):
    add('menu', rd(0x4b1008 + 4 * k), 0x4b1008 + 4 * k, 'menu')
# character names copied into save headers: exactly 6 bytes + terminator
for k in range(2):
    add('menu', rd(0x4b1020 + 4 * k), 0x4b1020 + 4 * k, 'save_name', fixed=6)
# save location names copied into save headers: exactly 16 bytes + terminator
for k in range(7):
    add('menu', rd(0x4b1110 + 4 * k), 0x4b1110 + 4 * k, 'save_place', fixed=16)

# 'Yes  No' choice labels: sprintf format drawn by the ASCII renderer
for s in code_refs(0x4cdf54):
    add('ascii', 0x4cdf54, s, 'yesno')

old = {}
if os.path.exists(OUT):
    old = {e['id']: e for e in json.load(open(OUT, encoding='utf-8'))}
for e in entries:
    if e['id'] in old:
        e['ko'] = old[e['id']].get('ko', '')
json.dump(entries, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(len(entries), 'strings,', sum(len(e['sites']) for e in entries), 'sites')
