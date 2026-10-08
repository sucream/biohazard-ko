"""Extract all room messages (JP + EN reference) into translations/rdt_messages.json."""
import glob, json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import rdt, jptable

GAME = sys.argv[1]  # .../4249100_Biohazard
OUT = sys.argv[2]
jp_root = os.path.join(GAME, 'japanese', 'JPN')
en_root = os.path.join(GAME, 'english', 'USA')


def find_ci(root, rel):
    p = root
    for part in rel.replace(chr(92), '/').split('/'):
        cand = [x for x in os.listdir(p) if x.upper() == part.upper()]
        if not cand:
            return None
        p = os.path.join(p, cand[0])
    return p


old = {}
if os.path.exists(OUT):
    for e in json.load(open(OUT, encoding='utf-8')):
        old[e['jp']] = e

entries = {}
order = []
for stage in sorted(x for x in os.listdir(jp_root) if x.upper().startswith('STAGE')):
    for fn in sorted(os.listdir(os.path.join(jp_root, stage)), key=str.upper):
        if not fn.upper().endswith('.RDT'):
            continue
        d = open(os.path.join(jp_root, stage, fn), 'rb').read()
        if not rdt.is_room(d):
            continue
        st5 = stage.upper() == 'STAGE5'
        enp = find_ci(en_root, stage + '/' + fn)
        enm = rdt.messages(open(enp, 'rb').read()) if enp else []
        for i, m in enumerate(rdt.messages(d)):
            jp = jptable.decode(m, stage5=st5)
            ref = '%s/%s#%d' % (stage.upper(), fn.upper(), i)
            if jp not in entries:
                en = rdt.decode_en(enm[i]) if i < len(enm) else ''
                entries[jp] = {'id': len(order), 'jp': jp, 'en': en, 'ko': old.get(jp, {}).get('ko', ''), 'refs': []}
                order.append(jp)
            entries[jp]['refs'].append(ref)
json.dump([entries[k] for k in order], open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print(len(order), 'unique messages')
