# -*- coding: utf-8 -*-
"""KTRT 启动器 v3：无终端、独立弹窗子进程、日志写文件。

流程：重定向日志 → 后台线程建库 + 起服务 → 独立子进程显示预备弹窗
（Tk 销毁崩溃只影响弹窗自己，不连累主服务）→ 弹窗关闭 → 打开浏览器 → 进程驻留。
"""
import os
import shutil
import socket
import subprocess
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
        f = open(log_path, 'a', encoding='utf-8', buffering=1)
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


def _pythonw():
    exe = sys.executable
    if exe.lower().endswith('python.exe'):
        pw = exe[:-len('python.exe')] + 'pythonw.exe'
        if os.path.exists(pw):
            return pw
    return exe


def _spawn_splash():
    """独立子进程显示弹窗，Tk 销毁崩溃不会连累主服务。"""
    if FROZEN:
        cmd = [sys.executable, '--splash-only', '--host', HOST,
               '--port', str(PORT), '--assets', RESOURCE_DIR]
    else:
        cmd = [_pythonw(), os.path.join(RESOURCE_DIR, 'splash.py'),
               '--host', HOST, '--port', str(PORT), '--assets', RESOURCE_DIR]
    try:
        return subprocess.Popen(
            cmd, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except Exception as e:
        print('[KTRT] 弹窗进程启动失败：%s' % e)
        return None


def _wait_splash(proc, timeout=25):
    if proc is None:
        return
    try:
        proc.wait(timeout=timeout)
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass


def ensure_bundled_resources():
    """首次运行：把安装包内置的词库/参考素材复制到用户数据目录。"""
    os.makedirs(db.DATA_DIR, exist_ok=True)
    for name in ('reference_phrasal_verbs.json',):
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
        from backend.seed import seed_default_book, seed_dictionary, seed_references
        seed_default_book()
        seed_dictionary()
        seed_references()
    except Exception as e:
        print('[KTRT] 初始化失败：%s' % e)
    start_server()


def main():
    log_path = _setup_logging()
    print('[KTRT] 正在启动… 日志文件：' + log_path)

    # 单实例保护：已有 KTRT 在运行则仍显示弹窗、打开浏览器后退出
    if _port_open(HOST, PORT):
        print('[KTRT] 已有实例在运行，仍显示启动弹窗…')
        _wait_splash(_spawn_splash())
        if os.environ.get('KTRT_NO_BROWSER') != '1':
            try:
                webbrowser.open(URL)
            except Exception as e:
                print('[KTRT] 打开浏览器失败：%s' % e)
        return

    # 后台线程建库 + 起服务；独立子进程显示弹窗
    threading.Thread(target=prepare_and_serve, daemon=True).start()
    splash_proc = _spawn_splash()

    # 轮询服务就绪（最长 25 秒）
    t0 = time.time()
    ready = False
    while time.time() - t0 < 25:
        if _port_open(HOST, PORT):
            ready = True
            break
        if splash_proc is not None and splash_proc.poll() is not None:
            break
        time.sleep(0.3)
    _wait_splash(splash_proc)
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


def _run_splash_only():
    """--splash-only：打包版子进程入口，仅显示弹窗后退出。"""
    import argparse
    from splash import run_splash
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='127.0.0.1')
    ap.add_argument('--port', type=int, default=8000)
    ap.add_argument('--assets', default=RESOURCE_DIR)
    args, _ = ap.parse_known_args()
    ok = run_splash(args.host, args.port, args.assets)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    if '--splash-only' in sys.argv:
        _run_splash_only()
    main()
