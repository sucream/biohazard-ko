"""Build everything: fonts, string tables, room text, movie subtitles, the patch DLL, the launcher.

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
import build_movies  # noqa: E402


def main():
    game = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, '4249100_Biohazard')
    build_font.main(game)
    build_exe.main()
    build_rooms.main(game)
    build_images.main(game)
    build_movies.main(game)
    dll = os.path.join(ROOT, 'dll')
    subprocess.check_call(['zig', 'cc', '-target', 'x86-windows-gnu', '-shared', '-O2', '-s',
                           '-o', os.path.join(ROOT, 'build', 'version.dll'),
                           'proxy.c', 'kopatch.c', 'movie.c', 'version.def', '-luser32', '-lgdi32'], cwd=dll)
    print('built build/version.dll')
    build_launcher(game)


def build_launcher(game):
    """build/4249100_Launcher.exe: the Steam launcher with a 'korean' entry."""
    tool = os.path.join(ROOT, 'build', 'launcher_patch')
    subprocess.check_call(['dotnet', 'build', '-c', 'Release', '-v', 'q', '-nologo', '-o', tool,
                           os.path.join(ROOT, 'tools', 'launcher_patch')])
    orig = os.path.join(game, 'kopatch_backup', '4249100_Launcher.exe')
    if not os.path.exists(orig):
        orig = os.path.join(game, '4249100_Launcher.exe')
    subprocess.check_call(['dotnet', os.path.join(tool, 'launcher_patch.dll'), orig,
                           os.path.join(ROOT, 'build', '4249100_Launcher.exe')])


if __name__ == '__main__':
    main()
