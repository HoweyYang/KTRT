# -*- coding: utf-8 -*-
"""KTRT 冒烟测试：在隔离的数据目录与端口上起一份实例，验证关键接口与本地安全边界。

用法：
  venv\\Scripts\\python.exe tests\\smoke_test.py

不碰你正在用的 data 目录和 8000 端口；退出码 0 = 全过，1 = 有失败项。
"""
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASSED = []
FAILED = []


def check(name, cond, extra=''):
    (PASSED if cond else FAILED).append(name)
    line = '%s  %s%s' % ('PASS' if cond else 'FAIL', name, ('  -> ' + str(extra)) if extra else '')
    try:
        print(line)
    except UnicodeEncodeError:      # 控制台是 GBK 时，先把编不出的字符换掉
        print(line.encode('ascii', 'replace').decode('ascii'))


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def http(method, url, body=None, headers=None, timeout=15):
    """返回 (状态码, 响应头, 正文)。HTTP 错误也照常返回，不当成异常。"""
    data = None if body is None else json.dumps(body).encode('utf-8')
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    if data is not None:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode('utf-8', 'replace')


def db_setting(data_dir, key):
    path = os.path.join(data_dir, 'ktrt.db')
    for _ in range(10):
        try:
            with sqlite3.connect(path) as conn:
                row = conn.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
            return row[0] if row else None
        except sqlite3.Error:
            time.sleep(0.2)
    return None


class _Quiet(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass


def serve(port, handler):
    srv = HTTPServer(('127.0.0.1', port), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.2)
    return srv


def stop(srv):
    srv.shutdown()
    srv.server_close()


def test_launcher_port_probe():
    """启动器必须能分清"端口上是不是 KTRT"，而不是见到端口通就当成自己。"""
    import launcher

    class Foreign(_Quiet):
        def do_GET(self):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'not ktrt')

    class FakeKtrt(_Quiet):
        def do_GET(self):
            body = json.dumps({'app': 'KTRT', 'version': 'test'}).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    port = free_port()
    srv = serve(port, Foreign)
    got, running = launcher._resolve_port('127.0.0.1', port)
    check('端口被别的程序占用时顺延，不误开别人的页面',
          got == port + 1 and running is False, 'got=%s running=%s' % (got, running))
    stop(srv)

    port2 = free_port()
    srv2 = serve(port2, FakeKtrt)
    got2, running2 = launcher._resolve_port('127.0.0.1', port2)
    check('端口上是 KTRT 时识别为已有实例',
          got2 == port2 and running2 is True, 'got=%s running=%s' % (got2, running2))
    stop(srv2)

    port3 = free_port()
    got3, running3 = launcher._resolve_port('127.0.0.1', port3)
    check('端口空闲时直接使用该端口',
          got3 == port3 and running3 is False, 'got=%s running=%s' % (got3, running3))

    # 20 个候选端口全被占：不能再返回一个已被占用的端口
    occupied, servers = [], []
    base = 21000
    while len(occupied) < 20 and base < 26000:
        try:
            servers.append(serve(base, Foreign))
            occupied.append(base)
        except OSError:
            pass
        base += 1
    if len(occupied) == 20:
        got4, running4 = launcher._resolve_port('127.0.0.1', occupied[0])
        check('候选端口全被占用时不会回到已占用端口',
              got4 not in occupied and running4 is False, 'got=%s' % got4)
    else:
        check('候选端口全被占用时不会回到已占用端口', False, '测试用端口没占满')
    for s in servers:
        stop(s)


def test_data_layer():
    """数据层回归（重复导入保留状态、补丁原子性）用子进程跑，保证模块状态干净。"""
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'tests', 'db_test.py')],
                       cwd=ROOT, capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    lines = [l for l in (r.stdout or '').splitlines() if l.strip()]
    check('数据层回归测试 tests/db_test.py 全过', r.returncode == 0,
          (lines[-1] if lines else 'no output'))
    if r.returncode != 0:
        print((r.stdout or '').encode('ascii', 'replace').decode('ascii'))


def test_launcher_end_to_end():
    """真跑一次 launcher.py：验证端口顺延、已有实例识别在真实启动路径上成立。"""
    import shutil as _shutil

    tmp = tempfile.mkdtemp(prefix='ktrt_launcher_')
    proc = proc2 = srv = None

    class Foreign(_Quiet):
        def do_GET(self):
            self.send_response(404)
            self.end_headers()

    try:
        port = free_port()
        srv = serve(port, Foreign)
        env = dict(os.environ, KTRT_DATA_DIR=tmp, KTRT_PORT=str(port),
                   KTRT_NO_BROWSER='1', KTRT_NO_SPLASH='1')

        proc = subprocess.Popen([sys.executable, os.path.join(ROOT, 'launcher.py')],
                                cwd=ROOT, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        moved = 'http://127.0.0.1:%d/api/ping' % (port + 1)
        started = False
        for _ in range(60):
            if proc.poll() is not None:
                break
            try:
                st, _, body = http('GET', moved, timeout=2)
                if st == 200 and json.loads(body).get('app') == 'KTRT':
                    started = True
                    break
            except Exception:
                pass
            time.sleep(0.5)
        check('launcher：端口被占用时顺延到下一个端口并启动成功', started, moved)

        proc2 = subprocess.Popen([sys.executable, os.path.join(ROOT, 'launcher.py')],
                                 cwd=ROOT, env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            proc2.wait(timeout=45)
            exited_early = proc2.returncode == 0
        except subprocess.TimeoutExpired:
            exited_early = False
        check('launcher：第二次启动识别到已有实例后自行退出', exited_early)

        log_path = os.path.join(tmp, 'launcher.log')
        log = ''
        if os.path.exists(log_path):
            with open(log_path, encoding='utf-8', errors='replace') as f:
                log = f.read()
        check('launcher 日志记录了端口顺延', '被其他程序占用' in log, log[-200:])
        check('launcher 日志记录了已有实例', '已有实例在运行' in log, log[-200:])
    finally:
        for p in (proc, proc2):
            if p is not None and p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=10)
                except Exception:
                    p.kill()
        if srv is not None:
            srv.shutdown()
        _shutil.rmtree(tmp, ignore_errors=True)


def main():
    data_dir = tempfile.mkdtemp(prefix='ktrt_smoke_')
    port = free_port()
    base = 'http://127.0.0.1:%d' % port
    env = dict(os.environ, KTRT_DATA_DIR=data_dir, KTRT_PORT=str(port))
    proc = subprocess.Popen(
        [sys.executable, '-m', 'uvicorn', 'backend.app:app',
         '--host', '127.0.0.1', '--port', str(port), '--log-level', 'warning'],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        # 等服务起来
        up = False
        for _ in range(60):
            if proc.poll() is not None:
                break
            try:
                st, _, _ = http('GET', base + '/api/ping', timeout=2)
                if st == 200:
                    up = True
                    break
            except Exception:
                pass
            time.sleep(0.5)
        if not up:
            out = proc.stdout.read().decode('utf-8', 'replace') if proc.poll() is not None else ''
            check('服务能启动', False, out[-500:])
            return

        st, hdrs, body = http('GET', base + '/api/ping')
        check('探针 /api/ping 返回自己的身份',
              st == 200 and json.loads(body).get('app') == 'KTRT', body[:120])

        st, _, body = http('GET', base + '/api/bootstrap')
        boot = json.loads(body) if st == 200 else {}
        check('/api/bootstrap 正常', st == 200 and 'books' in boot and 'settings' in boot, st)
        check('bootstrap 不再回传 API Key 明文',
              boot.get('settings', {}).get('api_key') == '', boot.get('settings', {}).get('api_key'))

        st, _, body = http('GET', base + '/')
        check('首页可访问', st == 200 and 'KTRT' in body, st)

        st, hdrs, _ = http('GET', base + '/static/docs/guide_usage.pdf')
        check('静态文件（PDF）仍可下载，中间件没挡住文件响应', st == 200, st)

        st, hdrs, _ = http('GET', base + '/api/settings')
        check('响应头不再放行跨域读取',
              'access-control-allow-origin' not in {k.lower() for k in hdrs}, list(hdrs))

        evil = {'Origin': 'http://evil.example'}
        st, _, _ = http('GET', base + '/api/settings', headers=evil)
        check('跨站 GET /api/settings 被拒绝', st == 403, st)

        st, _, _ = http('POST', base + '/api/settings', body={'api_key': 'sk-hacked'},
                        headers=evil)
        check('跨站 POST /api/settings 被拒绝', st == 403, st)
        check('跨站写入没有落库', db_setting(data_dir, 'api_key') is None, db_setting(data_dir, 'api_key'))

        same = {'Origin': 'http://127.0.0.1:%d' % port}
        st, _, body = http('POST', base + '/api/settings',
                           body={'api_key': 'sk-smoke-123', 'base_url': 'https://api.deepseek.com',
                                 'model': 'deepseek-chat', 'vendor': 'ds'}, headers=same)
        check('同源 POST /api/settings 正常', st == 200, st)
        check('Key 能正常保存到本地库', db_setting(data_dir, 'api_key') == 'sk-smoke-123',
              db_setting(data_dir, 'api_key'))
        check('保存后接口仍不回传明文',
              json.loads(body).get('api_key') == '' and json.loads(body).get('api_key_set') is True,
              body[:160])

        http('POST', base + '/api/settings',
             body={'api_key': '', 'base_url': 'https://api.deepseek.com',
                   'model': 'deepseek-chat', 'vendor': 'ds'})
        check('Key 留空 = 不修改（不会把已存的 Key 抹掉）',
              db_setting(data_dir, 'api_key') == 'sk-smoke-123', db_setting(data_dir, 'api_key'))

        st, _, body = http('POST', base + '/api/settings',
                           body={'api_key': '', 'clear_api_key': True, 'vendor': 'ds', 'model': 'deepseek-chat'})
        check('显式清除 Key 生效', db_setting(data_dir, 'api_key') == '', db_setting(data_dir, 'api_key'))
        check('清除后 api_key_set 变回 false',
              json.loads(body).get('api_key_set') is False, body[:160])

        test_launcher_port_probe()
        test_launcher_end_to_end()
        test_data_layer()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        shutil.rmtree(data_dir, ignore_errors=True)

    print('\n%d 项通过，%d 项失败' % (len(PASSED), len(FAILED)))
    if FAILED:
        print('失败项：' + '；'.join(FAILED))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
