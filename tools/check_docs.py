"""Validate translations/documents.json: every half page must fit 256x128."""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import build_images
path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), '..', 'translations', 'documents.json')
bad = todo = 0
for e in json.load(open(path, encoding='utf-8')):
    if e.get('ko') is None:
        todo += 1
        continue
    try:
        build_images.layout(e['ko'])
    except ValueError as x:
        bad += 1
        print('%s half %d: %s' % (e['file'], e['half'], x))
print('%d problems, %d untranslated' % (bad, todo))
