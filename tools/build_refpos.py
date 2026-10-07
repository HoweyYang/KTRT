# -*- coding: utf-8 -*-
"""生成「词性增强包」refpos.db：Moby Part-of-Speech + WordNet（词性 + 英文原文释义）。

用法（项目 venv）：
  venv\\Scripts\\python.exe tools\\build_refpos.py \
      --moby data\\reflib\\_src\\mobypos.txt --wordnet data\\reflib\\_src\\wn\\wordnet \
      --out data\\reflib\\refpos.db

源文件从哪来（本机自取，仓库里不放）：
  WordNet（含英文释义，约 10 MB）：
    https://raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/corpora/wordnet.zip
  Moby Part-of-Speech II（公有领域；Gutenberg 上的文本到 H 就断了，能拿到完整版更好）：
    https://www.gutenberg.org/files/3203/files/mobypos.txt

产物结构：
  pos(word TEXT PRIMARY KEY, tags TEXT, source TEXT)   # tags 形如 n|v:vt|a|ad
  gloss(word TEXT, pos TEXT, text TEXT)                # WordNet 英文释义（每词每词性取第一条，截断 300 字）

许可：Moby Part-of-Speech 为公有领域；WordNet 为 WordNet License（宽松，保留声明）。
"""
import argparse
import lzma
import os
import re
import sqlite3
import sys

# Moby 的码位 → 我们的标签（大小写敏感：N 名词 / V 动词 / A 形容词 / v 副词…）
MOBY = {
    'N': 'n', 'p': 'n', 'h': 'n',
    'V': 'v', 't': 'v:vt', 'i': 'v:vi',
    'A': 'a', 'v': 'ad',
    'C': 'conj', 'P': 'prep', 'I': 'int', 'r': 'pron', 'D': 'art', 'o': 'pron',
}
WN_POS = {'n': 'n', 'v': 'v', 'a': 'a', 's': 'a', 'r': 'ad'}
ORDER = ['n', 'v', 'v:vt', 'v:vi', 'a', 'ad', 'prep', 'conj', 'pron', 'num', 'art', 'int']


def read_moby(path):
    """Moby：每行 word\\CODES。xz 压缩文件自动解压。"""
    if not path or not os.path.exists(path):
        return {}
    opener = lzma.open if path.endswith('.xz') else open
    out = {}
    with opener(path, 'rt', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip()
            if '\\' not in line:
                continue
            word, _, codes = line.partition('\\')
            tags = {MOBY[c] for c in codes if c in MOBY}
            if tags:
                out.setdefault(word.lower(), set()).update(tags)
    return out


def read_wordnet(root):
    """WordNet：index.* 给词元→词性，data.* 给英文释义（每词每词性取第一条）。"""
    pos_map, gloss = {}, {}
    if not root or not os.path.isdir(root):
        return pos_map, gloss
    for fname, tag in (('index.noun', 'n'), ('index.verb', 'v'),
                       ('index.adj', 'a'), ('index.adv', 'ad')):
        p = os.path.join(root, fname)
        if not os.path.exists(p):
            continue
        with open(p, encoding='utf-8', errors='replace') as f:
            for line in f:
                if line.startswith(' ') or not line.strip():
                    continue
                lemma = line.split(' ', 1)[0]
                pos_map.setdefault(lemma.replace('_', ' ').lower(), set()).add(tag)
    for fname in ('data.noun', 'data.verb', 'data.adj', 'data.adv'):
        p = os.path.join(root, fname)
        if not os.path.exists(p):
            continue
        with open(p, encoding='utf-8', errors='replace') as f:
            for line in f:
                if '|' not in line:
                    continue
                left, _, text = line.partition('|')
                fields = left.split()
                if len(fields) < 5:
                    continue
                try:
                    w_cnt = int(fields[3], 16)
                except ValueError:
                    continue
                words = fields[4:4 + w_cnt * 2:2]
                tag = WN_POS.get(fields[2])
                if not tag or not words:
                    continue
                lemma = words[0].replace('_', ' ').lower()
                key = (lemma, tag)
                if key not in gloss:
                    gloss[key] = re.sub(r'\s+', ' ', text).strip()[:300]
    return pos_map, gloss


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--moby', default='')
    ap.add_argument('--wordnet', default='')
    ap.add_argument('--out', default=os.path.join('data', 'reflib', 'refpos.db'))
    args = ap.parse_args()

    words = read_moby(args.moby)
    wn_pos, wn_gloss = read_wordnet(args.wordnet)
    for w, tags in wn_pos.items():
        words.setdefault(w, set()).update(tags)

    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    if os.path.exists(args.out):
        os.remove(args.out)
    conn = sqlite3.connect(args.out)
    conn.executescript('CREATE TABLE pos(word TEXT PRIMARY KEY, tags TEXT, source TEXT);'
                       'CREATE TABLE gloss(word TEXT, pos TEXT, text TEXT, '
                       'PRIMARY KEY(word, pos));')
    conn.executemany('INSERT OR REPLACE INTO pos(word, tags, source) VALUES(?,?,?)',
                     [(w, '|'.join(t for t in ORDER if t in tags), 'pack')
                      for w, tags in words.items()])
    conn.executemany('INSERT OR REPLACE INTO gloss(word, pos, text) VALUES(?,?,?)',
                     [(w, pos, text) for (w, pos), text in wn_gloss.items()])
    conn.commit()
    conn.execute('CREATE INDEX IF NOT EXISTS idx_gloss_word ON gloss(word)')
    conn.commit()
    n_pos = conn.execute('SELECT COUNT(*) FROM pos').fetchone()[0]
    n_gloss = conn.execute('SELECT COUNT(*) FROM gloss').fetchone()[0]
    conn.close()
    size = os.path.getsize(args.out) / 1048576.0
    print('refpos.db: 词性 %d 条 / 英文释义 %d 条 / %.1f MB -> %s' % (n_pos, n_gloss, size, args.out))
    return 0


if __name__ == '__main__':
    sys.exit(main())
