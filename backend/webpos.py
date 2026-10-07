# -*- coding: utf-8 -*-
"""联网词性判定：先查免费词典接口（dictionaryapi.dev），查不到再交给 AI。

只用于「待确认清单」里用户主动点的联网判定，不参与普通离线检索；
断网 / 接口不可用时返回空，调用方会自动退回 AI 或保持待确认。
"""
import json
import urllib.parse
import urllib.request

API = 'https://api.dictionaryapi.dev/api/v2/entries/en/%s'
UA = 'KTRT/0.2.2'
# 免费词典接口的词性名 → 我们的标签
MAP = {
    'noun': 'n', 'verb': 'v', 'adjective': 'a', 'adverb': 'ad', 'preposition': 'prep',
    'conjunction': 'conj', 'pronoun': 'pron', 'numeral': 'num', 'article': 'art',
    'determiner': 'art', 'interjection': 'int', 'exclamation': 'int',
}


def lookup_pos(word, timeout=6):
    """查在线词典的词性；命中返回标签列表，否则空列表（任何异常都当没查到）。"""
    key = (word or '').strip().lower()
    if not key or ' ' in key or len(key) > 40:
        return []
    url = API % urllib.parse.quote(key)
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode('utf-8', 'replace'))
    except Exception:
        return []
    tags = set()
    for entry in (data if isinstance(data, list) else []):
        for meaning in (entry.get('meanings') or []):
            tag = MAP.get(str(meaning.get('partOfSpeech') or '').lower())
            if tag:
                tags.add(tag)
    order = ['n', 'v', 'a', 'ad', 'prep', 'conj', 'pron', 'num', 'art', 'int']
    return [t for t in order if t in tags]
