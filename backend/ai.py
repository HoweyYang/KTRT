import json
import os
import urllib.request

from . import db

# 厂商预设（OpenAI 兼容接口；Claude 单独处理）
PRESETS = {
    'ds': {'label': 'DeepSeek', 'base': 'https://api.deepseek.com', 'model': 'deepseek-chat'},
    'db': {'label': '豆包', 'base': 'https://ark.cn-beijing.volces.com/api/v3', 'model': 'doubao-1-5-pro-32k-250115'},
    'gpt': {'label': 'OpenAI GPT', 'base': 'https://api.openai.com/v1', 'model': 'gpt-4o-mini'},
    'qw': {'label': '通义千问', 'base': 'https://dashscope.aliyuncs.com/compatible-mode/v1', 'model': 'qwen-plus'},
    'grok': {'label': 'Grok', 'base': 'https://api.x.ai/v1', 'model': 'grok-3-mini'},
    'gemini': {'label': 'Gemini', 'base': 'https://generativelanguage.googleapis.com/v1beta/openai', 'model': 'gemini-2.0-flash'},
    'claude': {'label': 'Claude', 'base': 'https://api.anthropic.com', 'model': 'claude-sonnet-4-20250514'},
}


def _defaults():
    cfg_path = os.path.join(db.DATA_DIR, 'config.json')
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def current_config():
    vendor = db.get_setting('vendor', 'ds')
    preset = PRESETS.get(vendor, PRESETS['ds'])
    d = _defaults()
    return {
        'vendor': db.get_setting('vendor', d.get('vendor', 'ds')),
        'api_key': db.get_setting('api_key', d.get('api_key', '')),
        'base_url': db.get_setting('base_url', d.get('base_url', preset['base'])).rstrip('/'),
        'model': db.get_setting('model', d.get('model', preset['model'])),
    }


def chat(messages, max_tokens=1024, temperature=0.7):
    """Call the configured AI. messages: list of {role, content}."""
    cfg = current_config()
    if not cfg['api_key']:
        raise RuntimeError('未配置 API Key，请在「设置」中填写')
    if cfg['vendor'] == 'claude':
        return _chat_claude(cfg, messages, max_tokens, temperature)
    return _chat_openai_compat(cfg, messages, max_tokens, temperature)


def _chat_openai_compat(cfg, messages, max_tokens, temperature):
    body = json.dumps({
        'model': cfg['model'],
        'messages': messages,
        'max_tokens': max_tokens,
        'temperature': temperature,
    }).encode()
    req = urllib.request.Request(
        cfg['base_url'] + '/chat/completions',
        data=body,
        headers={'Content-Type': 'application/json',
                 'Authorization': 'Bearer ' + cfg['api_key']},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read().decode())
    return data['choices'][0]['message']['content']


def _chat_claude(cfg, messages, max_tokens, temperature):
    system = '\n'.join(m['content'] for m in messages if m['role'] == 'system')
    user_msgs = [m for m in messages if m['role'] != 'system']
    body = json.dumps({
        'model': cfg['model'],
        'max_tokens': max_tokens,
        'temperature': temperature,
        'system': system or 'You are a helpful English tutor.',
        'messages': user_msgs,
    }).encode()
    req = urllib.request.Request(
        cfg['base_url'] + '/v1/messages',
        data=body,
        headers={'Content-Type': 'application/json',
                 'x-api-key': cfg['api_key'],
                 'anthropic-version': '2023-06-01'},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.loads(r.read().decode())
    return ''.join(b.get('text', '') for b in data.get('content', []))
