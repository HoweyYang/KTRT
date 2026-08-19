"""初始化默认词书与 ECDICT 词典（幂等）。"""
import csv
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import db
from backend.importer import parse_xlsx


DEFAULT_BOOK = '外部单词收藏册'


def seed_default_book():
    """确保默认「外部单词收藏册」存在（空书也算存在）。"""
    db.init_db()
    with db.get_conn() as conn:
        exists = conn.execute('SELECT id FROM word_books WHERE name=?', (DEFAULT_BOOK,)).fetchone()
        if exists:
            print(DEFAULT_BOOK + ' 已存在，跳过')
            return
        conn.execute('INSERT INTO word_books(name, language, source) VALUES(?,?,?)',
                     (DEFAULT_BOOK, '英语', ''))
    print(DEFAULT_BOOK + ' 已创建（空书）')


def seed_dictionary():
    """把 ECDICT CSV 导入 dictionary.db（可选，用于应用内离线查词）。"""
    csv_path = os.path.join(db.DATA_DIR, 'ecdict.csv')
    if not os.path.exists(csv_path):
        print('未找到 ECDICT CSV，跳过词典导入（仍可查词库内单词）')
        return
    if os.path.exists(db.DICT_DB_PATH):
        print('dictionary.db 已存在，跳过')
        return
    os.makedirs(db.DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(db.DICT_DB_PATH)
    conn.execute(
        'CREATE TABLE IF NOT EXISTS dict('
        'word TEXT PRIMARY KEY, phonetic TEXT, definition TEXT, translation TEXT, '
        'pos TEXT, exchange TEXT, collins TEXT, oxford TEXT, tag TEXT, bnc TEXT, frq TEXT)'
    )
    n = 0
    with open(csv_path, encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                conn.execute(
                    'INSERT OR REPLACE INTO dict(word, phonetic, definition, translation, pos, '
                    'exchange, collins, oxford, tag, bnc, frq) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    (row['word'], row.get('phonetic') or '', row.get('definition') or '',
                     row.get('translation') or '', row.get('pos') or '', row.get('exchange') or '',
                     row.get('collins') or '', row.get('oxford') or '', row.get('tag') or '',
                     row.get('bnc') or '', row.get('frq') or ''),
                )
            except Exception:
                continue
            n += 1
    conn.commit()
    conn.execute('CREATE INDEX IF NOT EXISTS idx_dict_word ON dict(word)')
    conn.commit()
    conn.close()
    print(f'ECDICT 词典导入完成：{n} 词条')


def seed_references():
    """导入动词短语参考素材库（幂等）。"""
    db.init_db()
    path = os.path.join(db.DATA_DIR, 'reference_phrasal_verbs.json')
    if not os.path.exists(path):
        print('未找到参考素材 JSON，跳过')
        return
    with db.get_conn() as conn:
        n = conn.execute('SELECT COUNT(*) c FROM reference_phrases').fetchone()['c']
    if n > 0:
        print('参考素材库已存在，跳过（%d 条）' % n)
        return
    import json
    with open(path, encoding='utf-8') as f:
        rows = json.load(f)
    with db._lock:
        with db.get_conn() as conn:
            conn.executemany(
                'INSERT OR IGNORE INTO reference_phrases(phrase, meaning, example, source) '
                'VALUES(?,?,?,?)',
                [(r.get('verb', ''), r.get('meaning', ''), r.get('example', ''),
                  '附件4. 动词短语词典') for r in rows],
            )
    print(f'参考素材库导入完成：{len(rows)} 条动词短语')


if __name__ == '__main__':
    seed_default_book()
    seed_dictionary()
    seed_references()
