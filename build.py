"""Build everything: fonts, string tables, room text, the patch DLL.

usage: python build.py [game_dir]
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import build_exe  # noqa: E402
import build_font  # noqa: E402
import build_rooms  # noqa: E402
import build_images  # noqa: E402


def main():
    game = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, '4249100_Biohazard')
    build_font.main(game)
    build_exe.main()
    build_rooms.main(game)
    build_images.main(game)
    dll = os.path.join(ROOT, 'dll')
    subprocess.check_call(['zig', 'cc', '-target', 'x86-windows-gnu', '-shared', '-O2', '-s',
                           '-o', os.path.join(ROOT, 'build', 'version.dll'),
                           'proxy.c', 'kopatch.c', 'version.def', '-luser32'], cwd=dll)
    print('built build/version.dll')


if __name__ == '__main__':
    main()
