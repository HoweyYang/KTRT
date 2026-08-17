import os
import socket
import sys
import threading
import time
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

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


def main():
    print('[KTRT] 正在准备词库…')
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
