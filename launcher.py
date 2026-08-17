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

# 打包版（PyInstaller）：数据放 %APPDATA%\KTRT，资源从解压目录读取
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
from backend.seed import seed_gre, seed_dictionary, seed_references  # noqa: E402

HOST = '127.0.0.1'
PORT = 8000


def wait_ready(timeout=40):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((HOST, PORT), 0.25):
                return True
        except OSError:
            time.sleep(0.25)
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


def main():
    print('[KTRT] 正在准备词库…')
    ensure_bundled_resources()
    seed_gre()
    seed_dictionary()
    seed_references()

    import uvicorn
    from backend.app import app

    config = uvicorn.Config(app, host=HOST, port=PORT, log_level='info')
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    if wait_ready():
        print('[KTRT] 已启动：http://127.0.0.1:8000')
        if os.environ.get('KTRT_NO_BROWSER') != '1':
            webbrowser.open('http://127.0.0.1:8000')
    else:
        print('[KTRT] 启动超时，请查看上方错误信息。')

    try:
        thread.join()
    except KeyboardInterrupt:
        server.should_exit = True


if __name__ == '__main__':
    main()
