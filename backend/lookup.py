# -*- coding: utf-8 -*-
"""统一检索层：一个入口 lookup()，查词页 / 卡片查词典 / 风暴素材 / 蒙版判定都走它。

来源优先级：内置 ECDICT → 词性增强包（WordNet/Moby）→ 已导入词书 →（在线，默认关）。
每个来源独立 try：坏了、没装、被禁用都只是少一个来源，不阻断整体检索。
"""
import os
import sqlite3

from . import db, pos as poslib

EXCHANGE_NAMES = {'p': '过去式', 'd': '过去分词', 'i': '现在分词', '3': '第三人称单数',
                  'r': '比较级', 't': '最高级', 's': '复数', '0': '原形', '1': '变换形式'}
STOP = ('s', 'es', 'ed', 'd', 'ing', 'ies', 'ly', 'er', 'est')


def _exchange_pretty(exchange):
    """把 ECDICT 的 exchange 字段翻成人话（原形/复数/过去式…）。"""
    if not exchange:
        return ''
    parts = []
    for chunk in str(exchange).split('/'):
        if ':' not in chunk:
            continue
        code, _, val = chunk.partition(':')
        name = EXCHANGE_NAMES.get(code)
        if name and val:
            parts.append('%s %s' % (name, val))
    return '；'.join(parts)


def _ecdict(word):
    """内置离线词典（dictionary.db），命中返回整行 dict。"""
    key = (word or '').strip().lower()
    if not key or not os.path.exists(db.DICT_DB_PATH):
        return {}
    conn = sqlite3.connect(db.DICT_DB_PATH)
    try:
        cur = conn.execute('SELECT * FROM dict WHERE word=?', (key,))
        row = cur.fetchone()
        if not row:
            return {}
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))
    finally:
        conn.close()


def _ecdict_suggest(word):
    """没查到就给建议：去掉常见词尾再查 + 前缀模糊匹配。"""
    key = (word or '').strip().lower()
    if not key or not os.path.exists(db.DICT_DB_PATH):
        return [], []
    variants, hits = [], []
    for suf in STOP:
        if len(key) > len(suf) + 2 and key.endswith(suf):
            variants.append(key[:-len(suf)])
    try:
        conn = sqlite3.connect(db.DICT_DB_PATH)
    except Exception:
        return variants, []
    try:
        for v in variants:
            if conn.execute('SELECT 1 FROM dict WHERE word=?', (v,)).fetchone():
                hits.append(v)
        prefix = key[:max(3, len(key) - 1)]
        for (w,) in conn.execute('SELECT word FROM dict WHERE word LIKE ? LIMIT 6', (prefix + '%',)):
            if w != key:
                hits.append(w)
    except Exception:
        pass
    finally:
        conn.close()
    seen, out = set(), []
    for w in hits:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return variants, out[:6]


def lookup(word, depth='quick'):
    """统一检索：返回结构化结果，来源与原文都标清楚。

    depth='quick'：查词页 / 卡片（词性 + 中英释义 + 词形 + 建议）
    depth='full' ：风暴（多带 gloss 原文）
    """
    raw = (word or '').strip()
    key = raw.lower()
    out = {
        'word': raw, 'canonical': '', 'found': False, 'sources': [], 'errors': [],
        'pos': [], 'pos_source': '', 'translation': '', 'definition': '',
        'gloss': {}, 'exchange': '', 'exchange_text': '',
        'books': [], 'suggestions': [], 'variants': [],
    }
    if not raw:
        return out

    # ① 内置 ECDICT
    try:
        row = _ecdict(key)
        if row:
            out['found'] = True
            out['sources'].append('ECDICT')
            out['translation'] = (row.get('translation') or '').replace('\\n', '\n')
            out['definition'] = (row.get('definition') or '').replace('\\n', '\n')
            out['exchange'] = row.get('exchange') or ''
            out['exchange_text'] = _exchange_pretty(out['exchange'])
    except Exception as e:
        out['errors'].append('内置词典不可用：%s' % e)

    # ② 词性增强包（WordNet / Moby）：英文原文释义（高阶学习者要用）
    try:
        gloss = poslib.pack_gloss(key)
        if gloss:
            out['sources'].append('WordNet')
            if depth == 'full':
                out['gloss'] = gloss
            else:
                out['gloss'] = {k: v for k, v in list(gloss.items())[:1]}
    except Exception as e:
        out['errors'].append('增强包不可用：%s' % e)

    # ③ 已导入词书（中文释义 / 搭配 / 位置）
    try:
        with db.get_conn() as conn:
            for r in conn.execute(
                    'SELECT w.list_no, w.seq, w.meaning, w.collocations, '
                    'b.id book_id, b.name book_name FROM words w '
                    'JOIN word_books b ON b.id=w.book_id WHERE w.word=? COLLATE NOCASE '
                    'ORDER BY b.id, w.list_no, w.seq LIMIT 20', (raw,)):
                out['books'].append({'book_id': r['book_id'], 'book_name': r['book_name'],
                                     'list_no': r['list_no'], 'seq': r['seq'],
                                     'meaning': r['meaning'] or '',
                                     'collocations': r['collocations'] or ''})
            if out['books']:
                out['found'] = True
                out['sources'].append('词书')
    except Exception as e:
        out['errors'].append('词书检索失败：%s' % e)

    # ④ 词性（书 → 词典 → 增强包 → 规则 → 待确认）
    try:
        meaning = out['books'][0]['meaning'] if out['books'] else ''
        tags, src = poslib.judge(meaning or out['translation'], raw)
        out['pos'] = tags
        out['pos_source'] = src
    except Exception as e:
        out['errors'].append('词性判定失败：%s' % e)

    # ⑤ 没查到：给拼写 / 变形建议
    if not out['found']:
        try:
            variants, sug = _ecdict_suggest(key)
            out['variants'] = variants
            out['suggestions'] = sug
        except Exception as e:
            out['errors'].append('建议生成失败：%s' % e)
    return out
