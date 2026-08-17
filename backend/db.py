import os
import sqlite3
import threading

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
DB_PATH = os.path.join(DATA_DIR, 'ktrt.db')
DICT_DB_PATH = os.path.join(DATA_DIR, 'dictionary.db')

_lock = threading.Lock()


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    with _lock:
        with get_conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS word_books(
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL UNIQUE,
                  language TEXT NOT NULL DEFAULT '英语',
                  source TEXT DEFAULT '',
                  created_at TEXT DEFAULT (datetime('now','localtime'))
                );
                CREATE TABLE IF NOT EXISTS words(
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  book_id INTEGER NOT NULL REFERENCES word_books(id) ON DELETE CASCADE,
                  list_no INTEGER NOT NULL,
                  seq INTEGER NOT NULL,
                  word TEXT NOT NULL,
                  phonetic TEXT DEFAULT '',
                  meaning TEXT DEFAULT '',
                  collocations TEXT DEFAULT '',
                  phrases TEXT DEFAULT '',
                  synonyms TEXT DEFAULT '',
                  antonyms TEXT DEFAULT '',
                  root_words TEXT DEFAULT '',
                  UNIQUE(book_id, list_no, seq)
                );
                CREATE INDEX IF NOT EXISTS idx_words_book ON words(book_id, list_no, seq);
                CREATE TABLE IF NOT EXISTS word_status(
                  word_id INTEGER PRIMARY KEY REFERENCES words(id) ON DELETE CASCADE,
                  familiar INTEGER NOT NULL DEFAULT 0,
                  unfamiliar INTEGER NOT NULL DEFAULT 0,
                  favorite INTEGER NOT NULL DEFAULT 0,
                  learned INTEGER NOT NULL DEFAULT 0,
                  updated_at TEXT DEFAULT (datetime('now','localtime'))
                );
                CREATE TABLE IF NOT EXISTS sentences(
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  word_id INTEGER NOT NULL REFERENCES words(id) ON DELETE CASCADE,
                  prompt TEXT DEFAULT '',
                  sentence TEXT NOT NULL,
                  translation TEXT DEFAULT '',
                  created_at TEXT DEFAULT (datetime('now','localtime'))
                );
                CREATE TABLE IF NOT EXISTS settings(
                  key TEXT PRIMARY KEY,
                  value TEXT
                );
                CREATE TABLE IF NOT EXISTS reference_phrases(
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  phrase TEXT NOT NULL,
                  meaning TEXT DEFAULT '',
                  example TEXT DEFAULT '',
                  source TEXT DEFAULT '',
                  created_at TEXT DEFAULT (datetime('now','localtime'))
                );
                CREATE INDEX IF NOT EXISTS idx_ref_phrase ON reference_phrases(phrase);
                """
            )


def get_setting(key, default=None):
    with get_conn() as conn:
        row = conn.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    return row['value'] if row else default


def set_setting(key, value):
    with _lock:
        with get_conn() as conn:
            conn.execute(
                'INSERT INTO settings(key,value) VALUES(?,?) '
                'ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                (key, str(value)),
            )
