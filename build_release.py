"""构建 KTRT Windows 发布版（PyInstaller onedir）。

用法：
  venv\Scripts\python.exe build_release.py            # 完整版（含 GRE 词库）
  venv\Scripts\python.exe build_release.py --lite     # 纯净版（不含词库，自行导入）
产物：dist\KTRT-full\KTRT.exe 或 dist\KTRT-lite\KTRT.exe
"""
import os
import sys

import PyInstaller.__main__

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)

LITE = '--lite' in sys.argv
NAME = 'KTRT-lite' if LITE else 'KTRT-full'


def p(path):
    return os.path.join(ROOT, path)


add_data = [
    '--add-data=' + p('frontend') + os.pathsep + 'frontend',
    '--add-data=' + p(os.path.join('data', 'reference_phrasal_verbs.json')) + os.pathsep + 'data',
    '--add-data=' + p('docs') + os.pathsep + 'docs',
]
if not LITE:
    add_data.append(
        '--add-data=' + p(os.path.join('data', 'GRE必背_扩展词库.xlsx')) + os.pathsep + 'data'
    )

args = [
    p('launcher.py'),
    '--name=' + NAME,
    '--onedir',
    '--noconfirm',
    '--clean',
    '--console',
    '--icon=' + p('logo.ico'),
] + add_data + [
    '--hidden-import=multipart',
    '--hidden-import=uvicorn.logging',
    '--hidden-import=uvicorn.loops.auto',
    '--hidden-import=uvicorn.protocols.http.auto',
    '--hidden-import=uvicorn.protocols.http.h11_impl',
    '--hidden-import=uvicorn.protocols.websockets.auto',
    '--hidden-import=uvicorn.protocols.websockets.websockets_impl',
    '--hidden-import=uvicorn.lifespan.on',
    '--hidden-import=uvicorn.lifespan.off',
]
PyInstaller.__main__.run(args)
print('BUILD DONE:', os.path.join('dist', NAME, NAME + '.exe'))
