# -*- coding: utf-8 -*-
"""词性蒙版：从释义里抽出词性，并据此生成"定向词书"。

词性写在释义开头，形如「n. 减少，减轻」「vi. 停留…\\nvt. 忍受…」；
一个词可能命中多个词性，所以它会同时落进多个筛选桶（多义即多重对应）。
ECDICT 的 pos 列实测全为空，只能从文本解析；有些词书（如雅思）的释义是纯中文
（"岩浆"），本身没标词性，这时去离线词典借一把 —— ECDICT 的 translation /
definition 同样带 n. / a. / vt. 这类标记。
"""
import os
import re
import sqlite3

from . import db

LABELS = {
    'n': '名词', 'v': '动词', 'a': '形容词', 'ad': '副词', 'prep': '介词',
    'conj': '连词', 'pron': '代词', 'num': '数词', 'art': '冠词',
    'int': '感叹词', 'aux': '助动词', 'abbr': '缩写', 'phr': '短语', 'other': '其他',
}
ORDER = ['n', 'v', 'a', 'ad', 'prep', 'conj', 'pron', 'num', 'art', 'int', 'aux', 'abbr', 'phr', 'other']

_ALIAS = {
    'n': 'n', 'v': 'v', 'vt': 'v', 'vi': 'v', 'adj': 'a', 'a': 'a',
    'adv': 'ad', 'ad': 'ad', 'prep': 'prep', 'conj': 'conj', 'pron': 'pron',
    'num': 'num', 'art': 'art', 'int': 'int', 'interj': 'int', 'aux': 'aux',
    'abbr': 'abbr', 'phr': 'phr', 'phrase': 'phr',
}
_TAG_RE = re.compile(
    r'(?<![A-Za-z])(n|v|vt|vi|adj|a|adv|ad|prep|conj|pron|num|art|int|interj|aux|abbr|phr)\.(?![A-Za-z])',
    re.I)


def pos_of(meaning):
    """返回该释义涉及的规范词性（按 ORDER 排序，认不出则归 other）。"""
    found = _tags_from_text(meaning)
    if not found:
        return ['other']
    return [k for k in ORDER if k in found]


def pos_of_word(meaning, word):
    """先看释义，释义没标就去离线词典借（雅思这类纯中文释义靠这个补）；都没有才算 other。"""
    found = _tags_from_text(meaning) or _POS_CACHE.get((word or '').strip().lower(), set())
    if not found:
        return ['other']
    return [k for k in ORDER if k in found]


def _tags_from_text(text):
    """从一段文本里抽词性标记（n. / a. / vt. 等），返回规范 key 集合。"""
    found = set()
    for m in _TAG_RE.finditer(text or ''):
        key = _ALIAS.get(m.group(1).lower())
        if key:
            found.add(key)
    return found


_POS_CACHE = {}      # word → 从离线词典借来的词性集合（空集合 = 查过，没有）


def _load_dict_pos(rows):
    """释义没标词性的词，批量去离线词典借（一次查一批，别逐词开连接）。"""
    need = set()
    for r in rows:
        if _tags_from_text(r['meaning']):
            continue
        key = (r['word'] or '').strip().lower()
        if key and key not in _POS_CACHE:
            need.add(key)
    if not need or not os.path.exists(db.DICT_DB_PATH):
        return
    words = sorted(need)
    try:
        conn = sqlite3.connect(db.DICT_DB_PATH)
        for i in range(0, len(words), 800):
            chunk = words[i:i + 800]
            sql = ('SELECT word, translation, definition FROM dict WHERE word IN (%s)'
                   % ','.join('?' * len(chunk)))
            for word, translation, definition in conn.execute(sql, chunk):
                _POS_CACHE[word] = _tags_from_text(translation) or _tags_from_text(definition)
        conn.close()
    except Exception:
        return
    for w in words:
        _POS_CACHE.setdefault(w, set())     # 词典里也没有：记空，下次不再查


def _rows(conn, book_id, list_no=None):
    sql = ('SELECT id, list_no, seq, word, phonetic, meaning, collocations, phrases, '
           'synonyms, antonyms, root_words, phrasal_keys FROM words WHERE book_id=?')
    params = [book_id]
    if list_no:
        sql += ' AND list_no=?'
        params.append(list_no)
    return conn.execute(sql, params).fetchall()


def stats(book_id, list_no=None):
    """统计某本词书（可选某个 List）里各词性的词条数。"""
    with db.get_conn() as conn:
        rows = _rows(conn, book_id, list_no)
    _load_dict_pos(rows)
    counts = {k: 0 for k in ORDER}
    multi = 0
    for r in rows:
        hit = pos_of_word(r['meaning'], r['word'])
        if len(hit) > 1:
            multi += 1
        for k in hit:
            counts[k] += 1
    return {
        'total': len(rows),
        'multi': multi,
        'items': [{'key': k, 'label': LABELS[k], 'count': counts[k]} for k in ORDER if counts[k]],
    }


def _list_no_for(word):
    ch = (word or ' ').strip()[:1].lower()
    return ord(ch) - ord('a') + 1 if 'a' <= ch <= 'z' else 27


def build(book_id, list_no, poss, name=''):
    """按选定词性生成一本新词书：按字母排序、按首字母分 List、并记下原书位置。"""
    poss = [p for p in (poss or []) if p in LABELS]
    if not poss:
        raise RuntimeError('请先勾选至少一个词性')
    want = set(poss)
    with db.get_conn() as conn:
        src = conn.execute('SELECT id, name, language FROM word_books WHERE id=?', (book_id,)).fetchone()
        if src is None:
            raise RuntimeError('词书不存在')
        rows = _rows(conn, book_id, list_no)
        _load_dict_pos(rows)
        picked = [r for r in rows if want & set(pos_of_word(r['meaning'], r['word']))]
        if not picked:
            raise RuntimeError('这个范围内没有符合条件的词')
        book_name = (name or '').strip() or (src['name'] + '·' + '+'.join(LABELS[p] for p in poss))
        if conn.execute('SELECT id FROM word_books WHERE name=?', (book_name,)).fetchone():
            raise RuntimeError('已存在同名词书《%s》：先删掉它，或换个名字' % book_name)
        picked.sort(key=lambda r: (r['word'].lower(), r['list_no'], r['seq']))
        cur = conn.execute('INSERT INTO word_books(name, language, source) VALUES(?,?,?)',
                           (book_name, src['language'], '词性蒙版'))
        new_id = cur.lastrowid
        counter, data = {}, []
        for r in picked:
            ln = _list_no_for(r['word'])
            counter[ln] = counter.get(ln, 0) + 1
            data.append((new_id, ln, counter[ln], r['word'], r['phonetic'], r['meaning'],
                         r['collocations'], r['phrases'], r['synonyms'], r['antonyms'],
                         r['root_words'], r['phrasal_keys'],
                         '%d|%d|%d' % (book_id, r['list_no'], r['seq'])))
        conn.executemany(
            'INSERT INTO words(book_id, list_no, seq, word, phonetic, meaning, collocations, '
            'phrases, synonyms, antonyms, root_words, phrasal_keys, source_ref) '
            'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)', data)
    return {'book_id': new_id, 'name': book_name, 'count': len(picked), 'lists': len(counter)}
