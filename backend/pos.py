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
    ov = _overrides().get(key)          # 手动 / AI 改过的判定优先，蒙版也要跟着变
    if ov:
        groups = {_GROUP_OF[b] for b in _base_of(ov) if b in _GROUP_OF}
        return [k for k in ORDER if k in groups] or ['todo']
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
RULE_VERSION = 'r9'   # 判定规则版本：改了规则就整体重扫一次（和增强包一起做戳）


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
_COUNT_RE = re.compile(r'[\[（(]\s*C\s*[\]）)]')      # n. [C] / (C) / （可数）


def _merge_detail(tags, key):
    """书里只写 v. / n. 这类粗信息时，用词典与增强包里更细的补上（vt / vi / 系动词 / 专有 / 可数）。

    这是"词卡优先显示最底层性质"的关键：原书词库常常只写一个 v.，
    但内置词典和 WordNet 往往知道它是及物还是不及物。
    """
    out = set(tags)
    base = _base_of(out)
    for src in (_POS_CACHE.get(key, set()), _PACK_POS.get(key, set())):
        for t in src:
            if ':' in t and t.split(':', 1)[0] in base:
                out.add(t)
    return out


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


def _pattern_verb_tags(word, extra):
    """从搭配/短语列里推及物性：word + 宾语 → 及物；word + 介词 → 不及物。"""
    w = (word or '').strip()
    text = extra or ''
    if not w or not text:
        return set()
    out = set()
    stem = re.escape(w)
    if re.search(stem + r"\s+(?:sb|sth|one's|the|a|an|it|his|her|their|your)\b", text, re.I):
        out.add('v:vt')
    if re.search(stem + r"\s+(?:to|at|for|with|on|in|of|about|from|into|upon|against)\b", text, re.I):
        out.add('v:vi')
    return out


def _subtags_from_text(text):
    """从文本抽细分标记：vt → v:vt，vi → v:vi，adj → a…（比 base 版多一层）。"""
    out = set()
    src = text or ''
    for m in _TAG_RE.finditer(src):
        # 跳过"关联词"的标注：词书里常见 "destructive 破坏/有害的 destruct v. 毁坏"，
        # 那个 v. 说的是 destruct，不是本条词。判据：标记前面紧挨着另一个英文单词。
        j = m.start() - 1
        while j >= 0 and src[j] in ' \t':
            j -= 1
        if j >= 0 and src[j].isascii() and src[j].isalpha():
            continue
        if j >= 0 and '\u4e00' <= src[j] <= '\u9fff':
            continue          # "…装置. heat热v.变热" 这类：紧贴中文的标记说的是关联词
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
    key_in_sources = ((word or '').strip().lower() in _POS_CACHE
                      or (word or '').strip().lower() in _PACK_POS)
    if 'v' in base:
        first = _first_gloss(text)
        if first.startswith(_CAUS_PREFIX):
            tags.add('v:caus')
        if first.startswith(_LINK_PREFIX):
            tags.add('v:link')
        if re.search(r'[（(]\s*使\s*[）)]', text or ''):     # "（使）穿梭" → 及物兼不及物
            tags |= {'v:vt', 'v:vi'}
    if 'n' in base:
        if _is_proper(word, text):
            tags.add('n:proper')
        elif _countable(word) or _COUNT_RE.search(text or ''):
            tags.add('n:countable')
        elif key_in_sources:
            tags.add('n:uncountable')       # 有词典/增强包依据、又查不到复数形式 → 判不可数
    order = ['n', 'n:proper', 'n:countable', 'n:uncountable', 'v', 'v:vt', 'v:vi', 'v:link', 'v:modal',
             'v:aux', 'v:caus', 'a', 'ad', 'prep', 'conj', 'pron', 'num', 'art', 'int',
             'aux', 'abbr', 'phr', 'todo']
    return [t for t in order if t in tags], source


def judge(meaning, word='', extra=''):
    """五级判定 → (tags, source)：① 书里显式标记 ② 词典按行义项 ③ 关键词 ④ 闭集表 ⑤ 待确认。"""
    ov = override_tags(word)
    if ov:
        return ov, 'user'
    _ensure_word(word)
    book = _subtags_from_text(meaning)
    if book:
        tags, src = _finish(_merge_detail(book, (word or '').strip().lower()), word, meaning, 'book')
        return _add_pattern(tags, word, extra), src
    dt = _POS_CACHE.get((word or '').strip().lower(), set())
    if dt:
        tags, src = _finish(dt, word, _DICT_TEXT.get((word or '').strip().lower()) or meaning, 'dict')
        return _add_pattern(tags, word, extra), src
    pk = _PACK_POS.get((word or '').strip().lower(), set())
    if pk:
        tags, src = _finish(pk, word, meaning, 'pack')
        return _add_pattern(tags, word, extra), src
    tbl = _table_tags((word or '').strip().lower())
    if tbl:
        return _finish(tbl, word, meaning, 'table')
    base = _base_of(_subtags_from_text(meaning)) if meaning else set()
    if base:
        return _finish(base, word, meaning, 'rule')
    affix = _affix_tags(word)
    if affix:
        tags, src = _finish(affix, word, meaning, 'rule')
        return _add_pattern(tags, word, extra), src
    return ['todo'], 'todo'


def _add_pattern(tags, word, extra):
    """动词还没分及物/不及物时，用搭配/短语列再推一把。"""
    tags = list(tags)
    if 'v' in tags and not any(t in ('v:vt', 'v:vi') for t in tags):
        extra_tags = _pattern_verb_tags(word, extra)
        if extra_tags:
            merged = set(tags) | extra_tags
            order = ['n', 'n:proper', 'n:countable', 'n:uncountable', 'v', 'v:vt', 'v:vi',
                     'v:link', 'v:modal', 'v:aux', 'v:caus', 'a', 'ad', 'prep', 'conj',
                     'pron', 'num', 'art', 'int', 'aux', 'abbr', 'phr', 'todo']
            return [t for t in order if t in merged]
    return tags


def _ensure_word(word):
    """单个词懒加载：词典 / 增强包都没查过就先查一次（judge 单独调用也准）。"""
    key = (word or '').strip().lower()
    # 只看词典缓存：增强包的 miss 不能当作"词典已查过"，否则会短路掉细信息
    if not key or key in _POS_CACHE:
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
    sql = 'SELECT id, word, meaning, collocations, phrases FROM words WHERE book_id=?'
    if only_empty:
        sql += " AND (pos_tags IS NULL OR pos_tags='')"
    with db.get_conn() as conn:
        rows = [dict(r) for r in conn.execute(sql, (book_id,))]
    if not rows:
        return 0
    _load_dict_pos(rows)
    done = [(r['id'], r['word'],
             judge(r['meaning'], r['word'], (r['collocations'] or '') + ' ' + (r['phrases'] or '')))
            for r in rows]
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
    coarse_keys = ('v', 'n')      # 只有动词/名词还有更细一层（及物性、可数性）
    with db.get_conn() as conn:
        total = conn.execute('SELECT COUNT(*) c FROM words WHERE book_id=?', (book_id,)).fetchone()['c']
        rows = conn.execute('SELECT pos_source, COUNT(*) c FROM words WHERE book_id=? '
                            'GROUP BY pos_source', (book_id,)).fetchall()
        marks = ','.join('?' * len(coarse_keys))
        coarse = conn.execute(
            'SELECT COUNT(*) c FROM words WHERE book_id=? AND pos_tags IN (%s)' % marks,
            (book_id, *coarse_keys)).fetchone()['c']
        st = stats(book_id)
    return {
        'total': total,
        'by_source': {r['pos_source'] or 'todo': r['c'] for r in rows},
        'groups': st['items'],
        'multi': st['multi'],
        'todo': (st['items'] and next((i['count'] for i in st['items'] if i['key'] == 'todo'), 0)) or 0,
        'coarse': coarse,
    }


def _in_dict(phrase):
    """整条短语在离线词典里是否存在（判断"错行拼出来的假词"用）。"""
    try:
        if not os.path.exists(db.DICT_DB_PATH):
            return False
        conn = sqlite3.connect(db.DICT_DB_PATH)
        row = conn.execute('SELECT 1 FROM dict WHERE word=?', (phrase.strip().lower(),)).fetchone()
        conn.close()
        return bool(row)
    except Exception:
        return False


def _gloss_chars(text):
    """取释义里的中文字（做相似度比对用）。"""
    return {c for c in str(text or '') if '\u4e00' <= c <= '\u9fff'}


def repair_suggestion(word, meaning):
    """疑似被截断/打错的词，去词典里找最像的候选。

    判据（实测很准）：截断词在 ECDICT 里要么查不到、要么 frq=0（无词频）且释义多为
    领域标注（[医]/[法]/[地名]…）；而正确的完整词一定是有词频的常用词。
    再用中文释义重合度确认它俩说的是同一件事。
    """
    w = (word or '').strip().lower()
    if len(w) < 5 or ' ' in w or not os.path.exists(db.DICT_DB_PATH):
        return ''
    mine = _gloss_chars(meaning)
    if len(mine) < 2:          # 释义没有中文就没法比对，别乱猜
        return ''
    cands = []
    try:
        conn = sqlite3.connect(db.DICT_DB_PATH)
        row = conn.execute('SELECT frq FROM dict WHERE word=?', (w,)).fetchone()
        if row and int(row[0] or 0) > 0:
            conn.close()
            return ''                      # 有词频 = 正经词，不做截断推断
        for pattern in (w + '%', w[:4] + '%'):
            for cw, tr, frq in conn.execute(
                    'SELECT word, translation, frq FROM dict WHERE word LIKE ? AND length(word)<=? '
                    'AND CAST(frq AS INTEGER)>0 ORDER BY CAST(frq AS INTEGER) LIMIT 15',
                    (pattern, len(w) + 4)):
                cands.append((cw, tr or ''))
        conn.close()
    except Exception:
        return ''
    best, best_score = '', 0.0
    for cw, tr in cands:
        if cw.lower() == w or ' ' in cw or len(cw) < len(w):
            continue
        other = _gloss_chars(tr)
        if not other:
            continue
        share = len(mine & other) / max(1, len(mine))
        score = share if len(mine & other) >= 2 else 0.0
        if score > best_score:
            best, best_score = cw, score
    return best if best_score >= 0.34 else ''


def suspicious_words(book_id, limit=200):
    """词条体检：找出疑似被扫描/错行弄坏的条目（headword 拼了两个词、释义里混进别的词或音标…）。

    只做判断，不改数据；界面上让用户自己决定修正还是删除。
    """
    out = []
    ph_noise = re.compile(r'[\[/][^\]/]{2,40}[\]/]')          # 释义里混进音标 [fəˈsɪlɪteɪt]
    other_word = re.compile(r'[A-Za-z]{3,}\s?(v|n|a|adj|adv|vt|vi)\.')   # 关联词 + 词性
    with db.get_conn() as conn:
        rows = conn.execute('SELECT id, word, meaning FROM words WHERE book_id=? ORDER BY word',
                            (book_id,)).fetchall()
    for r in rows:
        word = (r['word'] or '').strip()
        mean = (r['meaning'] or '').strip()
        why = ''
        if not word:
            continue
        if re.search(r'[\u4e00-\u9fff]', word) or re.search(r'\d', word):
            why = '单词列混进了中文/数字'
        elif (not word[:1].isupper() and not _in_dict(word) and len(word) >= 5
              and ' ' not in word):
            guess = repair_suggestion(word, mean)
            if guess:
                why = '词典里查不到，疑似被截断/打错（建议：%s）' % guess
                out.append({'id': r['id'], 'word': word, 'meaning': mean[:120],
                            'reason': why, 'suggest': guess})
                if len(out) >= limit:
                    break
                continue
        elif ' ' in word:
            head = word.split()[0].lower()
            if ph_noise.search(mean):
                why = '释义里混进了音标（多半错行）'
            elif other_word.search(mean) and not re.match(r'^(no|in|on|at|of|for|to|with|by|the|a|an)\b', word, re.I):
                why = '释义里出现别的单词+词性（多半错行）'
            elif head and mean.lower().startswith(head) and len(head) > 3:
                why = '释义开头又重复了单词列的第一个词（多半拼接）'
            elif (not re.search(r'\b(sb|sth|doing|to do|one\'s)\b', word, re.I)
                  and not all(t[:1].isupper() for t in word.split() if t[:1].isalpha())
                  and not _in_dict(word)):
                why = '整个短语在离线词典里查不到（多半是错行拼出来的）'
        if why:
            out.append({'id': r['id'], 'word': word, 'meaning': mean[:120], 'reason': why})
            if len(out) >= limit:
                break
    return out


def todo_words(book_id, limit=500):
    """待确认清单：这部分词判不出来，列给用户改（只落程序，不碰词书）。"""
    coarse_keys = ('v', 'n')      # 只判到"动词/名词"、还没细分到及物性/可数性的词
    with db.get_conn() as conn:
        items = [{'word': r['word'], 'meaning': (r['meaning'] or '')[:120],
                  'tags': r['pos_tags'] or '', 'source': r['pos_source'] or '', 'coarse': False}
                 for r in conn.execute(
                     "SELECT word, meaning, pos_tags, pos_source FROM words "
                     "WHERE book_id=? AND (pos_tags='todo' OR pos_tags='') ORDER BY word LIMIT ?",
                     (book_id, limit))]
        # 只判到「动词 / 名词」这一层、还没细分的词也一并列出来（多为词书缺信息或写错）
        marks = ','.join('?' * len(coarse_keys))
        items += [{'word': r['word'], 'meaning': (r['meaning'] or '')[:120],
                   'tags': r['pos_tags'], 'source': r['pos_source'] or '', 'coarse': True}
                  for r in conn.execute(
                      'SELECT word, meaning, pos_tags, pos_source FROM words '
                      'WHERE book_id=? AND pos_tags IN (%s) ORDER BY word LIMIT ?' % marks,
                      (book_id, *coarse_keys, limit))]
    return items


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
                # ECDICT 的换行是字面量 \n（两个字符），先还原成真换行再解析，
                # 否则 "…连续\nvi. 跑" 里的 vi. 会被"前一个字符是字母"挡掉。
                tr = (translation or '').replace('\\n', '\n').replace('\\r', '')
                df = (definition or '').replace('\\n', '\n').replace('\\r', '')
                _POS_CACHE[word] = _subtags_from_text(tr) or _subtags_from_text(df)
                _DICT_TEXT[word] = (tr or df).strip()
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
