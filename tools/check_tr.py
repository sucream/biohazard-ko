"""Validate Korean translations in a translation JSON file.

usage: check_tr.py <file.json> [--all]

Checks every entry that has a 'ko' value:
  * control tags (<END:n>, <PAGE:n>, <C4:n>, <COL:n>, <ITEM:n>, <YESNO:n>)
    appear in exactly the same order as in 'jp'
  * every page has at most 2 lines, every line fits the message window
    (20 cells; Hangul/ASCII = 1 cell, space = 0.5 cell)
  * the line holding <YESNO:n> leaves room for the choice labels (9 cells)
  * only characters the font can show are used
  * item names <= 12 cells, menu strings fit their fixed byte budgets
"""
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(__file__))
import kocodec

TAG = re.compile(r'<(?:END|PAGE|C4|COL|ITEM|YESNO):\d+>|<RET>')
OK_CHARS = set(kocodec.FIXED) | set('…~%&+=*#@<>^_|°♪→←↑↓※')


def tags(s):
    """Control tags up to and including the first END (bytes after END are
    never read by the game)."""
    out = []
    for x in TAG.findall(s):
        out.append(x)
        if x.startswith('<END:'):
            break
    return out


def char_ok(c):
    if c in OK_CHARS or c == '\n':
        return True
    if '가' <= c <= '힣':
        return True
    return False


def check_entry(e):
    probs = []
    ko = unicodedata.normalize('NFC', e['ko'])
    kind = e.get('kind', 'msg')
    if kind in ('msg', None) or 'refs' in e:
        if tags(ko) != tags(e['jp']):
            probs.append('tags differ: jp=%s ko=%s' % (tags(e['jp']), tags(ko)))
        laid = kocodec.layout(ko, e['jp'])
        probs += kocodec.check(laid)
        # the Yes/No labels are drawn on the 2nd line of the window from x=174
        # (10 cells), so a question on the 2nd line must stay short
        if 'YESNO' in laid:
            page = re.split(r'<PAGE:\d+>', laid[:laid.index('<YESNO')])[-1]
            lines = page.split('\n')
            if len(lines) >= 2 and kocodec.width(lines[1]) > 9.5:
                probs.append('2nd line too wide for the Yes/No labels: %s' % TAG.sub('', lines[1]))
    elif kind == 'item':
        if kocodec.width(ko) > 12:
            probs.append('item name wider than 12 cells')
    text = TAG.sub('', ko).replace('S.T.A.R.S.', '')
    bad = sorted(set(c for c in text if not char_ok(c)))
    if bad:
        probs.append('unsupported characters: %s' % ' '.join('%r' % c for c in bad))
    if '  ' in text and kind != 'ascii':
        probs.append('double space')
    return probs


def main():
    path = sys.argv[1]
    entries = json.load(open(path, encoding='utf-8'))
    n = bad = empty = 0
    for e in entries:
        if not e.get('ko'):
            empty += 1
            continue
        n += 1
        p = check_entry(e)
        if p:
            bad += 1
            print('[%s] %s' % (e['id'], e['jp'].replace('\n', '/')[:60]))
            for x in p:
                print('    - ' + x)
    print('%d checked, %d with problems, %d untranslated' % (n, bad, empty))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
