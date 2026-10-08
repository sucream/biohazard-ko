"""Build the patcher payload: XOR diffs of every changed game file.

Only differences against the user's own original files are shipped, so the
patch contains no game data. Writes patcher/payload/{manifest.json,*.bin}.

The Korean version lives in its own folder, korean/, next to japanese/:
the installer mirrors japanese/ into korean/ and replaces the files listed
here. japanese/ itself is left untouched. The Steam launcher is patched in
place to offer 'korean' as a fifth language.

Manifest entries:
  {"dest": "korean/JPN/...", "mode": "xor", "src": "japanese/JPN/...", ...}
      dest = src XOR data (src must be the original file)
  {"dest": "korean/version.dll", "mode": "new", ...}
  {"dest": "4249100_Launcher.exe", "mode": "xor", "src": "4249100_Launcher.exe", "backup": true}
      patched in place; the original is kept in kopatch_backup/

The game folder must hold the original files; installer backups
(kopatch_backup/, or japanese/kopatch_backup/ from 1.0/1.1) are used when
present.

usage: make_patch.py [game_dir]
"""
import hashlib
import json
import os
import shutil
import sys
import zlib

ROOT = os.path.join(os.path.dirname(__file__), '..')
TARGET = 'korean'


def md5(b):
    return hashlib.md5(b).hexdigest()


def original(game_dir, rel):
    """Original bytes of <rel> (relative to the game folder), preferring backups."""
    for bak in (os.path.join(game_dir, 'kopatch_backup', rel),
                os.path.join(game_dir, 'japanese', 'kopatch_backup', rel)):
        if os.path.exists(bak):
            return open(bak, 'rb').read()
    return open(os.path.join(game_dir, rel), 'rb').read()


def main(game_dir):
    build = os.path.join(ROOT, 'build')
    out = os.path.join(ROOT, 'patcher', 'payload')
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(out)
    files = []

    def add_xor(dest, src, new, **extra):
        orig = original(game_dir, src)
        x = bytes(a ^ b for a, b in zip(new, orig.ljust(len(new), b'\0')))
        name = '%03d.bin' % len(files)
        open(os.path.join(out, name), 'wb').write(zlib.compress(x, 9))
        files.append(dict({'dest': dest, 'mode': 'xor', 'src': src, 'data': name,
                           'orig_md5': md5(orig), 'orig_size': len(orig),
                           'new_md5': md5(new), 'new_size': len(new)}, **extra))

    # modified game files: build/JPN/... mirrors japanese/JPN/...
    for dirpath, _, names in os.walk(os.path.join(build, 'JPN')):
        for n in sorted(names):
            rel = os.path.relpath(os.path.join(dirpath, n), build).replace(os.sep, '/')
            add_xor(TARGET + '/' + rel, 'japanese/' + rel, open(os.path.join(dirpath, n), 'rb').read())
    # new files
    for rel, src in ((TARGET + '/version.dll', os.path.join(build, 'version.dll')),):
        new = open(src, 'rb').read()
        name = '%03d.bin' % len(files)
        open(os.path.join(out, name), 'wb').write(zlib.compress(new, 9))
        files.append({'dest': rel, 'mode': 'new', 'data': name, 'new_md5': md5(new), 'new_size': len(new)})
    # launcher, patched in place
    add_xor('4249100_Launcher.exe', '4249100_Launcher.exe',
            open(os.path.join(build, '4249100_Launcher.exe'), 'rb').read(), backup=True)

    exe = open(os.path.join(game_dir, 'japanese', 'Biohazard.exe'), 'rb').read()
    version = open(os.path.join(ROOT, 'VERSION')).read().strip()
    manifest = {'name': 'Biohazard (1996) Korean patch', 'version': version, 'format': 2,
                'source': 'japanese', 'target': TARGET, 'exe_md5': md5(exe), 'files': files}
    json.dump(manifest, open(os.path.join(out, 'manifest.json'), 'w'), indent=1)
    total = sum(os.path.getsize(os.path.join(out, f['data'])) for f in files)
    print('patch payload v%s: %d files, %d KB' % (version, len(files), total // 1024))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, '4249100_Biohazard'))
