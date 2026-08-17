import asyncio
import hashlib
import os

import edge_tts

from . import db

VOICES = {
    '英语': 'en-US-AriaNeural',
    '英语(英)': 'en-GB-SoniaNeural',
    '法语': 'fr-FR-DeniseNeural',
}


def _cache_dir():
    d = os.path.join(db.DATA_DIR, 'tts_cache')
    os.makedirs(d, exist_ok=True)
    return d


def voice_for(language):
    return VOICES.get(language) or VOICES.get('英语')


def synthesize(text, language):
    """Synthesize speech; returns path to cached mp3."""
    voice = voice_for(language)
    key = hashlib.md5((voice + '|' + text).encode('utf-8')).hexdigest()
    path = os.path.join(_cache_dir(), key + '.mp3')
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    asyncio.run(edge_tts.Communicate(text, voice).save(path))
    return path
