# -*- coding: utf-8 -*-
"""KTRT 启动器 v2：无终端、先弹窗后建库、日志写文件。

流程：重定向日志 → 立即显示预备弹窗（后台线程先建库再启动服务）→
动画播完且服务就绪后弹窗关闭 → 打开浏览器 → 进程驻留。
"""
import os
import shutil
import socket
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
    """把 stdout/stderr 重定向到日志文件（无终端模式不丢失启动信息）。"""
    os.makedirs(db.DATA_DIR, exist_ok=True)
    log_path = os.path.join(db.DATA_DIR, 'launcher.log')
    try:
        f = open(log_path, 'a', encoding='utf-8', buffering=1)  # 行缓冲，日志实时落盘
        sys.stdout = f
        sys.stderr = f
    except Exception:
        pass
    return log_path


def _port_open(host, port, timeout=0.3):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


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


def prepare_and_serve():
    """后台线程：先建库（首次可能较慢），再启动服务。"""
    try:
        ensure_bundled_resources()
        from backend.seed import seed_gre, seed_dictionary, seed_references
        seed_gre()
        seed_dictionary()
        seed_references()
    except Exception as e:
        print('[KTRT] 初始化失败：%s' % e)
    start_server()


def main():
    log_path = _setup_logging()
    print('[KTRT] 正在启动… 日志文件：' + log_path)

    # 单实例保护：已有 KTRT 在运行则直接打开浏览器并退出，避免多实例互相锁库
    if _port_open(HOST, PORT):
        print('[KTRT] 已有实例在运行，直接打开浏览器…')
        if os.environ.get('KTRT_NO_BROWSER') != '1':
            try:
                webbrowser.open(URL)
            except Exception as e:
                print('[KTRT] 打开浏览器失败：%s' % e)
        return

    # 立即弹窗（动画约 3 秒，期间后台建库 + 起服务）
    threading.Thread(target=prepare_and_serve, daemon=True).start()

    from splash import run_splash
    t0 = time.time()
    try:
        ready = run_splash(HOST, PORT, RESOURCE_DIR)
    except Exception as e:
        ready = False
        print('[KTRT] 弹窗异常：%s' % e)
    print('[KTRT] 预备弹窗结束，耗时 %.1fs，服务就绪=%s' % (time.time() - t0, ready))

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

