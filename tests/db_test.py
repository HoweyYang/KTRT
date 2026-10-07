# -*- coding: utf-8 -*-
"""数据层回归测试：重复导入保留个人状态、热补丁原子换入。

在独立临时目录里跑，不碰真实 data 目录：
  venv\\Scripts\\python.exe tests\\db_test.py
"""
import csv
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix='ktrt_db_')
os.environ['KTRT_DATA_DIR'] = TMP          # 必须在导入 backend 之前设好
sys.path.insert(0, ROOT)

from backend import db, importer, updater  # noqa: E402

PASSED = []
FAILED = []


def check(name, cond, extra=''):
    (PASSED if cond else FAILED).append(name)
    print('%s  %s%s' % ('PASS' if cond else 'FAIL', name, ('  -> ' + str(extra)) if extra else ''))


def counts():
    with db.get_conn() as conn:
        return {t: conn.execute('SELECT COUNT(*) c FROM ' + t).fetchone()['c']
                for t in ('words', 'word_status', 'sentences', 'mistakes', 'notes', 'bookmarks')}


def write_csv(path, rows):
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f)
        w.writerow(['word', 'meaning'])
        w.writerows(rows)


def test_reimport_keeps_personal_state():
    """界面承诺：同词书重复导入覆盖词条，但保留已背/收藏等个人状态。"""
    db.init_db()
    path = os.path.join(TMP, 'book.csv')
    write_csv(path, [['alpha', 'n. 甲'], ['beta', 'n. 乙'], ['gamma', 'n. 丙']])
    importer.import_book(path)

    with db.get_conn() as conn:
        ids = [r['id'] for r in conn.execute('SELECT id FROM words ORDER BY id')]
        conn.execute('INSERT INTO word_status(word_id, learned, favorite, unfamiliar) VALUES(?,?,?,?)',
                     (ids[0], 1, 1, 0))
        conn.execute('INSERT INTO sentences(word_id, sentence) VALUES(?,?)', (ids[0], 'a sentence'))
        conn.execute('INSERT INTO mistakes(word_id, book_id, list_no) VALUES(?,?,?)', (ids[0], 1, 1))
        conn.execute('INSERT INTO notes(word_id, content) VALUES(?,?)', (ids[0], 'my note'))

    write_csv(path, [['alpha', 'n. 甲（改）'], ['beta', 'n. 乙'], ['gamma', 'n. 丙']])
    importer.import_book(path)

    after = counts()
    check('重复导入后「已背/收藏」仍在', after['word_status'] == 1, after['word_status'])
    check('重复导入后「造句」仍在', after['sentences'] == 1, after['sentences'])
    check('重复导入后「错题」仍在', after['mistakes'] == 1, after['mistakes'])
    check('重复导入后「逐词笔记」仍在', after['notes'] == 1, after['notes'])
    check('重复导入后词条数量不变', after['words'] == 3, after['words'])

    with db.get_conn() as conn:
        ids_after = [r['id'] for r in conn.execute('SELECT id FROM words ORDER BY id')]
        meaning = conn.execute("SELECT meaning FROM words WHERE word='alpha'").fetchone()['meaning']
        learned = conn.execute('SELECT learned, favorite FROM word_status').fetchone()
    check('重复导入后词条 id 稳定（状态才挂得住）', ids == ids_after, '%s -> %s' % (ids, ids_after))
    check('重复导入确实刷新了释义内容', meaning == 'n. 甲（改）', meaning)
    check('已背/收藏标记没被改写',
          learned is not None and learned['learned'] == 1 and learned['favorite'] == 1,
          dict(learned) if learned else None)


def _make_patch(path, files, broken=None):
    """files: {name: bytes}；broken: 故意写错校验值的文件名。"""
    manifest = {}
    for name, data in files.items():
        manifest[name] = hashlib.sha256(data).hexdigest()
    if broken:
        manifest[broken] = 'deadbeef' * 8
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('patch.json', json.dumps({'files': manifest}))
        for name, data in files.items():
            z.writestr(name, data)


def test_patch_is_atomic():
    """热补丁要么整套生效，要么一点不动；不能留下半成品 overlay。"""
    overlay = updater.overlay_dir(create=True)
    with open(os.path.join(overlay, 'index.html'), 'w', encoding='utf-8') as f:
        f.write('OLD-INDEX')
    with open(os.path.join(overlay, 'app.js'), 'w', encoding='utf-8') as f:
        f.write('OLD-APP')

    bad = os.path.join(TMP, 'bad.zip')
    _make_patch(bad, {'index.html': b'NEW-INDEX', 'app.js': b'NEW-APP'}, broken='app.js')
    raised = ''
    try:
        updater.apply_patch(bad, '9.9.9')
    except Exception as e:
        raised = str(e)
    check('校验失败的补丁会报错', bool(raised), raised)

    with open(os.path.join(overlay, 'index.html'), encoding='utf-8') as f:
        idx = f.read()
    app_js = os.path.join(overlay, 'app.js')
    check('校验失败后旧 index.html 原样保留', idx == 'OLD-INDEX', idx)
    check('校验失败后旧 app.js 未被删掉',
          os.path.exists(app_js) and open(app_js, encoding='utf-8').read() == 'OLD-APP')
    check('校验失败后目录里没有混入新版文件',
          sorted(os.listdir(overlay)) == ['app.js', 'index.html'], sorted(os.listdir(overlay)))

    good = os.path.join(TMP, 'good.zip')
    _make_patch(good, {'index.html': b'NEW-INDEX', 'app.js': b'NEW-APP'})
    n = updater.apply_patch(good, '9.9.10')
    check('正常补丁仍然能装上', n == 2, n)
    with open(os.path.join(overlay, 'index.html'), encoding='utf-8') as f:
        check('正常补丁内容已生效', f.read() == 'NEW-INDEX')
    check('正常补丁留下 patch.json 记录',
          os.path.exists(os.path.join(overlay, 'patch.json')))

    bad_path_zip = os.path.join(TMP, 'evil.zip')
    with zipfile.ZipFile(bad_path_zip, 'w') as z:
        z.writestr('patch.json', json.dumps({'files': {}}))
        z.writestr('../escape.txt', b'x')
        z.writestr('index.html', b'X')
    try:
        updater.apply_patch(bad_path_zip, '9.9.11')
        blocked = False
    except Exception:
        blocked = True
    check('补丁包里的目录穿越仍被拒绝', blocked)

    # 首次打补丁：overlay 目录还不存在时也要能一次装好
    shutil.rmtree(overlay, ignore_errors=True)
    fresh = os.path.join(TMP, 'fresh.zip')
    _make_patch(fresh, {'index.html': b'FIRST-INDEX', 'app.js': b'FIRST-APP'})
    n2 = updater.apply_patch(fresh, '9.9.12')
    check('overlay 不存在时首次补丁能装上', n2 == 2 and os.path.isdir(overlay), n2)
    with open(os.path.join(overlay, 'index.html'), encoding='utf-8') as f:
        check('首次补丁内容正确', f.read() == 'FIRST-INDEX')
    check('首次补丁后没有残留 staging 目录',
          not os.path.exists(overlay + '_staging'), sorted(os.listdir(TMP)))


def test_patch_notification_rules():
    """补丁提示规则：比自己手上的新才提示，装过就不再弹（否则会一直显示可更新）。"""
    real_rel, real_applied, real_ver = updater.latest_release, updater.applied_patch, updater.VERSION

    def fake_rel(version, asset):
        return lambda: {'tag': 'v' + version, 'version': version, 'newer': None,
                        'patch': {'name': asset, 'size': 1, 'url': 'x'}, 'installer': None}

    def applied(version):
        return (lambda: {'version': version}) if version else (lambda: None)

    try:
        updater.latest_release = fake_rel('0.2.0c', 'patch-0.2.0c.zip')
        updater.VERSION = '0.2.0b'
        updater.applied_patch = applied(None)
        check('没装过补丁：提示可更新',
              updater.status(deep=False)['patch']['applicable'] is True)
        updater.applied_patch = applied('0.2.0c')
        check('装过同一补丁：不再提示',
              updater.status(deep=False)['patch']['applicable'] is False)
        updater.applied_patch = applied('0.2.0b')
        check('装的是旧补丁：仍提示',
              updater.status(deep=False)['patch']['applicable'] is True)
        updater.VERSION = '0.2.0c'
        updater.applied_patch = applied(None)
        check('程序已升级到同版本：不再提示',
              updater.status(deep=False)['patch']['applicable'] is False)

        # 补丁名不合规范时不能把更新通道堵死
        updater.VERSION = '0.2.0b'
        updater.latest_release = lambda: {'tag': 'v?', 'version': '', 'newer': None,
                                          'patch': {'name': 'weird.zip', 'size': 1, 'url': 'x'},
                                          'installer': None}
        check('认不出补丁版本时仍允许应用',
              updater.status(deep=False)['patch']['applicable'] is True)
    finally:
        updater.latest_release = real_rel
        updater.applied_patch = real_applied
        updater.VERSION = real_ver

def test_patch_version_source():
    """补丁版本看文件名：Release v0.2.0d 里挂的 patch-0.2.0e.zip 是 0.2.0e。

    用户报的 bug：点了「立即更新」、刷新后提示还在 —— 因为补丁被记成了 Release
    版本（0.2.0d），下次检查发现"补丁 0.2.0e 比已装的 0.2.0d 新"，又提示一次。
    """
    real_assets, real_opener, real_ver = updater._assets, updater._opener, updater.VERSION
    atom = ('<?xml version="1.0" encoding="utf-8"?>'
            '<feed xmlns="http://www.w3.org/2005/Atom"><entry>'
            '<title>KTRT v0.2.0d — 三套纸质主题重做</title>'
            '<link href="https://github.com/HoweyYang/KTRT/releases/tag/v0.2.0d"/>'
            '<updated>2026-09-18T14:04:13Z</updated><content type="html">x</content>'
            '</entry></feed>')

    class FakeResp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class FakeOpener:
        def open(self, req, timeout=10):
            return FakeResp(atom.encode('utf-8'))

    def fake_assets(tag):
        return [{'name': 'KTRTSetup-lite-0.2.0d.exe', 'url': 'u', 'size': 18926149},
                {'name': 'patch-0.2.0d.zip', 'url': 'u', 'size': 1},
                {'name': 'patch-0.2.0e.zip', 'url': 'u', 'size': 1}]

    real_applied = updater.applied_patch
    try:
        updater._assets = fake_assets
        updater._opener = lambda: FakeOpener()
        rel = updater.latest_release()
        check('补丁版本取自文件名（patch-0.2.0e.zip → 0.2.0e）',
              rel['patch']['version'] == '0.2.0e', rel['patch'])
        check('Release 版本仍取 tag', rel['version'] == '0.2.0d')
        check('同一 Release 挂多个补丁时取最新的',
              rel['patch']['name'] == 'patch-0.2.0e.zip', rel['patch']['name'])

        updater.VERSION = '0.2.0d'
        updater.applied_patch = lambda: None
        st = updater.status(deep=False)
        check('没装过：提示可更新，且显示的是补丁自己的版本',
              st['patch']['applicable'] is True and st['patch']['version'] == '0.2.0e')
        updater.applied_patch = lambda: {'version': '0.2.0e', 'files': 12}
        st = updater.status(deep=False)
        check('装过 0.2.0e 之后不再提示「有小更新」', st['patch']['applicable'] is False)
        check('补丁比程序新：overlay 照常生效', st['overlay'] is True)

        updater.VERSION = '0.2.1'
        st = updater.status(deep=False)
        check('程序升到 0.2.1 后，0.2.0e 的补丁不再提示', st['patch']['applicable'] is False)
        check('程序升到 0.2.1 后，旧 overlay 不再顶替内置前端', st['overlay'] is False)
    finally:
        updater._assets = real_assets
        updater._opener = real_opener
        updater.applied_patch = real_applied
        updater.VERSION = real_ver


def test_pos_falls_back_to_dictionary():
    """释义是纯中文（雅思那种"岩浆"）时，词性去离线词典借；词典也没有才算「其他」。"""
    import sqlite3
    from backend import pos as poslib

    conn = sqlite3.connect(os.path.join(TMP, 'dictionary.db'))
    conn.execute('CREATE TABLE IF NOT EXISTS dict (word TEXT PRIMARY KEY, phonetic TEXT, '
                 'definition TEXT, translation TEXT, pos TEXT, exchange TEXT, collins TEXT, '
                 'oxford TEXT, tag TEXT, bnc TEXT, frq TEXT)')
    conn.execute("INSERT OR REPLACE INTO dict(word, translation, definition) "
                 "VALUES('magma', 'n. 岩浆, 糊剂', 'n. molten rock')")
    conn.commit()
    conn.close()

    path = os.path.join(TMP, 'ielts_like.csv')
    write_csv(path, [['magma', '岩浆'], ['zzznotindict', '某种东西']])
    importer.import_book(path)
    with db.get_conn() as conn:
        bid = conn.execute('SELECT id FROM word_books ORDER BY id DESC LIMIT 1').fetchone()['id']

    poslib._POS_CACHE.clear()
    got = {i['key']: i['count'] for i in poslib.stats(bid)['items']}
    check('纯中文释义的词性从离线词典借到（岩浆 → 名词性）', got.get('noun') == 1, got)
    check('词典也查不到才算「待确认」', got.get('todo') == 1, got)


def test_mask_edit_syncs_source_book():
    """蒙版词书与源词书是母子关系：改任意一边，另一边跟着改（DB 与两边 Excel 都跟上）。"""
    import openpyxl
    from backend import app as appmod, pos as poslib

    path = os.path.join(TMP, 'mask_src.csv')
    write_csv(path, [['apple', 'n. 苹果'], ['run', 'v. 跑'], ['banana', 'n. 香蕉']])
    importer.import_book(path)
    with db.get_conn() as conn:
        src = conn.execute('SELECT * FROM word_books ORDER BY id DESC LIMIT 1').fetchone()
        mother = conn.execute("SELECT * FROM words WHERE book_id=? AND word='apple'",
                              (src['id'],)).fetchone()

    built = poslib.build(src['id'], None, ['noun'], '蒙版测试书')
    with db.get_conn() as conn:
        child = conn.execute('SELECT * FROM words WHERE book_id=? AND word=\'apple\'',
                             (built['book_id'],)).fetchone()
    check('蒙版词条记着源书位置（书id|List|序号）',
          (child['source_ref'] or '') == '%d|%d|%d' % (src['id'], mother['list_no'], mother['seq']),
          child['source_ref'])

    appmod.edit_word(child['id'], appmod.EditBody(meaning='n. 苹果（蒙版改的）'))
    with db.get_conn() as conn:
        m2 = conn.execute('SELECT meaning FROM words WHERE id=?', (mother['id'],)).fetchone()['meaning']
    check('改蒙版 → 源词书同一条跟着改', m2 == 'n. 苹果（蒙版改的）', m2)

    appmod.edit_word(mother['id'], appmod.EditBody(meaning='n. 苹果（源书改的）'))
    with db.get_conn() as conn:
        c2 = conn.execute('SELECT meaning FROM words WHERE id=?', (child['id'],)).fetchone()['meaning']
    check('改源词书 → 蒙版同一条跟着改', c2 == 'n. 苹果（源书改的）', c2)

    def row_of(book_id, word):
        with db.get_conn() as conn:
            bk = conn.execute('SELECT * FROM word_books WHERE id=?', (book_id,)).fetchone()
        p = os.path.join(TMP, 'wordbooks', appmod._safe_filename(bk['name']) + '.xlsx')
        if not os.path.exists(p):
            return None
        ws = openpyxl.load_workbook(p).active
        for row in ws.iter_rows(values_only=True):
            cells = [str(v) for v in row if v is not None]
            if word in cells:
                return cells
        return None

    check('源词书的 Excel 回写了改动',
          (row_of(src['id'], 'apple') or ['']) and any('源书改的' in c for c in row_of(src['id'], 'apple')),
          row_of(src['id'], 'apple'))
    check('蒙版词书的 Excel 也回写了改动',
          (row_of(built['book_id'], 'apple') or ['']) and any('源书改的' in c for c in row_of(built['book_id'], 'apple')),
          row_of(built['book_id'], 'apple'))


def test_pos_judge_chain():
    """五级判定：闭集表（become/let/must）、词典 vt/vi、专有名词、生造词 → 待确认。"""
    import sqlite3
    from backend import pos as poslib

    conn = sqlite3.connect(os.path.join(TMP, 'dictionary.db'))
    nl = chr(10)
    conn.execute("INSERT OR REPLACE INTO dict(word, translation, definition, exchange) "
                 "VALUES('run', ?, 'v. move fast', 'p:ran/i:running/s:runs')",
                 ('n. 跑' + nl + 'vi. 跑, 奔跑' + nl + 'vt. 经营, 运转',))
    conn.execute("INSERT OR REPLACE INTO dict(word, translation, definition, exchange) "
                 "VALUES('atlantic', ?, 'n. the ocean', '')", ('n. 大西洋' + nl + 'a. 大西洋的',))
    conn.execute("INSERT OR REPLACE INTO dict(word, translation, definition, exchange) "
                 "VALUES('let', ?, 'v. allow', 'i:letting/p:let/3:lets')",
                 ('vt. 让, 假设' + nl + 'vi. 出租',))
    conn.commit()
    conn.close()
    for cache in (poslib._POS_CACHE, poslib._DICT_TEXT, poslib._EXCH_CACHE):
        cache.clear()
    poslib._load_dict_pos([{'word': 'run', 'meaning': ''}, {'word': 'atlantic', 'meaning': ''},
                           {'word': 'let', 'meaning': ''}])

    def tags_of(word, meaning=''):
        return poslib.judge(meaning, word)[0]

    check('become → 系动词（闭集表）', 'v:link' in tags_of('become'), tags_of('become'))
    check('must → 情态动词（闭集表）', 'v:modal' in tags_of('must'), tags_of('must'))
    check('let → 使役（闭集表）', 'v:caus' in tags_of('let'), tags_of('let'))
    check('run → 及物 + 不及物（词典按行义项）',
          {'v:vt', 'v:vi'} <= set(tags_of('run')), tags_of('run'))
    check('Atlantic → 专有名词', 'n:proper' in tags_of('Atlantic'), tags_of('Atlantic'))
    check('abstruse → 形容词（书里显式标记）', tags_of('abstruse', 'a. 难懂的') == ['a'],
          tags_of('abstruse', 'a. 难懂的'))
    check('生造词 → 待确认', tags_of('zxqv') == ['todo'], tags_of('zxqv'))

    # 增强包（WordNet / Moby）：词典也没有时兜底，并标来源 pack
    refdir = os.path.join(TMP, 'reflib')
    os.makedirs(refdir, exist_ok=True)
    ref = sqlite3.connect(os.path.join(refdir, 'refpos.db'))
    ref.executescript('CREATE TABLE IF NOT EXISTS pos(word TEXT PRIMARY KEY, tags TEXT, source TEXT);'
                      'CREATE TABLE IF NOT EXISTS gloss(word TEXT, pos TEXT, text TEXT, '
                      'PRIMARY KEY(word, pos));')
    ref.execute("INSERT OR REPLACE INTO pos(word, tags, source) VALUES('el nino','n','pack')")
    ref.execute("INSERT OR REPLACE INTO gloss(word, pos, text) "
                "VALUES('el nino','n','the Christ child')")
    ref.commit()
    ref.close()
    poslib._PACK_PATH = os.path.join(refdir, 'refpos.db')
    for cache in (poslib._POS_CACHE, poslib._PACK_POS, poslib._PACK_GLOSS):
        cache.clear()
    poslib._PACK_MISS.clear()
    pack_tags, pack_src = poslib.judge('', 'El Nino')
    check('增强包兜底：El Nino → 名词（来源 pack）',
          'n' in pack_tags and pack_src == 'pack', (pack_tags, pack_src))
    check('增强包给出专有名词标记', 'n:proper' in pack_tags, pack_tags)
    check('增强包能取英文原文释义', poslib.pack_gloss('El Nino').get('n', '').startswith('the Christ'),
          poslib.pack_gloss('El Nino'))


def test_import_fills_pos_tags():
    """导入后词性要落到词条上（卡片与蒙版都读它）。"""
    path = os.path.join(TMP, 'pos_import.csv')
    write_csv(path, [['become', '变成，变得'], ['abstruse', 'adj. 难懂的']])
    importer.import_book(path)
    with db.get_conn() as conn:
        rid = conn.execute('SELECT id FROM word_books ORDER BY id DESC LIMIT 1').fetchone()['id']
        rows = {r['word']: (r['pos_tags'], r['pos_source'])
                for r in conn.execute('SELECT word, pos_tags, pos_source FROM words WHERE book_id=?', (rid,))}
    check('导入即写入 pos_tags（become 系动词）', 'v:link' in rows['become'][0], rows)
    check('导入即写入来源', rows['become'][1] in ('table', 'dict', 'rule', 'book'), rows)
    check('书里显式标记优先（abstruse → a）', rows['abstruse'][0].startswith('a'), rows)


def test_todo_override_is_program_only():
    """待确认清单的修正只落程序：词条判定立刻变，词书文件不动。"""
    from backend import pos as poslib

    path = os.path.join(TMP, 'todo_src.csv')
    write_csv(path, [['zxqv', '某种东西']])
    importer.import_book(path)
    with db.get_conn() as conn:
        bk = conn.execute("SELECT id FROM word_books WHERE name='todo_src'").fetchone()
        bid = bk['id']
        tags = conn.execute('SELECT pos_tags FROM words WHERE book_id=?', (bid,)).fetchone()['pos_tags']
    check('生造词导入后是待确认', tags == 'todo', tags)

    exc = os.path.join(TMP, 'wordbooks', 'todo_src.xlsx')
    before = os.path.getmtime(exc) if os.path.exists(exc) else None
    n = poslib.apply_overrides(bid, [{'word': 'zxqv', 'tags': ['n']}])
    with db.get_conn() as conn:
        after = conn.execute('SELECT pos_tags, pos_source FROM words WHERE book_id=?', (bid,)).fetchone()
        ov = conn.execute("SELECT tags FROM word_pos_override WHERE word='zxqv'").fetchone()
    check('修正写进程序（pos_tags=user）', n == 1 and after['pos_tags'] == 'n',
          (n, dict(after)))
    check('修正同时记进覆盖表', bool(ov) and ov['tags'] == 'n', ov['tags'] if ov else None)
    now = os.path.getmtime(exc) if os.path.exists(exc) else None
    check('词书文件一个字节没动', before == now, (before, now))
    poslib.set_override('zxqv', [])          # 清理，别影响后续用例


def test_lookup_layer():
    """统一检索层：多源合并、来源标注、缺源/坏源不阻断、未命中给建议。"""
    import sqlite3
    from backend import lookup as lk, pos as poslib

    conn = sqlite3.connect(os.path.join(TMP, 'dictionary.db'))
    conn.execute("INSERT OR REPLACE INTO dict(word, translation, definition, exchange) "
                 "VALUES('alleviation', 'n. 减轻, 缓和', 'n. the act of alleviating', 's:alleviations')")
    conn.commit()
    conn.close()
    refdir = os.path.join(TMP, 'reflib')
    os.makedirs(refdir, exist_ok=True)
    with open(os.path.join(refdir, 'refpos.db'), 'wb') as f:
        f.write(b'not a database')          # 故意弄坏：模拟增强包文件损坏
    poslib._PACK_PATH = os.path.join(refdir, 'refpos.db')
    for cache in (poslib._PACK_POS, poslib._PACK_GLOSS):
        cache.clear()
    poslib._PACK_MISS.clear()

    r = lk.lookup('alleviation', depth='full')
    check('统一检索：命中内置词典并标来源', r['found'] and 'ECDICT' in r['sources'], r['sources'])
    check('统一检索：中文释义与英文定义同时给出',
          '减轻' in r['translation'] and 'act of' in r['definition'], (r['translation'], r['definition']))
    check('增强包损坏不影响出结果（也不报错）', r['found'] and not r['errors'], r['errors'])
    r2 = lk.lookup('zzqwx')
    check('未命中：给建议而不是报错', r2['found'] is False and r2['pos'] == ['todo'], r2['pos'])


def test_default_book_rename():
    """旧库的默认收藏册要跟着改名；已经有新名字时不乱动。"""
    with db.get_conn() as conn:
        conn.execute("INSERT INTO word_books(name, language, source) VALUES('外部单词收藏册','英语','')")
        legacy_id = conn.execute("SELECT id FROM word_books WHERE name='外部单词收藏册'").fetchone()['id']
    db.init_db()
    with db.get_conn() as conn:
        names = [r['name'] for r in conn.execute('SELECT name FROM word_books')]
    check('旧名自动改成「自定义单词收藏册」',
          '外部单词收藏册' not in names and '自定义单词收藏册' in names, names)

    # 已经有新名字时，旧的同名行不该被合并掉（用户自己导入过同名书的情况）
    with db.get_conn() as conn:
        conn.execute("INSERT INTO word_books(name, language, source) VALUES('外部单词收藏册','英语','')")
    db.init_db()
    with db.get_conn() as conn:
        names = [r['name'] for r in conn.execute('SELECT name FROM word_books')]
        conn.execute('DELETE FROM word_books WHERE id=?', (legacy_id,))
        conn.execute("DELETE FROM word_books WHERE name='外部单词收藏册'")
    check('已有新名字时旧名行保持原样', '外部单词收藏册' in names, names)


def main():
    try:
        test_reimport_keeps_personal_state()
        test_patch_is_atomic()
        test_patch_notification_rules()
        test_patch_version_source()
        test_mask_edit_syncs_source_book()
        test_pos_falls_back_to_dictionary()
        test_pos_judge_chain()
        test_import_fills_pos_tags()
        test_lookup_layer()
        test_todo_override_is_program_only()
        test_default_book_rename()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print('\n%d 项通过，%d 项失败' % (len(PASSED), len(FAILED)))
    if FAILED:
        print('失败项：' + '；'.join(FAILED))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
