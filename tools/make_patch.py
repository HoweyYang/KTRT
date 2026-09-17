# -*- coding: utf-8 -*-
"""把当前前端打包成热补丁 zip，挂在 GitHub Release 上供「更新」页一键应用。

用法：
  python tools/make_patch.py --version 0.2.1 --tag v0.2.1
  生成 release/patch-0.2.1.zip（内含整套 frontend/static + patch.json 校验表）

发布流程：打 tag 发 Release 时，把 dist 的安装包和这个 patch-*.zip 一起传上去。
"""
import argparse
import hashlib
import json
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'frontend', 'static')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--version', required=True)
    ap.add_argument('--src', default=SRC)
    ap.add_argument('--out', default='')
    args = ap.parse_args()

    out = args.out or os.path.join(ROOT, 'release', 'patch-%s.zip' % args.version)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    files = {}
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for base, _dirs, names in os.walk(args.src):
            for name in sorted(names):
                full = os.path.join(base, name)
                rel = os.path.relpath(full, args.src).replace('\\', '/')
                with open(full, 'rb') as f:
                    data = f.read()
                files[rel] = hashlib.sha256(data).hexdigest()
                z.writestr(rel, data)
        manifest = {'version': args.version, 'files': files,
                    'generated_at': __import__('time').strftime('%Y-%m-%d %H:%M:%S')}
        z.writestr('patch.json', json.dumps(manifest, ensure_ascii=False, indent=2))
    size = os.path.getsize(out)
    print('patch saved: %s（%d 个文件，%.0f KB）' % (out, len(files), size / 1024.0))
    return 0


if __name__ == '__main__':
    sys.exit(main())
