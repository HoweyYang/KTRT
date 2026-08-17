import json
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, UploadFile, File, Form, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.staticfiles import StaticFiles as StarletteStaticFiles
from pydantic import BaseModel

from backend import db, ai, tts, importer

db.init_db()

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
            f'用英文为单词「{w["word"]}」造一个自然地道的句子，句子必须包含该单词。'
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
    with db.get_conn() as conn:
        rows = conn.execute(
            'SELECT w.id, w.word, w.phonetic, w.list_no, w.seq, b.name book_name, b.language, '
            's.familiar, s.unfamiliar, s.favorite, s.learned, '
            '(SELECT COUNT(*) FROM sentences x WHERE x.word_id=w.id) sent_count '
            f'FROM words w JOIN word_books b ON b.id=w.book_id '
            f'LEFT JOIN word_status s ON s.word_id=w.id {where} ORDER BY b.id, w.list_no, w.seq',
            params,
        ).fetchall()
    return [dict(r) for r in rows]


@app.get('/api/export')
def export_words(scope: str = Query('unfamiliar')):
    if scope not in ('unfamiliar', 'favorite', 'both'):
        raise HTTPException(400, '未知导出范围')
    if scope == 'favorite':
        where = 'WHERE s.favorite=1'
    elif scope == 'both':
        where = 'WHERE (s.unfamiliar=1 OR s.favorite=1)'
    else:
        where = 'WHERE s.unfamiliar=1'
    with db.get_conn() as conn:
        rows = conn.execute(
            'SELECT w.word, w.phonetic, w.meaning, w.collocations, w.phrases, '
            'w.synonyms, w.antonyms, w.root_words, w.list_no, b.name AS book_name, b.language '
            'FROM words w JOIN word_books b ON b.id=w.book_id '
            f'LEFT JOIN word_status s ON s.word_id=w.id {where} ORDER BY b.id, w.list_no, w.seq',
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
            if book['name'] == 'GRE必背':
                raise HTTPException(400, 'GRE必背 为默认单词书，不可删除')
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
        path = tts.synthesize(text.strip(), lang)
    except Exception as e:
        raise HTTPException(502, f'语音合成失败：{e}')
    return FileResponse(path, media_type='audio/mpeg')


def _get_settings():
    cfg = ai.current_config()
    return {
        'api_key': cfg['api_key'],
        'base_url': cfg['base_url'],
        'model': cfg['model'],
        'vendor': cfg['vendor'],
        'tts_provider': db.get_setting('tts_provider', 'edge-tts'),
        'theme': db.get_setting('theme', 'light'),
    }


class SettingsBody(BaseModel):
    api_key: str = ''
    base_url: str = ''
    model: str = ''
    vendor: str = 'ds'
    tts_provider: str = 'edge-tts'
    theme: str = 'light'


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
    db.set_setting('theme', body.theme.strip() or 'light')
    return _get_settings()


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
