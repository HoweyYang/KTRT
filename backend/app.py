import json
import os
import re
import sqlite3
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, UploadFile, File, Form, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.staticfiles import StaticFiles as StarletteStaticFiles
from pydantic import BaseModel

from backend import db, ai, tts, importer

db.init_db()

APP_VERSION = '0.1.3'
GITHUB_REPO = 'HoweyYang/KTRT'
FRONTEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'frontend', 'static')
app = FastAPI(title='KillTimeRecitationTool')
app.add_middleware(
    CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'],
)


class NoCacheStaticFiles(StarletteStaticFiles):
    async def get_response(self, path: str, scope):
        resp = await super().get_response(path, scope)
        resp.headers['Cache-Control'] = 'no-store, must-revalidate'
        return resp


app.mount('/static', NoCacheStaticFiles(directory=FRONTEND), name='static')


def _lists_meta(book_id):
    with db.get_conn() as conn:
        rows = conn.execute(
            'SELECT w.list_no, COUNT(*) total, '
            '(SELECT COUNT(*) FROM word_status s JOIN words w2 ON s.word_id=w2.id '
            ' WHERE w2.book_id=? AND w2.list_no=w.list_no AND s.learned=1) learned '
            'FROM words w WHERE w.book_id=? GROUP BY w.list_no ORDER BY w.list_no',
            (book_id, book_id),
        ).fetchall()
    return [{'list_no': r['list_no'], 'total': r['total'], 'learned': r['learned']} for r in rows]


def _status(conn, word_id):
    row = conn.execute('SELECT * FROM word_status WHERE word_id=?', (word_id,)).fetchone()
    if row is None:
        return {'familiar': 0, 'unfamiliar': 0, 'favorite': 0, 'learned': 0}
    return {k: row[k] for k in ('familiar', 'unfamiliar', 'favorite', 'learned')}


@app.get('/')
def index():
    resp = FileResponse(os.path.join(FRONTEND, 'index.html'))
    resp.headers['Cache-Control'] = 'no-store, must-revalidate'
    return resp


@app.get('/api/bootstrap')
def bootstrap():
    with db.get_conn() as conn:
        books = conn.execute(
            'SELECT b.*, (SELECT COUNT(*) FROM words w WHERE w.book_id=b.id) word_count '
            'FROM word_books b ORDER BY b.id'
        ).fetchall()
    return {
        'books': [dict(r) for r in books],
        'settings': _get_settings(),
        'presets': ai.PRESETS,
    }


@app.get('/api/books/{book_id}/lists')
def book_lists(book_id: int):
    return _lists_meta(book_id)


@app.get('/api/card')
def card(book_id: int = Query(...), list_no: int = Query(1), seq: int = Query(1)):
    with db.get_conn() as conn:
        w = conn.execute(
            'SELECT * FROM words WHERE book_id=? AND list_no=? AND seq=?',
            (book_id, list_no, seq),
        ).fetchone()
        if w is None:
            raise HTTPException(404, '未找到该词')
        status = _status(conn, w['id'])
        sents = conn.execute(
            'SELECT * FROM sentences WHERE word_id=? ORDER BY id', (w['id'],)
        ).fetchall()
        count = conn.execute(
            'SELECT COUNT(*) c FROM words WHERE book_id=? AND list_no=?',
            (book_id, list_no),
        ).fetchone()['c']
        learned = conn.execute(
            'SELECT COUNT(*) c FROM word_status s JOIN words w2 ON s.word_id=w2.id '
            'WHERE w2.book_id=? AND w2.list_no=? AND s.learned=1',
            (book_id, list_no),
        ).fetchone()['c']
    return {
        'word': dict(w),
        'status': status,
        'sentences': [dict(s) for s in sents],
        'progress': {'total': count, 'learned': learned},
    }


class StatusBody(BaseModel):
    word_id: int
    field: str  # learned | familiar | unfamiliar | favorite
    value: bool


@app.post('/api/status')
def set_status(body: StatusBody):
    if body.field not in ('learned', 'familiar', 'unfamiliar', 'favorite'):
        raise HTTPException(400, '未知状态字段')
    with db._lock:
        with db.get_conn() as conn:
            conn.execute(
                'INSERT INTO word_status(word_id, familiar, unfamiliar, favorite, learned, updated_at) '
                'VALUES(?,0,0,0,0,datetime(\'now\',\'localtime\')) '
                'ON CONFLICT(word_id) DO NOTHING',
                (body.word_id,),
            )
            conn.execute(
                f'UPDATE word_status SET {body.field}=?, updated_at=datetime(\'now\',\'localtime\') '
                'WHERE word_id=?',
                (1 if body.value else 0, body.word_id),
            )
            status = _status(conn, body.word_id)
    return {'status': status}


@app.delete('/api/status/{word_id}')
def delete_status(word_id: int):
    with db._lock:
        with db.get_conn() as conn:
            conn.execute('DELETE FROM word_status WHERE word_id=?', (word_id,))
    return {'ok': True}


class ClearBody(BaseModel):
    book_id: int
    list_no: int


@app.post('/api/lists/clear')
def clear_list(body: ClearBody):
    with db._lock:
        with db.get_conn() as conn:
            conn.execute(
                'UPDATE word_status SET learned=0 WHERE word_id IN '
                '(SELECT id FROM words WHERE book_id=? AND list_no=?)',
                (body.book_id, body.list_no),
            )
    return {'ok': True}


class SentenceBody(BaseModel):
    word_id: int
    prompt: str = ''


def _extract_json(text):
    text = re.sub(r'```(?:json)?', '', text).strip()
    a, b = text.find('{'), text.rfind('}')
    if a == -1 or b == -1:
        raise ValueError('AI 未返回 JSON')
    return json.loads(text[a:b + 1])


@app.post('/api/sentences')
def create_sentence(body: SentenceBody):
    with db.get_conn() as conn:
        w = conn.execute('SELECT * FROM words WHERE id=?', (body.word_id,)).fetchone()
        if w is None:
            raise HTTPException(404, '未找到该词')
    prompt = (body.prompt or '').strip()
    messages = [
        {'role': 'system', 'content': '你是英语造句老师。只输出 JSON，不要任何多余文字。'},
        {'role': 'user', 'content': (
            f'用英文为单词「{w["word"]}」造句，规则：'
            '1) 先判断中文提示词是否与该单词语义相关；'
            '2) 若提示词与单词无关，完全忽略提示词，基于该单词随机造一个自然句子；'
            '3) 若提示词相关，按提示词的意思造句，句中可以使用该单词，也可以使用其同根词或不同词性变形'
            f'（如动词变名词、名词变形容词等，示例：abbreviate → abbreviation），只要读者能看出与「{w["word"]}」相关即可；'
            '4) 句子自然地道、长度适中。'
            f'中文提示词：{prompt or "（无）"}。'
            '输出 JSON：{"sentence": "英文句子", "translation": "整句中文翻译"}'
        )},
    ]
    try:
        raw = ai.chat(messages, max_tokens=500, temperature=0.7)
        data = _extract_json(raw)
        sentence = data.get('sentence', '').strip()
        translation = data.get('translation', '').strip()
    except Exception as e:
        raise HTTPException(502, f'AI 生成失败：{e}')
    if not sentence:
        raise HTTPException(502, 'AI 返回了空句子')
    with db._lock:
        with db.get_conn() as conn:
            conn.execute(
                'INSERT INTO sentences(word_id, prompt, sentence, translation, created_at) '
                'VALUES(?,?,?,?,datetime(\'now\',\'localtime\'))',
                (body.word_id, prompt, sentence, translation),
            )
            # 每词最多 3 句，超出删除最旧
            conn.execute(
                'DELETE FROM sentences WHERE id NOT IN '
                '(SELECT id FROM sentences WHERE word_id=? ORDER BY id DESC LIMIT 3) '
                'AND word_id=?',
                (body.word_id, body.word_id),
            )
            sents = conn.execute(
                'SELECT * FROM sentences WHERE word_id=? ORDER BY id', (body.word_id,)
            ).fetchall()
    return {'sentences': [dict(s) for s in sents]}


@app.delete('/api/sentences/{sentence_id}')
def delete_sentence(sentence_id: int):
    with db._lock:
        with db.get_conn() as conn:
            conn.execute('DELETE FROM sentences WHERE id=?', (sentence_id,))
    return {'ok': True}


@app.get('/api/sentences')
def list_sentences(word_id: int = Query(...)):
    with db.get_conn() as conn:
        sents = conn.execute(
            'SELECT * FROM sentences WHERE word_id=? ORDER BY id', (word_id,)
        ).fetchall()
    return [dict(s) for s in sents]


class NoteBody(BaseModel):
    word_id: int
    content: str = ''


class NotesClearBody(BaseModel):
    book_id: int = 0
    list_no: int = 0


@app.get('/api/notes/{word_id}')
def get_note(word_id: int):
    with db.get_conn() as conn:
        row = conn.execute('SELECT content, updated_at FROM notes WHERE word_id=?', (word_id,)).fetchone()
    return {'word_id': word_id, 'content': row['content'] if row else '', 'updated_at': row['updated_at'] if row else ''}


@app.post('/api/notes')
def save_note(body: NoteBody):
    content = (body.content or '').strip()
    with db._lock:
        with db.get_conn() as conn:
            if conn.execute('SELECT 1 FROM words WHERE id=?', (body.word_id,)).fetchone() is None:
                raise HTTPException(404, '未找到该词')
            if content:
                conn.execute(
                    'INSERT INTO notes(word_id, content, updated_at) '
                    'VALUES(?,?,datetime(\'now\',\'localtime\')) '
                    'ON CONFLICT(word_id) DO UPDATE SET content=excluded.content, updated_at=excluded.updated_at',
                    (body.word_id, content),
                )
            else:
                conn.execute('DELETE FROM notes WHERE word_id=?', (body.word_id,))
    return {'ok': True, 'content': content}


@app.delete('/api/notes/{word_id}')
def delete_note(word_id: int):
    with db._lock:
        with db.get_conn() as conn:
            conn.execute('DELETE FROM notes WHERE word_id=?', (word_id,))
    return {'ok': True}


@app.post('/api/notes/clear')
def clear_notes(body: NotesClearBody):
    sql = 'DELETE FROM notes WHERE word_id IN (SELECT w.id FROM words w WHERE 1=1'
    params = []
    if body.book_id:
        sql += ' AND w.book_id=?'
        params.append(body.book_id)
    if body.list_no:
        sql += ' AND w.list_no=?'
        params.append(body.list_no)
    sql += ')'
    with db._lock:
        with db.get_conn() as conn:
            cur = conn.execute(sql, params)
    return {'ok': True, 'cleared': cur.rowcount}


@app.get('/api/manage')
def manage(filter: str = Query('all')):
    where = ''
    params = []
    if filter == 'learned':
        where = 'WHERE s.learned=1'
    elif filter == 'familiar':
        where = 'WHERE s.familiar=1'
    elif filter == 'unfamiliar':
        where = 'WHERE s.unfamiliar=1'
    elif filter == 'favorite':
        where = 'WHERE s.favorite=1'
    elif filter == 'sentences':
        where = 'WHERE (SELECT COUNT(*) FROM sentences x WHERE x.word_id=w.id)>0'
    elif filter == 'notes':
        where = 'WHERE EXISTS(SELECT 1 FROM notes n WHERE n.word_id=w.id)'
    with db.get_conn() as conn:
        rows = conn.execute(
            'SELECT w.id, w.word, w.phonetic, w.list_no, w.seq, b.name book_name, b.language, '
            's.familiar, s.unfamiliar, s.favorite, s.learned, '
            '(SELECT COUNT(*) FROM sentences x WHERE x.word_id=w.id) sent_count, '
            'EXISTS(SELECT 1 FROM notes n WHERE n.word_id=w.id) has_note '
            f'FROM words w JOIN word_books b ON b.id=w.book_id '
            f'LEFT JOIN word_status s ON s.word_id=w.id {where} ORDER BY b.id, w.list_no, w.seq',
            params,
        ).fetchall()
    return [dict(r) for r in rows]


@app.get('/api/export')
def export_words(scope: str = Query('unfamiliar'), book_id: int = Query(None), list_no: int = Query(None)):
    if scope not in ('unfamiliar', 'favorite', 'both'):
        raise HTTPException(400, '未知导出范围')
    conds, params = [], []
    if scope == 'favorite':
        conds.append('s.favorite=1')
    elif scope == 'both':
        conds.append('(s.unfamiliar=1 OR s.favorite=1)')
    else:
        conds.append('s.unfamiliar=1')
    if book_id is not None:
        conds.append('w.book_id=?')
        params.append(book_id)
    if list_no is not None:
        conds.append('w.list_no=?')
        params.append(list_no)
    where = 'WHERE ' + ' AND '.join(conds)
    with db.get_conn() as conn:
        rows = conn.execute(
            'SELECT w.word, w.phonetic, w.meaning, w.collocations, w.phrases, '
            'w.synonyms, w.antonyms, w.root_words, w.list_no, b.name AS book_name, b.language '
            'FROM words w JOIN word_books b ON b.id=w.book_id '
            f'LEFT JOIN word_status s ON s.word_id=w.id {where} ORDER BY b.id, w.list_no, w.seq',
            params,
        ).fetchall()
    if not rows:
        raise HTTPException(404, '没有符合条件可导出的词汇')
    from openpyxl import Workbook
    from datetime import datetime
    wb = Workbook()
    ws = wb.active
    ws.title = '词汇'
    ws.append(['【单词】', '【音标】', '【词性释义】', '【搭配】', '【短语】', '【同义词】', '【反义词】', '【同根词】', '【List】', '【语言】', '【单词书】'])
    for r in rows:
        ws.append([r['word'], r['phonetic'], r['meaning'], r['collocations'], r['phrases'], r['synonyms'], r['antonyms'], r['root_words'], r['list_no'], r['language'], r['book_name']])
    label = {'unfamiliar': '不熟悉', 'favorite': '收藏', 'both': '不熟悉与收藏'}[scope]
    name = f"KTRT_{label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    path = os.path.join(tempfile.gettempdir(), name)
    wb.save(path)
    return FileResponse(path, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', filename=name)


@app.get('/api/export/notes')
def export_notes(book_id: int = Query(None), list_no: int = Query(None)):
    """导出笔记：只含写了笔记的词，Markdown 文件，格式为「词 + 笔记」循环。"""
    conds, params = [], []
    if book_id is not None:
        conds.append('w.book_id=?')
        params.append(book_id)
    if list_no is not None:
        conds.append('w.list_no=?')
        params.append(list_no)
    where = ('WHERE ' + ' AND '.join(conds)) if conds else ''
    with db.get_conn() as conn:
        rows = conn.execute(
            'SELECT w.word, n.content FROM words w '
            'JOIN notes n ON n.word_id=w.id '
            'JOIN word_books b ON b.id=w.book_id '
            f'{where} ORDER BY b.id, w.list_no, w.seq',
            params,
        ).fetchall()
    if not rows:
        raise HTTPException(404, '没有可导出的笔记')
    from datetime import datetime
    parts = []
    for r in rows:
        parts.append('## ' + r['word'] + '\n\n' + (r['content'] or '') + '\n')
    text = '\n'.join(parts)
    name = f"KTRT_笔记_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    path = os.path.join(tempfile.gettempdir(), name)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    return FileResponse(path, media_type='text/markdown', filename=name)


@app.post('/api/import')
async def import_book(
    file: UploadFile = File(...),
    book_name: str = Form(''),
    language: str = Form('英语'),
):
    suffix = os.path.splitext(file.filename or '')[-1] or '.xlsx'
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        path = tmp.name
    try:
        return importer.import_book(path, book_name.strip(), language.strip())
    except Exception as e:
        raise HTTPException(400, str(e))
    finally:
        try:
            os.unlink(path)
        except Exception:
            pass


@app.delete('/api/books/{book_id}')
def delete_book(book_id: int):
    with db._lock:
        with db.get_conn() as conn:
            book = conn.execute('SELECT * FROM word_books WHERE id=?', (book_id,)).fetchone()
            if book is None:
                raise HTTPException(404, '单词书不存在')
            if book['name'] == '外部单词收藏册':
                raise HTTPException(400, '外部单词收藏册 为默认单词书，不可删除')
            conn.execute('DELETE FROM word_books WHERE id=?', (book_id,))
    return {'ok': True, 'deleted': book['name']}


@app.get('/api/dict/{word}')
def lookup(word: str):
    import sqlite3
    if not os.path.exists(db.DICT_DB_PATH):
        return {'available': False, 'message': '离线词典未导入'}
    try:
        conn = sqlite3.connect(db.DICT_DB_PATH)
        row = conn.execute(
            'SELECT * FROM dict WHERE word=? COLLATE NOCASE', (word.lower(),)
        ).fetchone()
        conn.close()
    except Exception:
        return {'available': False, 'message': '词典读取失败'}
    if row is None:
        return {'available': True, 'found': False}
    return {
        'available': True,
        'found': True,
        'word': row[0],
        'phonetic': row[1] or '',
        'definition': row[2] or '',
        'translation': row[3] or '',
        'pos': row[4] or '',
        'exchange': row[5] or '',
        'collins': row[6] or '',
        'oxford': row[7] or '',
        'tag': row[8] or '',
        'bnc': row[9] or '',
        'frq': row[10] or '',
    }


class CustomDictBody(BaseModel):
    word: str = ''


@app.post('/api/custom-dict/lookup')
def custom_dict_lookup(body: CustomDictBody):
    """自定义查词典·速查：离线词典定义 + 词是否在已导入词书 + 是否已收藏。"""
    word = (body.word or '').strip()
    if not word:
        raise HTTPException(400, '请输入单词')
    dict_result = {'found': False, 'phonetic': '', 'translation': '', 'definition': '', 'exchange': ''}
    if os.path.exists(db.DICT_DB_PATH):
        try:
            conn = sqlite3.connect(db.DICT_DB_PATH)
            row = conn.execute('SELECT * FROM dict WHERE word=? COLLATE NOCASE', (word.lower(),)).fetchone()
            conn.close()
            if row:
                dict_result = {
                    'found': True,
                    'phonetic': row[1] or '',
                    'translation': row[3] or '',
                    'definition': row[2] or '',
                    'exchange': row[5] or '',
                }
        except Exception:
            pass
    in_books = []
    favorite = False
    with db.get_conn() as conn:
        for r in conn.execute(
                'SELECT w.id, b.id book_id, b.name FROM words w '
                'JOIN word_books b ON b.id=w.book_id WHERE w.word=? COLLATE NOCASE',
                (word,)):
            st = conn.execute('SELECT favorite FROM word_status WHERE word_id=?', (r['id'],)).fetchone()
            if st and st['favorite']:
                favorite = True
            in_books.append({'book_id': r['book_id'], 'book_name': r['name']})
    return {
        'word': word,
        'dict': dict_result,
        'in_books': in_books,
        'favorite': favorite,
        'in_fav_book': any(b['book_name'] == '外部单词收藏册' for b in in_books),
    }


@app.post('/api/custom-dict/favorite')
def custom_dict_favorite(body: CustomDictBody):
    """自定义查词典·收藏：词在任意已导入词书中则标记为收藏。"""
    word = (body.word or '').strip()
    if not word:
        raise HTTPException(400, '请输入单词')
    with db._lock:
        with db.get_conn() as conn:
            row = conn.execute('SELECT id FROM words WHERE word=? COLLATE NOCASE LIMIT 1', (word,)).fetchone()
            if row is None:
                raise HTTPException(404, '该词不在任何已导入单词书中，请先「添加」')
            conn.execute('INSERT OR IGNORE INTO word_status(word_id) VALUES(?)', (row['id'],))
            conn.execute('UPDATE word_status SET favorite=1 WHERE word_id=?', (row['id'],))
    return {'ok': True}


@app.post('/api/custom-dict/add')
def custom_dict_add(body: CustomDictBody):
    """自定义查词典·添加：词不在任何已导入词书时，AI 生成词条入默认书。"""
    word = (body.word or '').strip()
    if not word or not re.match(r"^[A-Za-z][A-Za-z\-']*$", word):
        raise HTTPException(400, '请输入合法的英文单词')
    with db.get_conn() as conn:
        exists = conn.execute('SELECT 1 FROM words WHERE word=? COLLATE NOCASE LIMIT 1', (word,)).fetchone()
    if exists:
        raise HTTPException(400, '该词已在已导入单词书中，请改用「收藏」')
    prompt = (
        f'为英语单词「{word}」生成词条数据，只输出一个 JSON 对象，不要任何其他文字：'
        '{"phonetic": "国际音标", "meaning": "词性. 中文释义", '
        '"collocations": "两个常见搭配（英文短语，用分号分隔）", '
        '"phrases": "两个常见短语（英文短语，用分号分隔）", '
        '"synonyms": "2-3 个同义词（英文，用分号分隔）", '
        '"antonyms": "1-2 个反义词（英文，用分号分隔）", '
        '"root_words": "2-3 个同根词（英文，用分号分隔）"}。'
        '要求：字段齐全、内容真实准确、不要编造。'
    )
    try:
        raw = ai.chat([{'role': 'user', 'content': prompt}], max_tokens=800, temperature=0.3)
        data = _extract_json(raw)
    except Exception as e:
        raise HTTPException(502, f'AI 生成失败（需联网且已配置 API Key）：{e}')
    phon = str(data.get('phonetic') or '').strip()
    meaning = str(data.get('meaning') or '').strip()
    colloc = str(data.get('collocations') or '').strip()
    phras = str(data.get('phrases') or '').strip()
    syns = str(data.get('synonyms') or '').strip()
    ants = str(data.get('antonyms') or '').strip()
    roots = str(data.get('root_words') or '').strip()
    with db._lock:
        with db.get_conn() as conn:
            book = conn.execute("SELECT id FROM word_books WHERE name='外部单词收藏册'").fetchone()
            if book is None:
                cur = conn.execute("INSERT INTO word_books(name, language, source) VALUES('外部单词收藏册','英语','')")
                book_id = cur.lastrowid
            else:
                book_id = book['id']
            row = conn.execute(
                'SELECT list_no, COUNT(*) c FROM words WHERE book_id=? GROUP BY list_no '
                'ORDER BY list_no DESC LIMIT 1', (book_id,)).fetchone()
            if row and row['c'] >= 50:
                list_no, seq = row['list_no'] + 1, 1
            elif row:
                list_no, seq = row['list_no'], row['c'] + 1
            else:
                list_no, seq = 1, 1
            cur = conn.execute(
                'INSERT INTO words(book_id, list_no, seq, word, phonetic, meaning, collocations, '
                'phrases, synonyms, antonyms, root_words) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (book_id, list_no, seq, word, phon, meaning, colloc, phras, syns, ants, roots),
            )
            conn.execute('INSERT OR IGNORE INTO word_status(word_id) VALUES(?)', (cur.lastrowid,))
    return {'ok': True, 'book_name': '外部单词收藏册', 'list_no': list_no, 'seq': seq}


@app.get('/api/references')
def references(word: str = Query(''), limit: int = Query(10)):
    """动词短语参考素材库；可按当前单词匹配（短语中任意词命中）。"""
    wl = word.strip().lower()
    limit = max(1, min(limit, 50))
    with db.get_conn() as conn:
        if wl:
            rows = conn.execute(
                "SELECT id, phrase, meaning, example, source FROM reference_phrases "
                "WHERE ' ' || lower(phrase) || ' ' LIKE '% ' || lower(?) || ' %' "
                "ORDER BY phrase, id LIMIT ?",
                (wl, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT id, phrase, meaning, example, source FROM reference_phrases '
                'ORDER BY phrase, id LIMIT ?',
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


@app.get('/api/tts')
def read_aloud(text: str = Query(''), lang: str = Query('英语')):
    if not text.strip():
        raise HTTPException(400, '没有可朗读的文本')
    try:
        voice_key = db.get_setting('tts_voice_fr' if lang == '法语' else 'tts_voice_en',
                                   '女声' if lang == '法语' else '美音·男')
        rate = db.get_setting('tts_rate', '0')
        pitch = db.get_setting('tts_pitch', '0')
        volume = db.get_setting('tts_volume', '100')
        path = tts.synthesize(text.strip(), lang, voice_key, rate, pitch, volume)
    except Exception as e:
        raise HTTPException(502, f'语音合成失败：{e}')
    return FileResponse(path, media_type='audio/mpeg', headers={'Cache-Control': 'no-store'})


def _get_settings():
    cfg = ai.current_config()
    return {
        'api_key': cfg['api_key'],
        'base_url': cfg['base_url'],
        'model': cfg['model'],
        'vendor': cfg['vendor'],
        'tts_provider': db.get_setting('tts_provider', 'edge-tts'),
        'tts_voice_en': db.get_setting('tts_voice_en', '美音·男'),
        'tts_voice_fr': db.get_setting('tts_voice_fr', '女声'),
        'tts_rate': db.get_setting('tts_rate', '0'),
        'tts_pitch': db.get_setting('tts_pitch', '0'),
        'tts_volume': db.get_setting('tts_volume', '100'),
        'theme': db.get_setting('theme', 'dark-blue'),
    }


class SettingsBody(BaseModel):
    api_key: str = ''
    base_url: str = ''
    model: str = ''
    vendor: str = 'ds'
    tts_provider: str = 'edge-tts'
    tts_voice_en: str = '美音·男'
    tts_voice_fr: str = '女声'
    tts_rate: str = '0'
    tts_pitch: str = '0'
    tts_volume: str = '100'
    theme: str = 'dark-blue'


@app.get('/api/settings')
def get_settings():
    return _get_settings()


@app.post('/api/settings')
def save_settings(body: SettingsBody):
    db.set_setting('api_key', body.api_key.strip())
    db.set_setting('base_url', body.base_url.strip().rstrip('/'))
    db.set_setting('model', body.model.strip())
    db.set_setting('vendor', body.vendor.strip() or 'ds')
    db.set_setting('tts_provider', body.tts_provider.strip() or 'edge-tts')
    db.set_setting('tts_voice_en', body.tts_voice_en.strip() or '美音·男')
    db.set_setting('tts_voice_fr', body.tts_voice_fr.strip() or '女声')
    db.set_setting('tts_rate', body.tts_rate.strip() or '0')
    db.set_setting('tts_pitch', body.tts_pitch.strip() or '0')
    db.set_setting('tts_volume', body.tts_volume.strip() or '100')
    db.set_setting('theme', body.theme.strip() or 'dark-blue')
    return _get_settings()


@app.get('/api/update/status')
def update_status():
    """检查 GitHub 最新补丁（main 最新 commit）与最新 Release（Atom 订阅源，无 API 限流）。"""
    def feed(url):
        req = urllib.request.Request(url, headers={'User-Agent': 'KTRT/' + APP_VERSION})
        with urllib.request.urlopen(req, timeout=15) as r:
            return ET.fromstring(r.read().decode('utf-8', 'replace'))

    ns = {'a': 'http://www.w3.org/2005/Atom'}

    out = {'ok': True, 'current_version': APP_VERSION, 'patch': None, 'release': None, 'error': ''}
    try:
        root = feed('https://github.com/%s/commits/main.atom' % GITHUB_REPO)
        entries = root.findall('a:entry', ns)
        if entries:
            e = entries[0]
            link = e.find('a:link', ns)
            href = link.get('href', '') if link is not None else ''
            sha = href.rstrip('/').split('/')[-1][:7] if href else ''
            out['patch'] = {
                'sha': sha,
                'message': (e.findtext('a:title', '', ns) or '').strip(),
                'date': e.findtext('a:updated', '', ns),
                'url': href,
            }
    except Exception as e:
        out['error'] += '补丁检查失败：%s' % e
    try:
        root = feed('https://github.com/%s/releases.atom' % GITHUB_REPO)
        entries = root.findall('a:entry', ns)
        if entries:
            e = entries[0]
            link = e.find('a:link', ns)
            out['release'] = {
                'tag_name': (e.findtext('a:title', '', ns) or '').strip(),
                'name': (e.findtext('a:title', '', ns) or '').strip(),
                'published_at': e.findtext('a:updated', '', ns),
                'html_url': link.get('href', '') if link is not None else '',
            }
    except Exception as e:
        out['error'] += ('；' if out['error'] else '') + '版本检查失败：%s' % e
    return out


@app.post('/api/ai/test')
def ai_test():
    try:
        reply = ai.chat([{'role': 'user', 'content': '只回复两个汉字：成功'}], max_tokens=10)
        return {'ok': True, 'reply': reply.strip()}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8000)
