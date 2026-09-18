# -*- coding: utf-8 -*-
"""启动弹窗的样式契约：这一版把弹窗改成墨蓝底 + 放大字号，这里锁住关键值，
免得以后有人顺手改回去（也可以直接 pytest 跑）。

用法：venv\\Scripts\\python.exe tests\\test_splash_style.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import splash  # noqa: E402


def test_splash_uses_noble_dark_palette_and_roomier_layout():
    assert splash.SPLASH_WIDTH == 720
    assert splash.SPLASH_HEIGHT == 500
    assert splash.SPLASH_PALETTE['background'] == '#101b25'
    assert splash.DESCRIPTOR_FONT == ('Segoe UI', 10, 'italic')
    # 签名走手写花体，第一位是 Edwardian Script（Apple 那种优雅手写）
    assert splash.SIGNATURE_FONTS[0] == 'Edwardian Script ITC'
    assert splash.SIGNATURE_TEXT.startswith('Designed by')


def main():
    """不依赖 pytest：直接跑断言，方便和其它测试一样一键执行。"""
    tests = [v for k, v in sorted(globals().items()) if k.startswith('test_') and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print('PASS  ' + t.__name__)
        except AssertionError as e:
            failed += 1
            print('FAIL  ' + t.__name__ + ('  ' + str(e) if str(e) else ''))
    print('\n%d 项通过，%d 项失败' % (len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
