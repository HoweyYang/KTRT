# -*- coding: utf-8 -*-
"""词性筛选（词蒙版）：从释义里抽出词性，并据此生成"定向词书"。

词性写在释义开头，形如「n. 减少，减轻」「vi. 停留…\\nvt. 忍受…」；
一个词可能命中多个词性，所以它会同时落进多个筛选桶（多义即多重对应）。
ECDICT 的 pos 列实测全为空，所以只能从释义文本解析。
"""
import re

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
    found = set()
    for m in _TAG_RE.finditer(meaning or ''):
        key = _ALIAS.get(m.group(1).lower())
        if key:
            found.add(key)
    if not found:
        return ['other']
    return [k for k in ORDER if k in found]


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
    counts = {k: 0 for k in ORDER}
    multi = 0
    for r in rows:
        hit = pos_of(r['meaning'])
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
        picked = [r for r in _rows(conn, book_id, list_no) if want & set(pos_of(r['meaning']))]
        if not picked:
            raise RuntimeError('这个范围内没有符合条件的词')
        book_name = (name or '').strip() or (src['name'] + '·' + '+'.join(LABELS[p] for p in poss))
        if conn.execute('SELECT id FROM word_books WHERE name=?', (book_name,)).fetchone():
            raise RuntimeError('已存在同名词书《%s》：先删掉它，或换个名字' % book_name)
        picked.sort(key=lambda r: (r['word'].lower(), r['list_no'], r['seq']))
        cur = conn.execute('INSERT INTO word_books(name, language, source) VALUES(?,?,?)',
                           (book_name, src['language'], '词性筛选'))
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
