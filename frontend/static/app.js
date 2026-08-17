/* KillTimeRecitationTool frontend */
const state = {
  books: [],
  bookId: null,
  listNo: 1,
  seq: 1,
  lists: [],
  card: null,
  settings: null,
  presets: {},
};

const $ = (id) => document.getElementById(id);

function applyTheme(theme) {
  document.body.dataset.theme = theme || 'light';
}

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || data.error || '请求失败');
  return data;
}

function toast(msg) {
  const el = $('toast');
  el.textContent = msg;
  el.classList.remove('hidden');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add('hidden'), 2600);
}

/* ---------- 视图切换 ---------- */
document.querySelectorAll('.tab').forEach((b) => {
  b.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach((x) => x.classList.remove('active'));
    document.querySelectorAll('.view').forEach((x) => x.classList.remove('active'));
    b.classList.add('active');
    $('view-' + b.dataset.view).classList.add('active');
    if (b.dataset.view === 'manage') {
      refreshBooksUI().then(loadManage);
    } else if (b.dataset.view === 'import') {
      renderBookList();
    }
  });
});

/* ---------- 初始化 ---------- */
async function init() {
  try {
    const b = await api('/api/bootstrap');
    state.books = b.books;
    state.presets = b.presets || {};
    state.settings = b.settings;
    applyTheme(b.settings.theme);
    populateBookSelect();
    populateSettings();
    if (state.books.length) {
      state.bookId = state.books[0].id;
      await loadLists();
    }
  } catch (e) {
    toast('初始化失败：' + e.message);
  }
}

function populateBookSelect() {
  const sel = $('book-select');
  sel.innerHTML = state.books.map((b) => `<option value="${b.id}">${b.name}（${b.language}，${b.word_count}词）</option>`).join('');
  if (state.bookId && state.books.some((b) => b.id === state.bookId)) {
    sel.value = state.bookId;
  }
  sel.onchange = async () => {
    state.bookId = Number(sel.value);
    state.seq = 1;
    await loadLists();
  };
  // 管理页清空进度用
  const cs = $('clear-book');
  cs.innerHTML = state.books.map((b) => `<option value="${b.id}">${b.name}</option>`).join('');
  cs.onchange = refreshClearList;
  refreshClearList();
}

async function refreshClearList() {
  const cs = $('clear-book');
  if (!cs.value) {
    $('clear-list').innerHTML = '<option value="">先导入单词书</option>';
    return;
  }
  $('clear-list').innerHTML = '<option value="">加载中…</option>';
  try {
    const meta = await api(`/api/books/${cs.value}/lists`);
    $('clear-list').innerHTML = meta.map((l) => `<option value="${l.list_no}">List ${l.list_no}</option>`).join('');
  } catch (e) {
    $('clear-list').innerHTML = '<option value="">加载失败</option>';
  }
}

async function refreshBooksUI() {
  const b = await api('/api/bootstrap');
  state.books = b.books;
  state.presets = b.presets || {};
  populateBookSelect();
  renderBookList();
}

async function loadLists() {
  const meta = await api(`/api/books/${state.bookId}/lists`);
  state.lists = meta;
  const sel = $('list-select');
  sel.innerHTML = meta.map((l) => `<option value="${l.list_no}">Word List ${l.list_no}</option>`).join('');
  sel.onchange = () => {
    state.listNo = Number(sel.value);
    state.seq = 1;
    loadCard();
  };
  state.listNo = meta.length ? meta[0].list_no : 1;
  await loadCard();
}

async function loadCard() {
  if (!state.bookId) return;
  try {
    state.card = await api(`/api/card?book_id=${state.bookId}&list_no=${state.listNo}&seq=${state.seq}`);
    renderCard();
    $('sentence-prompt').value = '';
    $('dict-box').classList.add('hidden');
  } catch (e) {
    toast(e.message);
  }
}

function bookLang() {
  const b = state.books.find((x) => x.id === state.bookId);
  return b ? b.language : '英语';
}

function renderCard() {
  const c = state.card;
  if (!c) return;
  $('word').textContent = c.word.word;
  $('phonetic').textContent = c.word.phonetic ? '/' + c.word.phonetic.replace(/\//g, '') + '/' : '';
  const fields = [
    ['词性释义', c.word.meaning],
    ['搭配', c.word.collocations],
    ['短语', c.word.phrases],
    ['同义词', c.word.synonyms],
    ['反义词', c.word.antonyms],
    ['同根词', c.word.root_words],
  ];
  $('fields').innerHTML = fields
    .filter(([, v]) => v)
    .map(([k, v]) => `
      <div class="field">
        <span class="label">${k}</span>
        <span class="value">${escapeHtml(v)}</span>
        ${k === '词性释义' ? '' : `<button class="icon-btn" data-tts="${escapeAttr(k + '：' + v)}" title="朗读">🔊</button>`}
      </div>`)
    .join('');
  document.querySelectorAll('[data-tts]').forEach((b) => {
    b.addEventListener('click', () => speak(b.dataset.tts));
  });
  const p = c.progress;
  $('progress-fill').style.width = p.total ? (p.learned / p.total * 100) + '%' : '0%';
  $('progress-text').textContent = `已背 ${p.learned}/${p.total}`;
  $('pos-text').textContent = `${c.word.seq} / ${p.total}`;
  renderStatus(c.status);
  renderSentences(c.sentences);
  loadReferences(c.word.word);
}

async function loadReferences(word) {
  const box = $('ref-section');
  const list = $('ref-list');
  try {
    const hits = await api('/api/references?word=' + encodeURIComponent(word) + '&limit=8');
    if (!hits.length) {
      box.classList.add('hidden');
      return;
    }
    list.innerHTML = hits.map((r) => `
      <div class="ref-item">
        <div class="ref-top">
          <b>${escapeHtml(r.phrase)}</b>
          <span class="ref-mean">${escapeHtml(r.meaning)}</span>
          <button class="icon-btn" data-ref-tts="${escapeAttr(r.phrase + '. ' + r.example)}" title="朗读">🔊</button>
        </div>
        <div class="ref-ex">${escapeHtml(r.example)}</div>
      </div>`).join('');
    box.classList.remove('hidden');
    list.querySelectorAll('[data-ref-tts]').forEach((b) => {
      b.addEventListener('click', () => speak(b.dataset.refTts));
    });
  } catch (e) {
    box.classList.add('hidden');
  }
}

function renderStatus(s) {
  $('btn-learn').classList.toggle('active', !!s.learned);
  $('btn-familiar').classList.toggle('active', !!s.familiar);
  $('btn-unfamiliar').classList.toggle('active', !!s.unfamiliar);
  $('btn-favorite').classList.toggle('active-fav', !!s.favorite);
  $('btn-learn').textContent = s.learned ? '✔ 已背' : '✔ 背（计入进度）';
}

function escapeHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function escapeAttr(s) {
  return escapeHtml(s).replace(/"/g, '&quot;');
}

/* ---------- 状态操作 ---------- */
async function setStatus(field, value) {
  try {
    const r = await api('/api/status', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ word_id: state.card.word.id, field, value }),
    });
    state.card.status = r.status;
    renderStatus(r.status);
  } catch (e) {
    toast(e.message);
  }
}

$('btn-learn').addEventListener('click', async () => {
  const s = state.card.status;
  if (!s.learned) {
    await setStatus('learned', true);
    go(1);
  } else {
    await setStatus('learned', false);
  }
});
$('btn-familiar').addEventListener('click', () => setStatus('familiar', !state.card.status.familiar));
$('btn-unfamiliar').addEventListener('click', () => setStatus('unfamiliar', !state.card.status.unfamiliar));
$('btn-favorite').addEventListener('click', () => setStatus('favorite', !state.card.status.favorite));

function go(delta) {
  const total = state.card.progress.total;
  let n = state.seq + delta;
  if (n < 1) n = 1;
  if (n > total) n = total;
  state.seq = n;
  loadCard();
}
$('btn-next').addEventListener('click', () => go(1));
$('btn-prev').addEventListener('click', () => go(-1));
document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  if (e.key === 'ArrowRight') go(1);
  if (e.key === 'ArrowLeft') go(-1);
});

/* ---------- 造句 ---------- */
function highlightWord(sentence, word) {
  const base = word.replace(/[()].*/, '').trim();
  const forms = [word, base];
  const lower = sentence.toLowerCase();
  let target = forms.find((f) => f && lower.includes(f.toLowerCase()));
  if (!target) {
    const suffixes = ['s', 'es', 'ed', 'd', 'ing', 'ies'];
    for (const s of suffixes) {
      const cand = base + s;
      if (cand && lower.includes(cand.toLowerCase())) { target = cand; break; }
    }
  }
  if (!target) return escapeHtml(sentence);
  const re = new RegExp('(' + target.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'ig');
  return escapeHtml(sentence).replace(new RegExp(re.source, 'ig'), '<mark>$1</mark>');
}

function renderSentences(list) {
  if (!list.length) {
    $('sentence-list').innerHTML = '<p class="muted" style="color:var(--muted);font-size:13px">还没有造句，试一个吧。</p>';
    return;
  }
  $('sentence-list').innerHTML = list.map((s) => `
    <div class="sentence-item">
      <button class="del" data-del="${s.id}">删除</button>
      <div class="en">${highlightWord(s.sentence, state.card.word.word)}</div>
      <div class="zh">${escapeHtml(s.translation || '')}</div>
      <div class="meta">${escapeHtml(s.prompt || '')} · ${s.created_at || ''}</div>
    </div>`).join('');
  document.querySelectorAll('[data-del]').forEach((b) => {
    b.addEventListener('click', async () => {
      await api('/api/sentences/' + b.dataset.del, { method: 'DELETE' });
      loadCard();
    });
  });
}

$('btn-make-sentence').addEventListener('click', async () => {
  const prompt = $('sentence-prompt').value;
  const btn = $('btn-make-sentence');
  btn.disabled = true;
  btn.textContent = '生成中…';
  try {
    const r = await api('/api/sentences', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ word_id: state.card.word.id, prompt }),
    });
    state.card.sentences = r.sentences;
    renderSentences(r.sentences);
    $('sentence-prompt').value = '';
    toast('造句已保存');
  } catch (e) {
    toast('造句失败：' + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '生成造句';
  }
});

/* ---------- 查词 ---------- */
$('btn-dict').addEventListener('click', async () => {
  const box = $('dict-box');
  box.classList.remove('hidden');
  box.textContent = '查询中…';
  try {
    const d = await api('/api/dict/' + encodeURIComponent(state.card.word.word));
    if (!d.available) { box.textContent = d.message; return; }
    if (!d.found) { box.textContent = '词典中未找到该词（可尝试在设置中导入 ECDICT 全库）。'; return; }
    box.innerHTML = escapeHtml(
      `${d.word}${d.phonetic ? ' [' + d.phonetic + ']' : ''}\n` +
      (d.translation ? `释义：${d.translation.replace(/;/g, '；')}` : '') +
      (d.definition ? `\n定义：${d.definition}` : '') +
      (d.exchange ? `\n词形变化：${d.exchange}` : '')
    );
  } catch (e) {
    box.textContent = '查询失败：' + e.message;
  }
});

/* ---------- 朗读 ---------- */
function speak(text) {
  const lang = bookLang();
  if (state.settings && state.settings.tts_provider === 'browser') {
    const u = new SpeechSynthesisUtterance(text);
    u.lang = lang === '法语' ? 'fr-FR' : 'en-US';
    speechSynthesis.cancel();
    speechSynthesis.speak(u);
    return;
  }
  const a = new Audio('/api/tts?text=' + encodeURIComponent(text) + '&lang=' + encodeURIComponent(lang));
  a.play().catch(() => toast('语音合成失败（需联网）'));
}
$('btn-word-tts').addEventListener('click', () => {
  const w = state.card.word;
  speak(`${w.word}. ${w.phonetic || ''}`);
});

/* ---------- 管理页 ---------- */
async function loadManage() {
  const filter = $('m-filter').value;
  const term = ($('m-search').value || '').trim().toLowerCase();
  const rows = await api('/api/manage?filter=' + filter);
  const filtered = rows.filter((r) =>
    !term || r.word.toLowerCase().includes(term) || (r.phonetic || '').toLowerCase().includes(term)
  );
  renderManage(filtered);
}

function renderManage(rows) {
  const box = $('manage-list');
  if (!rows.length) {
    box.innerHTML = '<p style="color:var(--muted);text-align:center;padding:24px">暂无记录</p>';
    return;
  }
  const byBook = new Map();
  for (const r of rows) {
    if (!byBook.has(r.book_name)) byBook.set(r.book_name, new Map());
    const byList = byBook.get(r.book_name);
    if (!byList.has(r.list_no)) byList.set(r.list_no, []);
    byList.get(r.list_no).push(r);
  }
  let html = '';
  for (const [book, byList] of byBook) {
    html += `<div class="book-group"><h3>${escapeHtml(book)}</h3></div>`;
    const listNos = [...byList.keys()].sort((a, b) => a - b);
    for (const ln of listNos) {
      const listRows = byList.get(ln);
      html += `<details class="list-group" open>
        <summary>Word List ${ln}<span class="cnt">（${listRows.length} 词）</span></summary>
        <table><thead><tr>
          <th>序号</th><th>单词</th><th>音标</th><th>状态</th><th>句子</th><th>操作</th>
        </tr></thead><tbody>`;
      for (const r of listRows) {
        const tags = [];
        if (r.familiar) tags.push('<span class="tag on">熟悉</span>');
        if (r.unfamiliar) tags.push('<span class="tag off">不熟悉</span>');
        if (r.favorite) tags.push('<span class="tag fav">收藏</span>');
        if (r.learned) tags.push('<span class="tag learn">已背</span>');
        if (!tags.length) tags.push('<span class="tag none">无</span>');
        html += `<tr data-wid="${r.id}">
          <td>${r.seq}</td>
          <td><b>${escapeHtml(r.word)}</b></td>
          <td>${escapeHtml(r.phonetic || '')}</td>
          <td>${tags.join('')}</td>
          <td>${r.sent_count}${r.sent_count ? ` <a href="#" data-sees="${r.id}">查看</a>` : ''}</td>
          <td><button class="btn danger" data-delstatus="${r.id}">删除记录</button></td>
        </tr>
        <tr class="sent-row hidden" data-sentrow="${r.id}"><td colspan="6" id="sent-${r.id}"></td></tr>`;
      }
      html += '</tbody></table></details>';
    }
  }
  box.innerHTML = html;
  box.querySelectorAll('[data-delstatus]').forEach((b) => {
    b.addEventListener('click', async () => {
      if (!confirm('确定删除该单词的全部状态记录？（不影响收藏的句子）')) return;
      await api('/api/status/' + b.dataset.delstatus, { method: 'DELETE' });
      loadManage();
    });
  });
  box.querySelectorAll('[data-sees]').forEach((a) => {
    a.addEventListener('click', async (e) => {
      e.preventDefault();
      const id = a.dataset.sees;
      const row = document.querySelector(`[data-sentrow="${id}"]`);
      row.classList.toggle('hidden');
      const cell = document.getElementById('sent-' + id);
      if (row.classList.contains('hidden')) return;
      const sents = await api('/api/sentences?word_id=' + id).catch(() => null);
      cell.innerHTML = sents && sents.length
        ? sents.map((s) => `<div class="sentence-line">${escapeHtml(s.sentence)}<button class="btn danger" data-sdel="${s.id}">删除</button></div>`).join('')
        : '（句子加载失败）';
      cell.querySelectorAll('[data-sdel]').forEach((b) => {
        b.addEventListener('click', async () => {
          await api('/api/sentences/' + b.dataset.sdel, { method: 'DELETE' });
          loadManage();
        });
      });
    });
  });
}

let _searchTimer;
$('m-search').addEventListener('input', () => {
  clearTimeout(_searchTimer);
  _searchTimer = setTimeout(loadManage, 200);
});
$('m-filter').addEventListener('change', loadManage);

function renderBookList() {
  const box = $('book-list');
  if (!box) return;
  if (!state.books.length) {
    box.innerHTML = '<p style="color:var(--muted)">暂无单词书，先导入一本吧。</p>';
    return;
  }
  box.innerHTML = state.books.map((b) => `
    <div class="book-row">
      <span><b>${escapeHtml(b.name)}</b>（${b.language}，${b.word_count} 词）</span>
      ${b.name === 'GRE必背'
        ? '<span class="tag learn">默认</span>'
        : `<button class="btn danger" data-delbook="${b.id}" data-name="${escapeAttr(b.name)}">删除</button>`}
    </div>`).join('');
  box.querySelectorAll('[data-delbook]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const name = btn.dataset.name;
      const id = Number(btn.dataset.delbook);
      if (!confirm(`确定删除单词书「${name}」？该书的进度、收藏与造句将一并删除，且不可恢复。`)) return;
      try {
        await api('/api/books/' + id, { method: 'DELETE' });
        toast('已删除 ' + name);
        await refreshBooksUI();
        if (state.bookId === id) {
          state.bookId = state.books.length ? state.books[0].id : null;
          state.seq = 1;
          if (state.bookId) await loadLists();
        } else if (state.bookId && state.books.some((x) => x.id === state.bookId)) {
          await loadLists();
        }
      } catch (e) {
        toast('删除失败：' + e.message);
      }
    });
  });
}

$('btn-refresh-manage').addEventListener('click', loadManage);
$('btn-clear-list').addEventListener('click', async () => {
  const bookId = Number($('clear-book').value);
  const listNo = Number($('clear-list').value);
  if (!bookId || !listNo) { toast('请选择单词书和 List'); return; }
  if (!confirm('确定清空该 List 的「已背」进度？（收藏/熟悉/不熟悉保留）')) return;
  await api('/api/lists/clear', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ book_id: bookId, list_no: listNo }),
  });
  toast('已清空');
  if (bookId === state.bookId) { state.lists = await api(`/api/books/${state.bookId}/lists`); loadCard(); }
});

/* ---------- 导入页 ---------- */
$('btn-import').addEventListener('click', async () => {
  const f = $('import-file').files[0];
  if (!f) { toast('请先选择 Excel 文件'); return; }
  const fd = new FormData();
  fd.append('file', f);
  fd.append('book_name', $('import-bookname').value);
  fd.append('language', $('import-language').value);
  $('btn-import').disabled = true;
  try {
    const r = await api('/api/import', { method: 'POST', body: fd });
    $('import-result').innerHTML = `<p class="ok">导入成功：${r.book_name}（${r.language}），${r.rows} 词</p>`;
    await refreshBooksUI();
    toast('导入成功');
  } catch (e) {
    $('import-result').innerHTML = `<p class="err">导入失败：${e.message}</p>`;
  } finally {
    $('btn-import').disabled = false;
  }
});

/* ---------- 设置页 ---------- */
function populateSettings() {
  const sel = $('s-vendor');
  sel.innerHTML = Object.entries(state.presets).map(([k, v]) =>
    `<option value="${k}">${v.label}</option>`).join('');
  const s = state.settings || {};
  sel.value = s.vendor || 'ds';
  $('s-base').value = s.base_url || '';
  $('s-model').value = s.model || '';
  $('s-key').value = s.api_key || '';
  $('s-tts').value = s.tts_provider || 'edge-tts';
  $('s-theme').value = s.theme || 'light';
  sel.onchange = () => {
    const p = state.presets[sel.value];
    if (p) {
      $('s-base').value = p.base;
      $('s-model').value = p.model;
    }
  };
  $('s-theme').onchange = () => applyTheme($('s-theme').value);
}

$('btn-save-settings').addEventListener('click', async () => {
  try {
    state.settings = await api('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        api_key: $('s-key').value,
        base_url: $('s-base').value,
        model: $('s-model').value,
        vendor: $('s-vendor').value,
        tts_provider: $('s-tts').value,
        theme: $('s-theme').value,
      }),
    });
    $('settings-msg').innerHTML = '<p class="ok">设置已保存</p>';
  } catch (e) {
    $('settings-msg').innerHTML = `<p class="err">${e.message}</p>`;
  }
});

$('btn-test-ai').addEventListener('click', async () => {
  $('settings-msg').innerHTML = '<p class="ok">测试中…</p>';
  const r = await api('/api/ai/test', { method: 'POST' });
  $('settings-msg').innerHTML = r.ok
    ? `<p class="ok">AI 连接成功：${escapeHtml(r.reply)}</p>`
    : `<p class="err">AI 连接失败：${escapeHtml(r.error)}</p>`;
});

/* ---------- 启动 ---------- */
init();
