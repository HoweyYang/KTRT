# 内置动词短语库：加载 data/phrasal_verbs.json 并按动词检索。
# 导入词书时（importer）与学词页卡片（app）共用同一份内存索引。
import json
import os
import re

BY_KEY = {}    # 短语小写 -> 条目
BY_HEAD = {}   # 首个词（动词） -> 条目列表
PATH = ''

# 明显不是动词的词性开头（n. adj. adv. prep. conj. pron. art. num. int.）
_NON_VERB = re.compile(r'^\s*(?:n|adj|adv|prep|conj|pron|art|num|int)\b\.?', re.I)
_VERB = re.compile(r'^\s*(?:v|vt|vi|verb)\b\.?', re.I)


def load(path):
    """加载短语库；返回是否加载成功。"""
    global BY_KEY, BY_HEAD, PATH
    if not path or not os.path.exists(path):
        return False
    try:
        data = json.load(open(path, encoding='utf-8'))
    except Exception:
        return False
    BY_KEY = {g['key']: g for g in data if g.get('key')}
    idx = {}
    for key, g in BY_KEY.items():
        idx.setdefault(key.split(' ')[0], []).append(g)
    for v in idx.values():
        v.sort(key=lambda e: (len(e['key']), e['key']))
    BY_HEAD = idx
    PATH = path
    return True


def is_verb(meaning):
    """按词性释义判断是不是动词：明确是别的词性就排除，没写词性则不排除。"""
    m = (meaning or '').strip()
    if not m:
        return True
    if _VERB.match(m):
        return True
    if _NON_VERB.match(m):
        return False
    return True


def keys_for(word, meaning='', only_verb=True):
    """该词命中的短语动词 key 列表（默认只认动词条目）。"""
    w = (word or '').strip()
    if not w or ' ' in w:
        return []
    if only_verb and not is_verb(meaning):
        return []
    return [g['key'] for g in BY_HEAD.get(w.lower(), [])]


def entries_for_keys(keys, limit=8):
    out = []
    for k in keys or []:
        g = BY_KEY.get((k or '').strip().lower())
        if g:
            out.append(g)
        if len(out) >= limit:
            break
    return out
