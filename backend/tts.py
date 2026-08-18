import asyncio
import hashlib
import os
import time

from . import db

# 语言 -> 可选发音（美/英 × 男/女；法语男/女）
VOICES = {
    '英语': {
        '美音·男': 'en-US-GuyNeural',
        '美音·女': 'en-US-AriaNeural',
        '英音·男': 'en-GB-RyanNeural',
        '英音·女': 'en-GB-SoniaNeural',
    },
    '法语': {
        '女声': 'fr-FR-DeniseNeural',
        '男声': 'fr-FR-HenriNeural',
    },
}
DEFAULT_VOICE = {'英语': '美音·男', '法语': '女声'}

# 缓存策略：30 天以上的旧文件清理；总大小超过 200MB 时删最旧
CACHE_MAX_AGE_DAYS = 30
CACHE_MAX_MB = 200
_PRUNE_INTERVAL = 86400  # 每天最多执行一次清理


def _cache_dir():
    d = os.path.join(db.DATA_DIR, 'tts_cache')
    os.makedirs(d, exist_ok=True)
    return d


def voice_for(language, voice_key=None):
    lang = language if language in VOICES else '英语'
    voices = VOICES[lang]
    key = voice_key if voice_key in voices else DEFAULT_VOICE[lang]
    return voices[key]


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


def _edge_params(rate='0', pitch='0', volume='100'):
    """把设置数值转成 edge-tts 参数字符串：语速 %, 音调 Hz, 音量 %（100=默认音量）。"""
    try:
        r = int(rate or 0)
        p = int(pitch or 0)
        v = int(volume if volume != '' else '100')
    except ValueError:
        r = p = 0
        v = 100
    rate_s = ('+' if r >= 0 else '') + str(r) + '%'
    pitch_s = ('+' if p >= 0 else '') + str(p) + 'Hz'
    vol = max(-100, min(100, v - 100))
    volume_s = ('+' if vol >= 0 else '') + str(vol) + '%'
    return rate_s, pitch_s, volume_s


def synthesize(text, language, voice=None, rate='0', pitch='0', volume='100'):
    """Synthesize speech; returns path to cached mp3."""
    voice = voice_for(language, voice)
    rate_s, pitch_s, volume_s = _edge_params(rate, pitch, volume)
    key = hashlib.md5((voice + '|' + rate_s + '|' + pitch_s + '|' + volume_s + '|' + text).encode('utf-8')).hexdigest()
    path = os.path.join(_cache_dir(), key + '.mp3')
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    _maybe_prune()
    import edge_tts  # 延迟导入，降低启动内存占用
    asyncio.run(edge_tts.Communicate(text, voice, rate=rate_s, pitch=pitch_s, volume=volume_s).save(path))
    return path
