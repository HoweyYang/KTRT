# -*- coding: utf-8 -*-
"""把内置动词短语库导成一本词书（Excel），按首字母分 List。

List 编号对应：A=1、B=2 … Z=26，非字母开头归到 List 27。
（导入器只认数字 List，所以字母只能映射成序号。）

用法：venv\\Scripts\\python.exe tools\\make_phrasal_wordbook.py
产物：wordbooks/Phrasal_Verbs_Wordbook.xlsx
"""
import json
import os
import string
import sys

from openpyxl import Workbook

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'data', 'phrasal_verbs.json')
OUT = os.path.join(ROOT, 'wordbooks', 'Phrasal_Verbs_Wordbook.xlsx')
BOOK_NAME = '动词短语库'
HEADERS = ['【单词】', '【音标】', '【词性释义】', '【搭配】', '【短语】',
           '【同义词】', '【反义词】', '【同根词】', '【List】', '【语言】', '【单词书】']


def list_no_for(phrase):
    ch = (phrase or ' ').strip()[:1].lower()
    return ord(ch) - ord('a') + 1 if ch in string.ascii_lowercase else 27


def build_row(entry):
    zh, en, ex = [], [], []
    for s in entry.get('senses') or []:
        meaning = (s.get('zh') or '').strip()
        meta = '·'.join(x for x in ((s.get('register') or '').strip(), (s.get('level') or '').strip()) if x)
        if meaning:
            zh.append(meaning + ('（%s）' % meta if meta else ''))
        if (s.get('en') or '').strip():
            en.append(s['en'].strip())
        if (s.get('example') or '').strip():
            line = s['example'].strip()
            if (s.get('example_zh') or '').strip():
                line += ' ' + s['example_zh'].strip()
            ex.append(line)
    display = (entry.get('display') or entry.get('key') or '').strip()
    return [display, '', 'v. ' + '；'.join(zh) if zh else '',
            '\n'.join(en), '\n'.join(ex), '', '', '',
            list_no_for(display), '英语', BOOK_NAME]


def main():
    entries = json.load(open(SRC, encoding='utf-8'))
    if not isinstance(entries, list):
        raise SystemExit('短语库格式不是列表，脚本需要更新')
    rows = [build_row(e) for e in entries if (e.get('display') or e.get('key'))]
    rows.sort(key=lambda r: (r[8], r[0].lower()))

    wb = Workbook()
    ws = wb.active
    ws.title = '动词短语库'
    ws.append(HEADERS)
    for r in rows:
        ws.append(r)
    ws.freeze_panes = 'A2'
    wb.save(OUT)

    dist = {}
    for r in rows:
        dist[r[8]] = dist.get(r[8], 0) + 1
    print('已生成 %s' % OUT)
    print('共 %d 条，分成 %d 个 List' % (len(rows), len(dist)))
    preview = ', '.join('%s=%d' % (chr(ord('A') + n - 1) if n <= 26 else '其他', c)
                        for n, c in sorted(dist.items())[:8])
    print('前几个 List：' + preview)
    return 0


if __name__ == '__main__':
    sys.exit(main())
