"""Package the patcher for release: dist/BH1_KOR_Patch_v<VERSION>.zip

Contents: bh1_kor_patch.exe, 읽어주세요.txt, font licences.
Run after make_patch.py and the Go build (build/bh1_kor_patch.exe).
"""
import os
import zipfile

ROOT = os.path.join(os.path.dirname(__file__), '..')


def main():
    version = open(os.path.join(ROOT, 'VERSION')).read().strip()
    readme = open(os.path.join(ROOT, 'packaging', '읽어주세요.txt'), encoding='utf-8').read()
    readme = readme.replace('{VERSION}', version).replace('\r\n', '\n').replace('\n', '\r\n')
    os.makedirs(os.path.join(ROOT, 'dist'), exist_ok=True)
    out = os.path.join(ROOT, 'dist', 'BH1_KOR_Patch_v%s.zip' % version)
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        z.write(os.path.join(ROOT, 'build', 'bh1_kor_patch.exe'), 'bh1_kor_patch.exe')
        z.writestr('읽어주세요.txt', readme.encode('utf-8-sig'))
        for lic in ('Galmuri-OFL.txt', 'Nanum-OFL.txt'):
            z.write(os.path.join(ROOT, 'fonts', lic), lic)
    print('%s (%d KB)' % (os.path.relpath(out, ROOT), os.path.getsize(out) // 1024))


if __name__ == '__main__':
    main()
