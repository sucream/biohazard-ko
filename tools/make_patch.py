"""Build the patcher payload: XOR diffs of every changed game file.

Only differences against the user's own original files are shipped, so the
patch contains no game data. Writes patcher/payload/{manifest.json,*.bin}.

The game folder must hold the original files; if it is patched, the backups
in japanese/kopatch_backup (made by the installer) are used instead.

usage: make_patch.py [game_dir]
"""
import hashlib
import json
import os
import shutil
import sys
import zlib

ROOT = os.path.join(os.path.dirname(__file__), '..')


def md5(b):
    return hashlib.md5(b).hexdigest()


def original(game_dir, rel):
    """Original bytes of japanese/<rel>, preferring the installer's backup."""
    bak = os.path.join(game_dir, 'japanese', 'kopatch_backup', 'japanese', rel)
    return open(bak if os.path.exists(bak) else os.path.join(game_dir, 'japanese', rel), 'rb').read()


def main(game_dir):
    build = os.path.join(ROOT, 'build')
    out = os.path.join(ROOT, 'patcher', 'payload')
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(out)
    files = []

    # modified game files: build/JPN/... mirrors japanese/JPN/...
    for dirpath, _, names in os.walk(os.path.join(build, 'JPN')):
        for n in sorted(names):
            src_new = os.path.join(dirpath, n)
            rel = os.path.relpath(src_new, build).replace(os.sep, '/')
            new = open(src_new, 'rb').read()
            orig = original(game_dir, rel)
            x = bytes(a ^ b for a, b in zip(new, orig.ljust(len(new), b'\0')))
            blob = zlib.compress(x, 9)
            name = '%03d.bin' % len(files)
            open(os.path.join(out, name), 'wb').write(blob)
            files.append({'path': 'japanese/' + rel, 'mode': 'xor', 'data': name,
                          'orig_md5': md5(orig), 'orig_size': len(orig),
                          'new_md5': md5(new), 'new_size': len(new)})
    # new files
    for rel, src in (('japanese/version.dll', os.path.join(build, 'version.dll')),):
        new = open(src, 'rb').read()
        name = '%03d.bin' % len(files)
        open(os.path.join(out, name), 'wb').write(zlib.compress(new, 9))
        files.append({'path': rel, 'mode': 'new', 'data': name, 'new_md5': md5(new), 'new_size': len(new)})

    exe = open(os.path.join(game_dir, 'japanese', 'Biohazard.exe'), 'rb').read()
    version = open(os.path.join(ROOT, 'VERSION')).read().strip()
    manifest = {'name': 'Biohazard (1996) Korean patch', 'version': version, 'exe_md5': md5(exe), 'files': files}
    json.dump(manifest, open(os.path.join(out, 'manifest.json'), 'w'), indent=1)
    total = sum(os.path.getsize(os.path.join(out, f['data'])) for f in files)
    print('patch payload v%s: %d files, %d KB' % (version, len(files), total // 1024))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, '4249100_Biohazard'))
