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

# 蒙版筛选用的粗桶（0.2.2 起按语言学合并：名词性含代词/数词/冠词/缩写；
# 介词连词同属封闭功能词；短语与感叹词归其他；判不出的单独一桶"待确认"）。
GROUPS = [
    ('noun', '名词性', ('n', 'pron', 'num', 'art', 'abbr')),
    ('verb', '动词', ('v',)),
    ('adj', '形容词', ('a',)),
    ('adv', '副词', ('ad',)),
    ('func', '虚词（介词·连词）', ('prep', 'conj')),
    ('misc', '其他（短语·感叹）', ('phr', 'int')),
    ('todo', '待确认', ('todo', 'other')),
]
LABELS = {key: label for key, label, _ in GROUPS}
ORDER = [key for key, _, _ in GROUPS]
_GROUP_OF = {base: key for key, _, bases in GROUPS for base in bases}

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
    """粗桶：释义 → 离线词典 → 增强包 → 词缀规则；都没有算「待确认」。"""
    key = (word or '').strip().lower()
    tags = (_subtags_from_text(meaning) or _POS_CACHE.get(key, set())
            or _PACK_POS.get(key, set()) or _affix_tags(word))
    groups = {_GROUP_OF[b] for b in _base_of(tags) if b in _GROUP_OF}
    if not groups:
        return ['todo']
    return [k for k in ORDER if k in groups]


def _tags_from_text(text):
    """从一段文本里抽词性标记（n. / a. / vt. 等），返回规范 key 集合。"""
    found = set()
    for m in _TAG_RE.finditer(text or ''):
        key = _ALIAS.get(m.group(1).lower())
        if key:
            found.add(key)
    return found


_POS_CACHE = {}      # word → 从离线词典借来的词性集合（空集合 = 查过，没有）
_DICT_TEXT = {}      # word → 词典原文（translation 优先，其次 definition）
_EXCH_CACHE = {}     # word → exchange 字段（判断可数性用）
_PACK_POS = {}       # word → 增强包（WordNet / Moby）的词性
_PACK_GLOSS = {}     # word → {词性: 英文原文释义}
_PACK_MISS = set()   # 增强包里查过没有的词
_PACK_PATH = os.path.join(db.DATA_DIR, 'reflib', 'refpos.db')
RULE_VERSION = 'r2'   # 判定规则版本：改了规则就整体重扫一次（和增强包一起做戳）


def _load_pack(rows):
    """增强包：批量取词性；文件不存在就直接跳过（没装包也能跑）。"""
    if not os.path.exists(_PACK_PATH) or not pack_enabled():
        return
    need = set()
    for r in rows:
        key = (r['word'] or '').strip().lower()
        if key and key not in _PACK_POS and key not in _PACK_MISS:
            need.add(key)
    if not need:
        return
    words = sorted(need)
    try:
        conn = sqlite3.connect(_PACK_PATH)
        for i in range(0, len(words), 800):
            chunk = words[i:i + 800]
            sql = ('SELECT word, tags FROM pos WHERE word IN (%s)' % ','.join('?' * len(chunk)))
            for word, tags in conn.execute(sql, chunk):
                _PACK_POS[word] = set(t for t in (tags or '').split('|') if t)
        conn.close()
    except Exception:
        return
    for w in words:
        _PACK_MISS.add(w)


def pack_gloss(word):
    """增强包里的英文原文释义（每词每词性第一条），给高阶学习者看原文用。"""
    key = (word or '').strip().lower()
    if not key or not os.path.exists(_PACK_PATH) or not pack_enabled():
        return {}
    if key not in _PACK_GLOSS:
        _PACK_GLOSS[key] = {}
        try:
            conn = sqlite3.connect(_PACK_PATH)
            for pos_, text in conn.execute('SELECT pos, text FROM gloss WHERE word=?', (key,)):
                _PACK_GLOSS[key][pos_] = text
            conn.close()
        except Exception:
            pass
    return _PACK_GLOSS[key]


def pack_enabled():
    """增强包是否启用（离线参考库面板可开关）。"""
    try:
        return db.get_setting('reflib_pack_enabled', '1') != '0'
    except Exception:
        return True


def reset_pack_cache():
    """开关增强包后清缓存，让判定重新走一遍。"""
    _PACK_POS.clear()
    _PACK_MISS.clear()
    _PACK_GLOSS.clear()

# ---------- 细分判定（0.2.2）：闭集表 + 关键词信号 ----------

LINKING = {  # 系动词（核心表：中文教材那套"变化类 / 表象类 / 持续类"里最常用的）
    'be', 'become', 'seem', 'appear', 'look', 'feel', 'sound', 'taste', 'smell',
    'remain', 'stay', 'turn', 'grow', 'get', 'prove',
}
MODAL = {'can', 'could', 'may', 'might', 'must', 'shall', 'should', 'will', 'would',
         'ought', 'need', 'dare', 'used'}
AUX = {'be', 'am', 'is', 'are', 'was', 'were', 'been', 'being', 'have', 'has', 'had',
       'do', 'does', 'did', 'will', 'would', 'shall', 'should'}
CAUSATIVE = {'make', 'let', 'have', 'get', 'cause', 'force', 'enable', 'allow', 'permit',
             'require', 'persuade', 'remind', 'help', 'keep', 'leave', 'drive', 'lead',
             'render', 'set', 'turn', 'bring', 'put', 'send', 'compel', 'oblige',
             'encourage', 'inspire', 'induce', 'prompt', 'urge'}
_CAUS_PREFIX = ('使', '让', '令')          # 首个中文释义以这些字开头 → 使役
_LINK_PREFIX = ('变成', '变得', '成为', '显得', '看起来', '听起来', '闻起来', '尝起来', '保持')

# 词缀规则（只在前四级都判不出时用，来源标 rule）
_SUF_NOUN = ('tion', 'sion', 'ment', 'ness', 'ity', 'ty', 'ance', 'ence', 'ship', 'hood',
             'ism', 'ist', 'ure', 'age', 'ery', 'ory', 'ary', 'ology', 'graphy', 'meter')
_SUF_ADJ = ('ous', 'ive', 'able', 'ible', 'al', 'ial', 'ic', 'ical', 'ful', 'less', 'ent',
            'ant', 'ary', 'ish', 'like', 'worthy', 'proof', 'tight', 'free', 'tolerant',
            'friendly', 'based', 'driven', 'aware', 'proofed', 'resistant', 'dependent')
_SUF_VERB = ('ize', 'ise', 'ify', 'ate', 'en')


def _affix_tags(word):
    """词形/结构兜底：带连字符的复合词、词组、常见词缀。"""
    w = (word or '').strip().lower()
    if len(w) < 4:
        return set()
    if '-' in w:                       # shade-tolerant / state-of-the-art
        tail = w.rsplit('-', 1)[-1]
        if tail.endswith(_SUF_ADJ) or tail.endswith(('ed', 'ing')):
            return {'a'}
        return set()
    if ' ' in w:                       # 词组：按中心词判
        head = w.split()[-1]
        if head.endswith(_SUF_ADJ) or head.endswith('ed'):
            return {'a'}
        return {'n'}
    if w.endswith(_SUF_ADJ):
        return {'a'}
    if w.endswith(_SUF_NOUN):
        return {'n'}
    if w.endswith('ly'):
        return {'ad'}
    if w.endswith(_SUF_VERB) and len(w) > 5:
        return {'v'}
    return set()


def _subtags_from_text(text):
    """从文本抽细分标记：vt → v:vt，vi → v:vi，adj → a…（比 base 版多一层）。"""
    out = set()
    for m in _TAG_RE.finditer(text or ''):
        raw = m.group(1).lower()
        key = _ALIAS.get(raw)
        if not key:
            continue
        out.add(key)
        if key == 'v':
            if raw == 'vt':
                out.add('v:vt')
            elif raw == 'vi':
                out.add('v:vi')
    return out


def _base_of(tags):
    return {t.split(':')[0] for t in tags}


def _first_gloss(text):
    """取第一段中文释义（用于关键词规则）：去掉词性标记与括号注释后取首个词。"""
    s = re.sub(r'\[[^\]]*\]', ' ', text or '')
    s = _TAG_RE.sub(' ', s)
    s = re.sub(r'^[\s,，;；、.。:：-]+', '', s)
    return s[:6]


def _table_tags(low):
    out = set()
    if low in LINKING:
        out |= {'v', 'v:link'}
    if low in MODAL:
        out |= {'v', 'v:modal'}
    if low in AUX:
        out |= {'v', 'v:aux'}
    if low in CAUSATIVE:
        out |= {'v', 'v:caus'}
    return out


def _is_proper(word, text):
    """专有名词：首字母大写，或词典释义里明确标了 [地名] / [人名]。"""
    if len(word or '') > 1 and word[:1].isupper():
        return True
    return bool(re.search(r'\[(地名|人名)\]', text or ''))


def _countable(word):
    """可数性（弱推断）：词典 exchange 里有复数（s: / 3:）就算"有复数形式"。"""
    key = (word or '').strip().lower()
    if not key:
        return False
    if key not in _EXCH_CACHE:
        val = ''
        try:
            if os.path.exists(db.DICT_DB_PATH):
                conn = sqlite3.connect(db.DICT_DB_PATH)
                row = conn.execute('SELECT exchange FROM dict WHERE word=?', (key,)).fetchone()
                conn.close()
                val = (row[0] or '') if row else ''
        except Exception:
            val = ''
        _EXCH_CACHE[key] = val
    exch = _EXCH_CACHE[key]
    return 's:' in exch or '3:' in exch


def _finish(tags, word, text, source):
    """补齐细分：闭集表、关键词规则、名词子类；返回 (排序后的标签, 来源)。"""
    tags = set(tags)
    tags |= _table_tags((word or '').strip().lower())
    base = _base_of(tags)
    if 'v' in base:
        first = _first_gloss(text)
        if first.startswith(_CAUS_PREFIX):
            tags.add('v:caus')
        if first.startswith(_LINK_PREFIX):
            tags.add('v:link')
    if 'n' in base:
        if _is_proper(word, text):
            tags.add('n:proper')
        if _countable(word):
            tags.add('n:countable')
    order = ['n', 'n:proper', 'n:countable', 'v', 'v:vt', 'v:vi', 'v:link', 'v:modal',
             'v:aux', 'v:caus', 'a', 'ad', 'prep', 'conj', 'pron', 'num', 'art', 'int',
             'aux', 'abbr', 'phr', 'todo']
    return [t for t in order if t in tags], source


def judge(meaning, word=''):
    """五级判定 → (tags, source)：① 书里显式标记 ② 词典按行义项 ③ 关键词 ④ 闭集表 ⑤ 待确认。"""
    ov = override_tags(word)
    if ov:
        return ov, 'user'
    _ensure_word(word)
    book = _subtags_from_text(meaning)
    if book:
        return _finish(book, word, meaning, 'book')
    dt = _POS_CACHE.get((word or '').strip().lower(), set())
    if dt:
        return _finish(dt, word, _DICT_TEXT.get((word or '').strip().lower()) or meaning, 'dict')
    pk = _PACK_POS.get((word or '').strip().lower(), set())
    if pk:
        return _finish(pk, word, meaning, 'pack')
    tbl = _table_tags((word or '').strip().lower())
    if tbl:
        return _finish(tbl, word, meaning, 'table')
    base = _base_of(_subtags_from_text(meaning)) if meaning else set()
    if base:
        return _finish(base, word, meaning, 'rule')
    affix = _affix_tags(word)
    if affix:
        return _finish(affix, word, meaning, 'rule')
    return ['todo'], 'todo'


def _ensure_word(word):
    """单个词懒加载：词典 / 增强包都没查过就先查一次（judge 单独调用也准）。"""
    key = (word or '').strip().lower()
    if not key or key in _POS_CACHE or key in _PACK_POS or key in _PACK_MISS:
        return
    _load_dict_pos([{'word': word, 'meaning': ''}])


_OVERRIDE = None    # word → 手动修正标签（懒加载，判词时不再逐词查库）


def _overrides():
    global _OVERRIDE
    if _OVERRIDE is None:
        _OVERRIDE = {}
        try:
            with db.get_conn() as conn:
                for r in conn.execute('SELECT word, tags FROM word_pos_override'):
                    if r['tags']:
                        _OVERRIDE[r['word']] = r['tags'].split('|')
        except Exception:
            _OVERRIDE = {}
    return _OVERRIDE


def override_tags(word):
    """用户手动改过的判定（只存在程序里，不写回词书）；没有就返回空。"""
    return _overrides().get((word or '').strip().lower()) or []


def set_override(word, tags):
    """写入/清除手动修正（tags 为空 = 清除）。"""
    global _OVERRIDE
    key = (word or '').strip().lower()
    if not key:
        raise RuntimeError('缺少单词')
    with db._lock:
        with db.get_conn() as conn:
            if tags:
                conn.execute('INSERT OR REPLACE INTO word_pos_override(word, tags) VALUES(?,?)',
                             (key, '|'.join(tags)))
            else:
                conn.execute('DELETE FROM word_pos_override WHERE word=?', (key,))
    _OVERRIDE = None
    return list(tags or [])


def fill_book_pos(book_id, only_empty=True):
    """给某本书的词条算一次词性（导入后 / 启动补扫用）；只写程序库，不碰词书文件。"""
    sql = 'SELECT id, word, meaning FROM words WHERE book_id=?'
    if only_empty:
        sql += " AND (pos_tags IS NULL OR pos_tags='')"
    with db.get_conn() as conn:
        rows = [dict(r) for r in conn.execute(sql, (book_id,))]
    if not rows:
        return 0
    _load_dict_pos(rows)
    done = [(r['id'], r['word'], judge(r['meaning'], r['word'])) for r in rows]
    with db._lock:
        with db.get_conn() as conn:
            for wid, word, (tags, source) in done:
                conn.execute('UPDATE words SET pos_tags=?, pos_source=? WHERE id=?',
                             ('|'.join(tags), source, wid))
                key = (word or '').strip().lower()
                if key and source != 'user':
                    conn.execute('INSERT OR REPLACE INTO word_pos_cache(word, tags, source) '
                                 'VALUES(?,?,?)', (key, '|'.join(tags), source))
    return len(done)


def backfill_all():
    """老库补扫：所有还没判过词性的词条（静默失败，不挡启动）。"""
    total = 0
    try:
        stamp = RULE_VERSION + ('|on' if pack_enabled() else '|off')
        if os.path.exists(_PACK_PATH):
            st = os.stat(_PACK_PATH)
            stamp += '|%d-%d' % (st.st_size, int(st.st_mtime))
        pack_changed = db.get_setting('pos_pack_stamp', '') != stamp
        with db.get_conn() as conn:
            ids = [r['id'] for r in conn.execute('SELECT id FROM word_books ORDER BY id')]
            pending = conn.execute(
                "SELECT COUNT(*) c FROM words WHERE pos_tags IS NULL OR pos_tags=''").fetchone()['c']
        if not pending and not pack_changed:
            return 0
        for bid in ids:
            total += fill_book_pos(bid, only_empty=not pack_changed)
        if stamp:
            db.set_setting('pos_pack_stamp', stamp)
    except Exception:
        return total
    return total


def book_summary(book_id):
    """导入体检：这本书的词性判定分布（自带/词典/增强包/规则/待确认）。"""
    with db.get_conn() as conn:
        total = conn.execute('SELECT COUNT(*) c FROM words WHERE book_id=?', (book_id,)).fetchone()['c']
        rows = conn.execute('SELECT pos_source, COUNT(*) c FROM words WHERE book_id=? '
                            'GROUP BY pos_source', (book_id,)).fetchall()
        st = stats(book_id)
    return {
        'total': total,
        'by_source': {r['pos_source'] or 'todo': r['c'] for r in rows},
        'groups': st['items'],
        'multi': st['multi'],
        'todo': (st['items'] and next((i['count'] for i in st['items'] if i['key'] == 'todo'), 0)) or 0,
    }


def todo_words(book_id, limit=500):
    """待确认清单：这部分词判不出来，列给用户改（只落程序，不碰词书）。"""
    with db.get_conn() as conn:
        return [{'word': r['word'], 'meaning': (r['meaning'] or '')[:120],
                 'tags': r['pos_tags'] or '', 'source': r['pos_source'] or ''}
                for r in conn.execute(
                    "SELECT word, meaning, pos_tags, pos_source FROM words "
                    "WHERE book_id=? AND (pos_tags='todo' OR pos_tags='') ORDER BY word LIMIT ?",
                    (book_id, limit))]


def apply_overrides(book_id, items, source='user'):
    """批量写入手动修正：items = [{word, tags:[...]}]，同时刷新该词在本程序里的判定。"""
    done = 0
    for it in items or []:
        word = (it.get('word') or '').strip()
        tags = it.get('tags') or []
        if not word:
            continue
        set_override(word, tags)
        with db._lock:
            with db.get_conn() as conn:
                conn.execute('UPDATE words SET pos_tags=?, pos_source=? WHERE book_id=? AND word=?',
                             ('|'.join(tags), (source if tags else ''), book_id, word))
        done += 1
    return done


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
        _load_pack(rows)
        return
    words = sorted(need)
    try:
        conn = sqlite3.connect(db.DICT_DB_PATH)
        for i in range(0, len(words), 800):
            chunk = words[i:i + 800]
            sql = ('SELECT word, translation, definition FROM dict WHERE word IN (%s)'
                   % ','.join('?' * len(chunk)))
            for word, translation, definition in conn.execute(sql, chunk):
                _POS_CACHE[word] = _subtags_from_text(translation) or _subtags_from_text(definition)
                _DICT_TEXT[word] = (translation or definition or '').strip()
        conn.close()
    except Exception:
        return
    for w in words:
        _POS_CACHE.setdefault(w, set())     # 词典里也没有：记空，下次不再查
    _load_pack(rows)


def _rows(conn, book_id, list_no=None):
    sql = ('SELECT id, list_no, seq, word, phonetic, meaning, collocations, phrases, '
           'synonyms, antonyms, root_words, phrasal_keys, pos_tags, pos_source '
           'FROM words WHERE book_id=?')
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
                         '%d|%d|%d' % (book_id, r['list_no'], r['seq']),
                         r['pos_tags'] or '', r['pos_source'] or ''))
        conn.executemany(
            'INSERT INTO words(book_id, list_no, seq, word, phonetic, meaning, collocations, '
            'phrases, synonyms, antonyms, root_words, phrasal_keys, source_ref, pos_tags, pos_source) '
            'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', data)
    return {'book_id': new_id, 'name': book_name, 'count': len(picked), 'lists': len(counter)}
