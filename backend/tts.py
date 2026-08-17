import asyncio
import hashlib
import os
import time

from . import db

VOICES = {
    '英语': 'en-US-AriaNeural',
    '英语(英)': 'en-GB-SoniaNeural',
    '法语': 'fr-FR-DeniseNeural',
}

# 缓存策略：30 天以上的旧文件清理；总大小超过 200MB 时删最旧
CACHE_MAX_AGE_DAYS = 30
CACHE_MAX_MB = 200
_PRUNE_INTERVAL = 86400  # 每天最多执行一次清理


def _cache_dir():
    d = os.path.join(db.DATA_DIR, 'tts_cache')
    os.makedirs(d, exist_ok=True)
    return d


def voice_for(language):
    return VOICES.get(language) or VOICES.get('英语')


def _prune(d):
    now = time.time()
    max_age = CACHE_MAX_AGE_DAYS * 86400
    limit = CACHE_MAX_MB * 1024 * 1024
    files = []
    total = 0
    for fn in os.listdir(d):
        if not fn.endswith('.mp3'):
            continue
        p = os.path.join(d, fn)
        try:
            st = os.stat(p)
        except OSError:
            continue
        total += st.st_size
        files.append((st.st_mtime, st.st_size, p))
    keep = []
    for mtime, size, p in files:
        if now - mtime > max_age:
            try:
                os.remove(p)
                total -= size
            except OSError:
                keep.append((mtime, size, p))
        else:
            keep.append((mtime, size, p))
    keep.sort()
    for mtime, size, p in keep:
        if total <= limit:
            break
        try:
            os.remove(p)
            total -= size
        except OSError:
            pass


def _maybe_prune():
    d = _cache_dir()
    marker = os.path.join(d, '.last_prune')
    try:
        if os.path.exists(marker) and time.time() - os.path.getmtime(marker) < _PRUNE_INTERVAL:
            return
        _prune(d)
        with open(marker, 'w') as f:
            f.write(str(time.time()))
    except Exception:
        pass


def synthesize(text, language):
    """Synthesize speech; returns path to cached mp3."""
    voice = voice_for(language)
    key = hashlib.md5((voice + '|' + text).encode('utf-8')).hexdigest()
    path = os.path.join(_cache_dir(), key + '.mp3')
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    _maybe_prune()
    import edge_tts  # 延迟导入，降低启动内存占用
    asyncio.run(edge_tts.Communicate(text, voice).save(path))
    return path
