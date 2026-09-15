# -*- coding: utf-8 -*-
# 动词短语库补全：为 3217 条动词短语补中文释义、例句中译、语域与学习价值。
#
# 用法：
#   venv\Scripts\python.exe tools\enrich_phrasal_verbs.py            默认 4 并发、每批 25 条
#   venv\Scripts\python.exe tools\enrich_phrasal_verbs.py --limit 50 先跑一小批看质量
#
# 产物：
#   data/phrasal_verbs_zh.jsonl  逐条结果，断点续跑（重跑自动跳过已完成）
#   data/phrasal_verbs.json      聚合输出（同一短语的多个义项合并为一条）
import argparse
import json
import os
import re
import sqlite3
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'data', 'reference_phrasal_verbs.json')
OUT_JSONL = os.path.join(ROOT, 'data', 'phrasal_verbs_zh.jsonl')
OUT_JSON = os.path.join(ROOT, 'data', 'phrasal_verbs.json')

SYSTEM = (
    '你是英语学习词典编辑，服务中国考生（雅思/GRE/托福）。'
    '我会给你一批英语动词短语的义项（含英文释义与例句）。'
    '请为每个义项给出：'
    'zh = 中文释义（简洁准确，2~14 字，可带括注，禁止直译例句）；'
    'example_zh = 例句的中文翻译（自然、忠实，保持原句的人称与时态）；'
    'register = 语域，只能是「口语」「中性」「正式」「俚语」之一；'
    'level = 学习价值，只能是「高频」「常用」「少见」之一。'
    '只输出 JSON，不要任何解释文字。'
)

_lock = threading.Lock()
_done = 0


def load_config():
    cfg_path = os.path.join(ROOT, 'data', 'config.json')
    cfg = {}
    if os.path.exists(cfg_path):
        try:
            cfg = json.load(open(cfg_path, encoding='utf-8'))
        except Exception:
            cfg = {}
    if not cfg.get('api_key'):
        db_path = os.path.join(ROOT, 'data', 'ktrt.db')
        if os.path.exists(db_path):
            try:
                conn = sqlite3.connect('file:%s?mode=ro' % db_path.replace('\\', '/'), uri=True)
                kv = dict(conn.execute('SELECT key, value FROM settings'))
                cfg = {
                    'api_key': kv.get('api_key', ''),
                    'base_url': kv.get('base_url') or 'https://api.deepseek.com',
                    'model': kv.get('model') or 'deepseek-chat',
                }
            except Exception:
                pass
    if not cfg.get('api_key'):
        raise SystemExit('未找到 API Key（data/config.json 或 data/ktrt.db settings）')
    cfg['base_url'] = (cfg.get('base_url') or 'https://api.deepseek.com').rstrip('/')
    cfg['model'] = cfg.get('model') or 'deepseek-chat'
    return cfg


def build_groups():
    rows = json.load(open(SRC, encoding='utf-8'))
    groups = {}
    for r in rows:
        display = (r.get('verb') or '').strip()
        if not display:
            continue
        key = re.sub(r'\s+', ' ', display.lower())
        g = groups.setdefault(key, {'key': key, 'display': display, 'senses': []})
        en = (r.get('meaning') or '').strip()
        ex = (r.get('example') or '').strip()
        if any(s['en'] == en and s['example'] == ex for s in g['senses']):
            continue
        g['senses'].append({'n': len(g['senses']) + 1, 'en': en, 'example': ex})
    return [groups[k] for k in sorted(groups)]


def call_llm(cfg, chunk, retries=3):
    payload = {
        'batch': [
            {'key': g['key'], 'n': s['n'], 'phrase': g['display'],
             'en': s['en'], 'example': s['example']}
            for g in chunk for s in g['senses']
        ]
    }
    body = json.dumps({
        'model': cfg['model'],
        'messages': [
            {'role': 'system', 'content': SYSTEM},
            {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)},
        ],
        'temperature': 0.2,
        'max_tokens': 4000,
        'response_format': {'type': 'json_object'},
    }).encode()
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                cfg['base_url'] + '/chat/completions',
                data=body,
                headers={'Content-Type': 'application/json',
                         'Authorization': 'Bearer ' + cfg['api_key']},
            )
            with urllib.request.urlopen(req, timeout=180) as r:
                data = json.loads(r.read().decode())
            text = data['choices'][0]['message']['content']
            m = re.search(r'\{.*\}', text, re.S)
            if not m:
                raise ValueError('返回里没有 JSON')
            obj = json.loads(m.group(0))
            items = obj.get('items') or obj.get('batch')
            if not items:
                items = next((v for v in obj.values() if isinstance(v, list)), [])
            if not items:
                raise ValueError('返回里没有条目数组')
            return items
        except Exception as e:
            last = e
            if attempt < retries - 1:
                time.sleep(3 * (attempt + 1))
    raise RuntimeError('调用失败：%s' % last)


def apply_items(chunk, items):
    by_key = {g['key']: g for g in chunk}
    got = 0
    for it in items:
        g = by_key.get(str(it.get('key', '')).strip().lower())
        if not g:
            continue
        n = int(it.get('n') or 0)
        for s in g['senses']:
            if s['n'] == n:
                s['zh'] = (it.get('zh') or '').strip()
                s['example_zh'] = (it.get('example_zh') or '').strip()
                s['register'] = (it.get('register') or '').strip()
                s['level'] = (it.get('level') or '').strip()
                got += 1
    return got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--batch', type=int, default=25, help='每个请求包含的短语条数')
    ap.add_argument('--limit', type=int, default=0, help='只跑前 N 条（试质量用）')
    args = ap.parse_args()

    cfg = load_config()
    print('模型 %s @ %s' % (cfg['model'], cfg['base_url']), flush=True)

    done_keys = set()
    if os.path.exists(OUT_JSONL):
        for line in open(OUT_JSONL, encoding='utf-8'):
            try:
                g = json.loads(line)
                # 只有全部义项都翻好了才算完成，缺的会在下一轮重跑
                if g.get('senses') and all(s.get('zh') for s in g['senses']):
                    done_keys.add(g['key'])
            except Exception:
                continue

    groups = [g for g in build_groups() if g['key'] not in done_keys]
    if args.limit:
        groups = groups[:args.limit]
    total_senses = sum(len(g['senses']) for g in groups)
    print('待处理 %d 条短语 / %d 个义项（已完成 %d 条）' % (len(groups), total_senses, len(done_keys)),
          flush=True)
    if not groups:
        print('没有待处理条目')
        return

    chunks = [groups[i:i + args.batch] for i in range(0, len(groups), args.batch)]
    out = open(OUT_JSONL, 'a', encoding='utf-8')

    def work(chunk):
        global _done
        try:
            items = call_llm(cfg, chunk)
            got = apply_items(chunk, items)
        except Exception as e:
            print('  [跳过] %s…：%s' % (chunk[0]['key'], e), flush=True)
            return
        with _lock:
            for g in chunk:
                out.write(json.dumps(g, ensure_ascii=False) + '\n')
                _done += 1
            out.flush()
            if _done % 100 < args.batch or _done >= len(groups):
                print('  已完成 %d/%d 条短语（本批补全 %d 个义项）'
                      % (_done, len(groups), got), flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        list(ex.map(work, chunks))
    out.close()

    merged = {}
    for line in open(OUT_JSONL, encoding='utf-8'):
        try:
            g = json.loads(line)
        except Exception:
            continue
        merged[g['key']] = g
    data = [merged[k] for k in sorted(merged)]
    json.dump(data, open(OUT_JSON, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    missing = sum(1 for g in data for s in g['senses'] if not s.get('zh'))
    print('完成：%d 条短语写入 %s（未翻译义项 %d 个）' % (len(data), OUT_JSON, missing))


if __name__ == '__main__':
    main()
