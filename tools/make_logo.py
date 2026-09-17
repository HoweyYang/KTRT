# -*- coding: utf-8 -*-
"""把源 logo 做成圆角方形图标（Windows 应用图标那种），产出三份：

  logo.ico                     程序 / 安装包 / 快捷方式用的图标（多尺寸）
  frontend/static/logo.png     程序内图标与网页图标
  assets/logo_rounded.png      圆角版母版（带透明通道，方便以后再改）

用法（需要带 Pillow 的解释器，例如 Codex 运行时）：
  python tools/make_logo.py                 # 圆角半径 22%
  python tools/make_logo.py --radius 0.18   # 角更方一点
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'assets', 'logo_master.png')
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
SS = 4          # 超采样倍数：先放大画角再缩回去，边缘才不会毛刺


def load_square(path):
    im = Image.open(path).convert('RGBA')
    side = min(im.size)
    left = (im.width - side) // 2
    top = (im.height - side) // 2
    return im.crop((left, top, left + side, top + side))


def rounded(im, size, radius_ratio):
    """从正方形源图生成 size×size 的圆角图标。"""
    big = int(size) * SS
    base = im.resize((big, big), Image.LANCZOS)
    mask = Image.new('L', (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, big - 1, big - 1], radius=max(1, int(round(big * radius_ratio))), fill=255)
    out = Image.new('RGBA', (big, big), (0, 0, 0, 0))
    out.paste(base, (0, 0), mask)
    return out.resize((size, size), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', default=SRC)
    ap.add_argument('--radius', type=float, default=0.22, help='圆角半径占边长的比例，默认 0.22')
    args = ap.parse_args()

    src = load_square(args.src)
    ico_path = os.path.join(ROOT, 'logo.ico')
    png_path = os.path.join(ROOT, 'frontend', 'static', 'logo.png')
    master_path = os.path.join(ROOT, 'assets', 'logo_rounded.png')

    frames = {s: rounded(src, s[0], args.radius) for s in ICO_SIZES}
    frames[(256, 256)].save(ico_path, format='ICO', sizes=ICO_SIZES)
    frames[(256, 256)].save(png_path)
    rounded(src, 1254, args.radius).save(master_path)

    # 自检：四角必须透明、中心必须不透明
    for path in (ico_path, png_path, master_path):
        im = Image.open(path)
        w, h = im.size
        corners = [im.getpixel(p)[3] for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
        center = im.getpixel((w // 2, h // 2))[3]
        print('%-38s %sx%s  角alpha=%s  中心alpha=%s' % (
            os.path.relpath(path, ROOT), w, h, corners, center))
    print('ico 内含尺寸：', sorted(Image.open(ico_path).info.get('sizes', [])))
    return 0


if __name__ == '__main__':
    sys.exit(main())
