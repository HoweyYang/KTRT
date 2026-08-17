# -*- coding: utf-8 -*-
"""KTRT 启动器：无终端启动，预备弹窗显示加载进度，后台日志写入文件。"""
import os
import shutil
import sys
import threading
import time
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# 打包版（PyInstaller --noconsole）：数据放 %APPDATA%\KTRT，资源从解压目录读取
FROZEN = bool(getattr(sys, 'frozen', False))
if FROZEN:
    os.environ.setdefault(
        'KTRT_DATA_DIR',
        os.path.join(os.environ.get('APPDATA') or ROOT, 'KTRT'),
    )
    RESOURCE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
else:
    RESOURCE_DIR = ROOT

from backend import db  # noqa: E402

HOST = '127.0.0.1'
PORT = 8000
URL = 'http://127.0.0.1:%d' % PORT


def _setup_logging():
    """把 stdout/stderr 重定向到日志文件（无终端模式不会丢失启动信息）。"""
    os.makedirs(db.DATA_DIR, exist_ok=True)
    log_path = os.path.join(db.DATA_DIR, 'launcher.log')
    try:
        f = open(log_path, 'a', encoding='utf-8')
        sys.stdout = f
        sys.stderr = f
    except Exception:
        pass
    return log_path


def ensure_bundled_resources():
    """首次运行：把安装包内置的词库/参考素材复制到用户数据目录。"""
    os.makedirs(db.DATA_DIR, exist_ok=True)
    for name in ('GRE必背_扩展词库.xlsx', 'reference_phrasal_verbs.json'):
        src = os.path.join(RESOURCE_DIR, 'data', name)
        dst = os.path.join(db.DATA_DIR, name)
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copy2(src, dst)
            print('[KTRT] 已初始化数据：' + name)


def start_server():
    import uvicorn
    from backend.app import app
    config = uvicorn.Config(app, host=HOST, port=PORT, log_level='warning')
    server = uvicorn.Server(config)
    server.run()


def main():
    log_path = _setup_logging()
    print('[KTRT] 正在启动… 日志文件：' + log_path)
    try:
        ensure_bundled_resources()
        from backend.seed import seed_gre, seed_dictionary, seed_references
        seed_gre()
        seed_dictionary()
        seed_references()
    except Exception as e:
        print('[KTRT] 初始化失败：%s' % e)

    threading.Thread(target=start_server, daemon=True).start()

    from splash import run_splash
    try:
        ready = run_splash(HOST, PORT, RESOURCE_DIR)
    except Exception as e:
        ready = False
        print('[KTRT] 弹窗异常：%s' % e)
    print('[KTRT] 预备弹窗结束，服务就绪=%s' % ready)

    if os.environ.get('KTRT_NO_BROWSER') != '1':
        try:
            webbrowser.open(URL)
        except Exception as e:
            print('[KTRT] 打开浏览器失败：%s' % e)

    # 保持进程存活，直到用户关闭
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
