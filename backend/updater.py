# -*- coding: utf-8 -*-
"""一键更新：查最新 Release、下载热补丁、静默安装新版。

两条通道：
- 补丁通道（不用重启）：Release 里挂 patch-<版本>.zip，内含整套前端静态文件与 patch.json
  校验表；解压到数据目录 web/ 后覆盖内置前端，刷新页面即生效。
- 版本通道（换整包）：Release 里的 KTRTSetup-*.exe，下载后静默安装，装完自动重开程序。
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

from . import db

REPO = 'HoweyYang/KTRT'
ATOM_RELEASES = 'https://github.com/%s/releases.atom' % REPO
ATOM_COMMITS = 'https://github.com/%s/commits/main.atom' % REPO
ASSETS_URL = 'https://github.com/%s/releases/expanded_assets/%%s' % REPO
VERSION_RE = re.compile(r'(\d+(?:\.\d+)*[a-z]?)', re.I)
UA = 'KTRT-Updater'
CHUNK = 128 * 1024

VERSION = '0.0.0'
APP_EXE = ''
FROZEN = False

JOB = {
    'state': 'idle',      # idle / downloading / verifying / applying / installing / done / error
    'kind': '',
    'message': '',
    'received': 0,
    'total': 0,
    'error': '',
    'version': '',
}


def configure(version, exe_path='', frozen=False):
    global VERSION, APP_EXE, FROZEN
    VERSION, APP_EXE, FROZEN = version, exe_path or '', bool(frozen)


# ---------- 版本号 ----------

def version_key(v):
    m = re.match(r'^v?(\d+(?:\.\d+)*)([a-z]*)', str(v or '').strip(), re.I)
    if not m:
        return (0, 0, 0, '')
    nums = [int(x) for x in m.group(1).split('.')]
    while len(nums) < 3:
        nums.append(0)
    return (nums[0], nums[1], nums[2], (m.group(2) or '').lower())


def is_newer(candidate, current):
    a, b = version_key(candidate), version_key(current)
    return a > b


# ---------- 网络 ----------

def _proxy():
    for key in ('HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy'):
        v = os.environ.get(key)
        if v:
            return {'http': v, 'https': v}
    try:
        import winreg
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r'Software\Microsoft\Windows\CurrentVersion\Internet Settings') as k:
            enabled, _ = winreg.QueryValueEx(k, 'ProxyEnable')
            server, _ = winreg.QueryValueEx(k, 'ProxyServer')
        if not enabled or not server:
            return None
        if '=' in server:
            proxies = {}
            for part in server.split(';'):
                scheme, _, addr = part.strip().partition('=')
                if scheme in ('http', 'https') and addr:
                    proxies[scheme] = addr if '://' in addr else 'http://' + addr
            return proxies or None
        return {'http': 'http://' + server, 'https': 'http://' + server}
    except Exception:
        return None


def _opener():
    proxies = _proxy()
    return (urllib.request.build_opener(urllib.request.ProxyHandler(proxies))
            if proxies else urllib.request.build_opener())


def _plain(html):
    text = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html or '', flags=re.S | re.I)
    text = re.sub(r'<br\s*/?>|</p>|</li>', '\n', text, flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    text = (text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<')
                .replace('&gt;', '>').replace('&quot;', '"').replace('&#39;', "'"))
    return '\n'.join(line.strip() for line in text.splitlines() if line.strip())


def version_from_text(text):
    """从 tag / Release 标题里取裸版本号（'KTRT v0.2.0 · 首个正式版' → '0.2.0'）。"""
    for m in VERSION_RE.finditer(str(text or '')):
        v = m.group(1)
        if '.' in v:
            return v.lstrip('vV')
    return ''


def _size_bytes(text):
    m = re.match(r'([\d.]+)\s*(KB|MB|GB|bytes|Bytes)', str(text or '').strip())
    if not m:
        return 0
    scale = {'kb': 1024, 'mb': 1048576, 'gb': 1073741824, 'bytes': 1}[m.group(2).lower()]
    return int(float(m.group(1)) * scale)


def _assets(tag):
    """从 Release 资产列表片段取文件名 / 下载地址 / 大小（不走 GitHub API，避免限流）。"""
    url = ASSETS_URL % urllib.parse.quote(tag)
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with _opener().open(req, timeout=10) as r:
        html = r.read().decode('utf-8', 'replace')
    out = []
    for m in re.finditer(r'href="(/[^"]*?/releases/download/[^"]+)"', html):
        path = m.group(1)
        out.append({'name': urllib.parse.unquote(path.rsplit('/', 1)[-1]),
                    'url': 'https://github.com' + path, 'size': 0})
    for asset, size in zip(out, re.findall(
            r'>\s*([\d.]+\s*(?:KB|MB|GB|bytes|Bytes))\s*<', html)):
        asset['size'] = _size_bytes(size)
    return out


def latest_commit():
    """main 分支最新提交（只在 API 不通时用来展示）。"""
    req = urllib.request.Request(ATOM_COMMITS, headers={'User-Agent': UA})
    with _opener().open(req, timeout=8) as r:
        root = ET.fromstring(r.read().decode('utf-8', 'replace'))
    ns = {'a': 'http://www.w3.org/2005/Atom'}
    entries = root.findall('a:entry', ns)
    if not entries:
        return None
    e = entries[0]
    link = e.find('a:link', ns)
    href = link.get('href', '') if link is not None else ''
    return {
        'sha': href.rstrip('/').split('/')[-1][:7] if href else '',
        'message': (e.findtext('a:title', '', ns) or '').strip(),
        'date': e.findtext('a:updated', '', ns),
        'url': href,
    }


def latest_release():
    """最新 Release：tag、版本号、更新说明与资产（安装包 / 可选热补丁）。"""
    req = urllib.request.Request(ATOM_RELEASES, headers={'User-Agent': UA})
    with _opener().open(req, timeout=10) as r:
        root = ET.fromstring(r.read().decode('utf-8', 'replace'))
    ns = {'a': 'http://www.w3.org/2005/Atom'}
    entries = root.findall('a:entry', ns)
    if not entries:
        return None
    e = entries[0]
    link = e.find('a:link', ns)
    html_url = link.get('href', '') if link is not None else ''
    title = (e.findtext('a:title', '', ns) or '').strip()
    tag = html_url.rstrip('/').split('/')[-1] if '/tag/' in html_url else title
    out = {
        'tag': tag,
        'title': title,
        'version': version_from_text(tag) or version_from_text(title),
        'published_at': e.findtext('a:updated', '', ns),
        'html_url': html_url,
        'notes': _plain(e.findtext('a:content', '', ns))[:1200],
        'installer': None,
        'patch': None,
    }
    try:
        for asset in _assets(tag):
            low = asset['name'].lower()
            if low.endswith('.exe') and low.startswith('ktrtsetup'):
                out['installer'] = asset
            elif low.endswith('.zip') and low.startswith('patch-'):
                out['patch'] = dict(asset, version=out['version'])
    except Exception:
        pass
    return out


# ---------- 已装补丁 ----------

def overlay_dir(create=False):
    """热补丁目录：默认在数据目录下的 web/，优先于打包内置的前端。"""
    path = os.environ.get('KTRT_WEB_OVERLAY') or os.path.join(db.DATA_DIR, 'web')
    if create:
        os.makedirs(path, exist_ok=True)
    return path


def overlay_active():
    return os.path.isdir(overlay_dir()) and os.path.exists(os.path.join(overlay_dir(), 'index.html'))


def applied_patch():
    meta = os.path.join(overlay_dir(), 'patch.json')
    if not os.path.exists(meta):
        return None
    try:
        with open(meta, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def _patch_applicable(patch, applied):
    """补丁要比自己手上的新才提示。

    基线 = 已装补丁的版本，没装过就是当前程序版本。少了这一比，
    同一份补丁会一直显示"可更新"（应用完刷新还在），所以必须比一次。
    """
    pv = version_from_text(patch.get('name', '')) or patch.get('version', '')
    if not pv:
        return True          # 认不出补丁版本就别挡，免得把更新通道堵死
    return is_newer(pv, (applied or {}).get('version') or VERSION)


def status(deep=True):
    """给「更新」页用：当前版本、最新 Release、可用的补丁/整包、已装补丁。"""
    out = {
        'ok': True,
        'current_version': VERSION,
        'mode': 'packaged' if FROZEN else 'source',
        'latest': None,
        'installer': None,
        'patch': None,
        'applied_patch': applied_patch(),
        'overlay': overlay_active(),
        'error': '',
    }
    try:
        rel = latest_release()
    except Exception as e:
        out['ok'] = False
        out['error'] = '检查更新失败：%s' % e
        rel = None
    if rel:
        rel['newer'] = is_newer(rel['version'], VERSION)
        out['latest'] = rel
        out['installer'] = rel.get('installer')
        out['patch'] = rel.get('patch')
        if out['patch']:
            out['patch']['applicable'] = _patch_applicable(out['patch'], out['applied_patch'])
    if deep:
        try:
            out['commit'] = latest_commit()
        except Exception:
            out['commit'] = None
    return out


# ---------- 下载与进度 ----------

def job():
    return dict(JOB)


def _reset_job(kind, version):
    JOB.update({'state': 'idle', 'kind': kind, 'message': '', 'received': 0,
                'total': 0, 'error': '', 'version': version})


def _download(url, dest, label):
    JOB['state'] = 'downloading'
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with _opener().open(req, timeout=60) as r:
        total = int(r.headers.get('Content-Length') or 0)
        JOB['total'] = total
        JOB['received'] = 0
        with open(dest, 'wb') as f:
            while True:
                buf = r.read(CHUNK)
                if not buf:
                    break
                f.write(buf)
                JOB['received'] += len(buf)
                JOB['message'] = '正在下载%s %.1f / %.1f MB' % (
                    label, JOB['received'] / 1048576.0, (total or 0) / 1048576.0)
    if JOB['total'] and JOB['received'] != JOB['total']:
        raise RuntimeError('下载不完整（%d / %d 字节）' % (JOB['received'], JOB['total']))
    return dest


# ---------- 补丁 ----------

def _safe_rel(name):
    name = name.replace('\\', '/')
    if name.startswith('/') or ':' in name:
        raise RuntimeError('补丁包路径非法：%s' % name)
    parts = [p for p in name.split('/') if p not in ('', '.')]
    if any(p == '..' for p in parts):
        raise RuntimeError('补丁包路径非法：%s' % name)
    return os.path.join(*parts) if parts else ''


def apply_patch(zip_path, version):
    """热补丁：先整套解压到临时目录并逐个校验，全部通过才换上去。

    之前是边解压边往正式目录里写，一旦中途某个文件校验失败，就会留下
    "新 index.html + 旧 app.js" 这种半成品 overlay，页面直接坏掉，
    而且旧补丁已被挪到备份目录、不会自动回滚。现在校验不过就原地不动。
    """
    root = overlay_dir(create=True)
    staging = root + '_staging'
    JOB.update({'state': 'applying', 'message': '正在应用补丁…'})
    shutil.rmtree(staging, ignore_errors=True)
    os.makedirs(staging, exist_ok=True)
    count = 0
    try:
        files = {}
        with zipfile.ZipFile(zip_path) as z:
            names = [n for n in z.namelist() if not n.endswith('/')]
            if 'patch.json' in names:
                try:
                    manifest = json.loads(z.read('patch.json').decode('utf-8'))
                    files = manifest.get('files') or {}
                except Exception:
                    files = {}
            for name in names:
                if name == 'patch.json':
                    continue
                rel = _safe_rel(name)
                if not rel:
                    continue
                data = z.read(name)
                if files.get(name):
                    digest = hashlib.sha256(data).hexdigest()
                    if digest != files[name]:
                        raise RuntimeError('补丁校验失败：%s' % name)
                target = os.path.join(staging, rel)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, 'wb') as f:
                    f.write(data)
                count += 1
        if not os.path.exists(os.path.join(staging, 'index.html')):
            raise RuntimeError('补丁包不完整：缺少 index.html')
        meta = {
            'version': version,
            'applied_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'files': count,
        }
        with open(os.path.join(staging, 'patch.json'), 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        # 就位：旧目录改名备份 → 新目录改成正式名；改名失败就把备份换回来
        backup = ''
        if os.path.isdir(root):
            if os.listdir(root):
                backup = '%s_backup_%s' % (root, time.strftime('%Y%m%d_%H%M%S'))
                shutil.rmtree(backup, ignore_errors=True)
                shutil.move(root, backup)
            else:
                os.rmdir(root)          # 空目录直接去掉，否则 move 会塞进它里面
        try:
            shutil.move(staging, root)
        except Exception:
            if backup and not os.path.isdir(root):
                shutil.move(backup, root)
            raise
        _prune_backups(root)
        return count
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _prune_backups(root):
    parent = os.path.dirname(root)
    prefix = os.path.basename(root) + '_backup_'
    olds = sorted(d for d in os.listdir(parent) if d.startswith(prefix))
    for d in olds[:-2]:      # 只留最近两份
        shutil.rmtree(os.path.join(parent, d), ignore_errors=True)


# ---------- 整包 ----------

def launch_installer(setup_path):
    """启动静默安装；装完由独立脚本重新拉起程序（[Run] 在静默模式下不执行）。"""
    script = write_helper_script(setup_path)
    flags = getattr(subprocess, 'DETACHED_PROCESS', 0) | getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    subprocess.Popen(['cmd', '/c', script], creationflags=flags, close_fds=True)
    subprocess.Popen([setup_path, '/SILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
                      '/NOCANCEL', '/CLOSEAPPLICATIONS'])


def write_helper_script(setup_path):
    """生成等待安装结束再拉起程序的批处理（分开写方便自测）。"""
    setup_name = os.path.basename(setup_path)
    app_exe = APP_EXE if (FROZEN and APP_EXE and os.path.exists(APP_EXE)) else ''
    app_name = os.path.basename(app_exe) if app_exe else ''
    script = os.path.join(tempfile.gettempdir(), 'ktrt_update_%d.cmd' % int(time.time()))
    lines = ['@echo off', 'setlocal', 'set /a n=0',
             ':appear', 'timeout /t 2 /nobreak >nul', 'set /a n+=1',
             'tasklist /FI "IMAGENAME eq %s" | find /I "%s" >nul' % (setup_name, setup_name),
             'if errorlevel 1 if %n% lss 90 goto appear',
             ':finish', 'timeout /t 3 /nobreak >nul',
             'tasklist /FI "IMAGENAME eq %s" | find /I "%s" >nul' % (setup_name, setup_name),
             'if not errorlevel 1 goto finish']
    if app_name:
        # 换到 per-user 安装后程序在别处，优先拉起新位置那份；
        # 判断放在脚本运行时（安装已结束），而不是生成脚本的时候。
        installed = '%LOCALAPPDATA%\\Programs\\KTRT\\' + app_name
        lines += ['set "KTRTEXE=' + app_exe + '"',
                  'if exist "' + installed + '" set "KTRTEXE=' + installed + '"',
                  'tasklist /FI "IMAGENAME eq %s" | find /I "%s" >nul' % (app_name, app_name),
                  'if not errorlevel 1 goto done',
                  'if not "%KTRTEXE%"=="" start "" "%KTRTEXE%"']
    lines += [':done', 'del "%~f0"']
    with open(script, 'w', encoding='ascii', errors='ignore', newline='') as f:
        f.write('\r\n'.join(lines) + '\r\n')
    return script


# ---------- 入口 ----------

def start(kind, url, version):
    """后台执行下载 + 应用；前端轮询 /api/update/progress。"""
    if JOB['state'] in ('downloading', 'applying', 'installing'):
        raise RuntimeError('已有更新任务在进行中')
    _reset_job(kind, version)

    def run():
        try:
            if kind == 'patch':
                dest = os.path.join(tempfile.gettempdir(), 'ktrt_patch_%s.zip' % version)
                _download(url, dest, '补丁')
                JOB['message'] = '正在校验并应用补丁…'
                count = apply_patch(dest, version)
                JOB['state'] = 'done'
                JOB['message'] = '补丁已应用（%d 个文件），刷新页面即可生效' % count
            elif kind == 'full':
                name = os.path.basename(urllib.parse.urlparse(url).path) or 'KTRTSetup.exe'
                dest = os.path.join(tempfile.gettempdir(), name)
                _download(url, dest, '安装包')
                JOB.update({'state': 'installing',
                            'message': '正在启动安装程序，请在系统弹窗里点“是”授权'})
                launch_installer(dest)
                JOB['message'] = '安装程序已启动，程序即将退出并自动重开'
                time.sleep(2)
                threading.Timer(1.0, lambda: os._exit(0)).start()
            else:
                raise RuntimeError('未知的更新类型：%s' % kind)
        except Exception as e:
            JOB['state'] = 'error'
            JOB['error'] = str(e)
            JOB['message'] = '更新失败：%s' % e

    threading.Thread(target=run, daemon=True).start()
    return job()


def restart_app(delay=1.0):
    threading.Timer(delay, lambda: os._exit(0)).start()
