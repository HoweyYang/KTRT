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
  bookmarks: [],
  storms: [],
};

const $ = (id) => document.getElementById(id);
const SPEAKER_ICON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5 6 9H2v6h4l5 4V5z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M19 5a9 9 0 0 1 0 14"/></svg>';

function applyTheme(theme) {
  document.body.dataset.theme = theme === 'paper' ? 'light' : (theme || 'light');
  syncBrandImage();
}

/* 页面质感：简约 / 纸质 / 赛博朋克 —— 每套质感各带三种配色，标签随质感变化 */
const PAGE_MODES = ['minimal', 'paper', 'cyber'];
const THEME_LABELS = {
  minimal: { light: '浅色', dark: '深色', 'dark-blue': '石墨' },
  paper: { light: '米白纸', dark: '牛皮纸', 'dark-blue': '靛蓝纸' },
  cyber: { light: '霓虹', dark: '酸黄', 'dark-blue': '矩阵' },
};

function currentPageMode() {
  const m = document.body.dataset.page;
  return PAGE_MODES.includes(m) ? m : 'minimal';
}

function applyPageMode(mode) {
  const m = PAGE_MODES.includes(mode) ? mode : (mode === 'paper' ? 'paper' : 'minimal');
  document.body.dataset.page = m;
  syncThemeLabels();
  syncBrandImage();
  return m;
}

function syncThemeLabels() {
  const labels = THEME_LABELS[currentPageMode()] || THEME_LABELS.minimal;
  const slots = { 'theme-light': 'light', 'theme-dark': 'dark', 'theme-blue': 'dark-blue' };
  Object.entries(slots).forEach(([id, key]) => {
    const el = $(id);
    if (el && labels[key]) el.textContent = labels[key];
  });
  const sel = $('s-theme');
  if (sel) {
    Object.entries(slots).forEach(([, key]) => {
      const opt = sel.querySelector(`option[value="${key}"]`);
      if (opt && labels[key]) opt.textContent = labels[key];
    });
  }
}

/* 品牌图：可在 frontend/static/brand/ 放自己的 logo（按配色切换），没有就退回文字字标 */
const BRAND_FILES = {
  'cyber|light': ['brand-neon.svg', 'brand-neon.png'],
  'cyber|dark': ['brand-acid.svg', 'brand-acid.png'],
  'cyber|dark-blue': ['brand-matrix.svg', 'brand-matrix.png'],
  'paper|light': ['brand-paper.svg', 'brand-paper.png'],
  'minimal|light': ['brand-minimal.svg', 'brand-minimal.png'],
};
let brandSeq = 0;

function syncBrandImage() {
  const el = document.getElementById('brand-mark');
  if (!el) return;
  const seq = ++brandSeq;
  const files = BRAND_FILES[currentPageMode() + '|' + (document.body.dataset.theme || 'light')];
  const fail = () => {
    if (seq !== brandSeq) return;
    el.classList.remove('on');
    el.removeAttribute('src');
  };
  if (!files || !files.length) { fail(); return; }
  const tryLoad = (i) => {
    if (seq !== brandSeq) return;
    if (i >= files.length) { fail(); return; }
    const img = new Image();
    img.onload = () => {
      if (seq !== brandSeq) return;
      el.src = img.src;
      el.classList.add('on');
    };
    img.onerror = () => tryLoad(i + 1);   // SVG 没有就试 PNG
    img.src = '/static/brand/' + files[i];
  };
  tryLoad(0);
}

async function api(path, opts = {}) {
  const { timeout = 0, ...rest } = opts;
  const ctrl = timeout ? new AbortController() : null;
  const timer = timeout ? setTimeout(() => ctrl.abort(), timeout) : null;
  let res;
  try {
    res = await fetch(path, { ...rest, signal: ctrl ? ctrl.signal : undefined });
  } catch (e) {
    throw new Error(timeout ? '请求超时，请检查网络后重试' : e.message);
  } finally {
    if (timer) clearTimeout(timer);
  }
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

/* ---------- 功能引导：悬停显示该按钮的作用与效果 ---------- */
const FEATURE_HINTS = {
  'book-select': '选择当前背诵的单词书。',
  'list-select': '选择当前 List；切换后从该 List 第一个词开始。',
  'bookmark-select': '跳转到已留书签的位置（可跨词书，选中即直达）。',
  'btn-learn': '将当前词标记为「已背」并自动进入本 List 的下一个词，进度相应 +1；若当前词已背，点击则取消「已背」，不会自动跳转。',
  'btn-unfamiliar': '切换当前词的「不熟悉」标记：标记后管理页可按此筛选或导出；杀词答题出错也会自动打上该标记。此标记与「已背」「收藏」相互独立。',
  'btn-favorite': '切换当前词的「收藏」标记：仅作状态记录，不影响已背进度；管理页可按收藏筛选或导出。',
  'btn-bookmark': '为当前词所在位置（词书 + List + 序号）创建书签；创建后可用顶部「书签▾」一键跳回，再点此图标则移除。',
  'bookmark-select': '列出全部已建书签并直达对应词；若词书被改动导致位置失效，会提示并自动刷新列表。',
  'btn-prev': '前往本 List 的上一个词；已在本 List 开头则停留（键盘 ←）。',
  'btn-next': '前往本 List 的下一个词；已在本 List 末尾则停留（键盘 →）。',
  'btn-word-tts': '按设置中的朗读方式与音色朗读当前单词：edge-tts 需联网，浏览器语音可离线。',
  'btn-dict': '打开本地 ECDICT 词典，展示当前词释义与词形变化（离线可用）。',
  'btn-edit': '编辑：在卡片内直接修改当前这一条（单词、音标、释义、搭配、短语、同反义词、同根词），保存后同步本地库并回写所属词书 Excel；原文件失效时自动改用本地托管副本。',
  'btn-cd-lookup': '查询输入词：依次做离线词典速查、变形还原为原形、所在词书与收藏判断；词典与词书都未命中时提供拼写建议。',
  'btn-custom-dict': '查询任意单词。流程：离线词典 → 变形还原原形 → 判断原形所在词书/收藏 → 拼写纠错；可按需使用在线词源或 AI 整理（AI 需配置 Key）。',
  'btn-storm-view': '查看或生成当前词的风暴词卡（词源、用法、释义、变形、派生词、同反近义、易混词）；生成需调用 AI 并联网，若尚无词卡会先询问是否生成。',
  'btn-make-sentence': '用当前词造句：先在输入框写一句中文提示词再点击；AI 返回英文句与中文翻译并高亮目标词，保存后进入造句收藏。每词最多 3 句，超出时自动删除最早一条。',
  'btn-note-save': '把当前词笔记写入本地（所见即所得 Markdown）。切换单词前请先保存：未保存的编辑内容不会保留。',
  'chg-mode-word': '记词闯关：以当前 List 为单元，把单词打乱后逐一做“词性释义四选一”。每局乱序；答错自动标为「不熟悉」并即时加入错题本；成绩只保留该 List 的历史最高正确数。',
  'chg-mode-mistake': '错题闯关：从错题本出题，可多选 List 合并成一个题池；答对后由你决定「移出错题本」或保留，避免误清。',
  'chg-book': '选择闯关所用的单词书。',
  'chg-list': '选择以哪个 List 作为本局题源。',
  'chg-mbook': '选择错题所属的单词书。',
  'chg-start-word': '开始记词闯关（List 每局乱序）。',
  'chg-start-mistake': '按已勾选的 List 开始错题闯关。',
  'chg-exit': '退出闯关：本局进度不保留，但已加入错题本的词不受影响。',
  'm-search': '在管理范围内检索单词或音标（不区分大小写、子串匹配）。',
  'm-filter': '按状态筛选：全部 / 不熟悉 / 收藏 / 已背 / 有造句 / 有笔记。',
  'clear-book': '选择要清空进度的单词书。',
  'clear-list': '选择要清空进度的 List。',
  'btn-clear-list': '清空该 List 的「已背」进度；收藏、造句、笔记不受影响（执行前建议先备份数据目录）。',
  'btn-clear-notes': '删除选定范围内全部单词笔记，不可恢复，请谨慎使用。',
  'btn-export-unfamiliar': '导出范围选择「不熟悉」词。',
  'btn-export-favorite': '导出范围选择「收藏」词。',
  'btn-export-both': '导出范围选择「不熟悉 + 收藏」（去重）。',
  'export-book': '限定导出到某本词书（默认全部）。',
  'export-list': '限定导出到某个 List（默认全部）。',
  'btn-export-go': '按当前范围与过滤条件导出 Excel；每行是该词在词库里的完整字段，可直接再导入。',
  'btn-export-notes': '导出所选范围内各词及其 Markdown 笔记（词与笔记循环排列）。',
  'import-bookname': '自定义词书名；留空则使用文件名。',
  'import-language': '声明词书语言，用于决定朗读音色与后续语言处理。',
  'import-file': '选择词库文件：Excel（【】格式）/ CSV / 纯文本均可。',
  'btn-import': '解析并导入所选文件；同词书重复导入会覆盖词条，但保留已背/收藏等个人状态。',
  'btn-test-ai': '向当前配置的 AI 发送一条探针请求，验证 Key 与网络连通；不修改任何数据。',
  'btn-save-settings': '保存本页全部设置（AI、语音、主题与页面质感）。',
  'btn-upd-check': '读取 GitHub 上最新一次发布：有新版本或热补丁时会出现「立即更新」。',
  'btn-upd-apply': '一键更新：新版本走下载安装（会弹一次系统授权框），热补丁直接应用、刷新即生效。',
  'upd-auto': '打开程序时自动检查一次更新；有新版会弹窗提示，不会自动安装。',
  's-theme': '主题色：随页面质感变化——简约=浅色/深色/石墨，纸质=米白纸/牛皮纸/靛蓝纸，赛博=电光/酸黄/矩阵。',
  'page-normal': '页面质感：简约（Apple / OpenAI 风格，素色、克制留白、细边框）。',
  'page-paper': '页面质感：纸质（米白纸 / 牛皮纸 / 靛蓝纸，纸纹 + 纤维 + 边缘阴影，衬线阅读字体）。',
  'page-cyber': '页面质感：科幻（霓虹夜景配色、扫描线、色散标题、DIN 科技字体；三种配色：霓虹夜景 / 酸黄黑 / 矩阵绿）。',
  'theme-light': '配色一号位：简约=浅色，纸质=米白纸，科幻=霓虹夜景（青×品红）。',
  'theme-dark': '配色二号位：简约=深色，纸质=牛皮纸，科幻=酸黄黑。',
  'theme-blue': '配色三号位：简约=石墨，纸质=靛蓝纸，科幻=矩阵（纯绿黑）。',
};

function initFeatureHints() {
  const VIEW_TIPS = {
    study: '一页一词地背：进度、收藏、笔记、书签与风暴都在这页。',
    challenge: '四选一闯关：记词闯关 & 错题闯关，答错自动进错题本。',
    manage: '按 书 → List 管理进度 / 收藏 / 造句 / 笔记，可搜索、筛选、导出。',
    storm: '浏览与生成「风暴词卡」，可搜索已建词卡的单词并导出。',
    import: '导入新词书（Excel / CSV / 纯文本），也可删除词书。',
    settings: '配置 AI Key / 厂商、语音、主题。',
    update: '检查更新：有热补丁直接应用（不用重启），有新版本一键下载安装并自动重开。',
    guide: '操作指南与文档。',
  };
  const tip = document.createElement('div');
  tip.className = 'kttip';
  document.body.appendChild(tip);
  Object.entries(FEATURE_HINTS).forEach(([id, text]) => {
    const el = $(id);
    if (el) el.setAttribute('data-tip', text);
  });
  document.querySelectorAll('.tab').forEach((b) => {
    const t = VIEW_TIPS[b.dataset.view];
    if (t) b.setAttribute('data-tip', t);
  });
  document.querySelectorAll('[data-tip]').forEach((el) => el.removeAttribute('title'));
  let current = null;
  let timer = null;
  function hide() { tip.classList.remove('show'); current = null; }
  function show(el) {
    const text = el.getAttribute('data-tip');
    if (!text) return;
    clearTimeout(timer);
    current = el;
    tip.textContent = text;
    tip.classList.add('show');
    requestAnimationFrame(() => {
      const r = el.getBoundingClientRect();
      const tw = tip.offsetWidth || 200;
      const th = tip.offsetHeight || 40;
      let x = Math.min(Math.max(8, r.left), window.innerWidth - tw - 8);
      let y = r.bottom + 7;
      if (y + th > window.innerHeight - 8) y = Math.max(8, r.top - th - 7);
      tip.style.left = x + 'px';
      tip.style.top = y + 'px';
    });
  }
  document.addEventListener('mouseover', (e) => {
    const t = e.target && e.target.closest ? e.target.closest('[data-tip]') : null;
    if (!t) return;
    if (t === current) { clearTimeout(timer); return; }
    show(t);
  });
  document.addEventListener('mouseout', (e) => {
    if (!current) return;
    const t = e.target && e.target.closest ? e.target.closest('[data-tip]') : null;
    if (t === current) { clearTimeout(timer); timer = setTimeout(hide, 120); }
  });
  document.addEventListener('click', hide);
}

/* ---------- 侧栏收缩 ---------- */
(function initSidebar() {
  const root = document.documentElement;
  $('btn-collapse-side').addEventListener('click', () => {
    const on = root.classList.toggle('side-collapsed');
    try { localStorage.setItem('ktrt.side', on ? '1' : '0'); } catch (e) {}
  });
  document.querySelectorAll('.side .tab').forEach((b) => {
    const label = b.querySelector('span');
    if (label) b.title = label.textContent;
  });
})();

/* ---------- 视图切换 ---------- */
function saveStudyPos() {
  if (!state.bookId || !state.listNo) return;
  try {
    const m = JSON.parse(localStorage.getItem('ktrt.pos') || '{}');
    m[state.bookId] = { l: state.listNo, s: state.seq || 1 };
    localStorage.setItem('ktrt.pos', JSON.stringify(m));
  } catch (e) { /* 忽略 */ }
}

function studyPos(bookId) {
  try { return JSON.parse(localStorage.getItem('ktrt.pos') || '{}')[bookId] || null; } catch (e) { return null; }
}

/* ---------- 定位跳转：从风暴页/查词页跳到某词书的具体位置 ---------- */
function posChipsHtml(items) {
  return (items || []).map((p) => `
    <span class="pos-chip" data-book="${p.book_id}" data-list="${p.list_no || 1}" data-seq="${p.seq || 1}"
      data-tip="点击跳到《${escapeAttr(p.book_name || '')}》 List ${p.list_no || 1} 第 ${p.seq || 1} 个词">${escapeHtml(p.book_name || '')}</span>`).join('');
}

function wirePosChips(root) {
  (root || document).querySelectorAll('.pos-chip[data-book]').forEach((c) => {
    c.addEventListener('click', (e) => {
      e.stopPropagation();
      goToWord(c.dataset.book, c.dataset.list, c.dataset.seq);
    });
  });
}

async function goToWord(bookId, listNo, seq) {
  if (!bookId) return;
  state.bookId = Number(bookId);
  state.listNo = Number(listNo) || 1;
  state.seq = Number(seq) || 1;
  const sel = $('book-select');
  if (sel) sel.value = String(state.bookId);
  state.lists = [];
  switchView('study');
  saveStudyPos();
  toast('已跳到该词在词书中的位置');
}

function switchView(name) {
  if (chg.active && name !== 'challenge') {
    if (!confirm('闯关进行中，切换页面将丢弃本次进度（已入错题本的词不受影响），确定退出？')) return;
    resetChallengeState();
  }
  document.querySelectorAll('.tab').forEach((x) => x.classList.toggle('active', x.dataset.view === name));
  document.querySelectorAll('.view').forEach((x) => x.classList.toggle('active', x.id === 'view-' + name));
  localStorage.setItem('activeView', name);
  if (name === 'manage') {
    refreshBooksUI().then(loadManage);
  } else if (name === 'import') {
    renderBookList();
  } else if (name === 'challenge') {
    refreshChallengeBooks();
  } else if (name === 'study') {
    if (state.books.length && !state.bookId) {
      state.bookId = state.books[0].id;
      const p = studyPos(state.bookId);
      if (p) { state.listNo = p.l; state.seq = p.s; }
    }
    if (state.bookId && !state.lists.length) loadLists();
  }
}
document.querySelectorAll('.tab').forEach((b) => {
  b.addEventListener('click', () => switchView(b.dataset.view));
});

/* ---------- 初始化 ---------- */
async function init() {
  try {
    const b = await api('/api/bootstrap');
    state.books = b.books;
    state.presets = b.presets || {};
    const s = b.settings || {};
  state.settings = { ...s, theme: s.theme === 'paper' ? 'light' : (s.theme || 'light'), theme_page: s.theme_page || 'minimal' };
    applyTheme(state.settings.theme);
    applyPageMode(state.settings.theme_page);
    populateBookSelect();
    populateSettings();
    syncThemeButtons();
    refreshExportSelects();
    switchView(localStorage.getItem('activeView') || 'study');
    reloadBookmarks();
    loadStorms();
    initFeatureHints();
    updInit();
    fitNoteHeight();
    if (window.ResizeObserver) new ResizeObserver(fitNoteHeight).observe(document.querySelector('.card'));
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
    saveStudyPos();
    state.bookId = Number(sel.value);
    const p = studyPos(state.bookId);
    state.listNo = p ? p.l : null;
    state.seq = p ? p.s : 1;
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
  refreshExportSelects();
}

async function loadLists() {
  const meta = await api(`/api/books/${state.bookId}/lists`);
  return renderLists(meta);
}

async function renderLists(meta) {
  state.lists = meta;
  const sel = $('list-select');
  if (!meta.some((l) => l.list_no === state.listNo)) {
    state.listNo = meta.length ? meta[0].list_no : 1;
    state.seq = 1;
  }
  sel.innerHTML = meta.map((l) => `<option value="${l.list_no}">Word List ${l.list_no}</option>`).join('');
  sel.value = state.listNo;
  sel.onchange = () => {
    state.listNo = Number(sel.value);
    state.seq = 1;
    saveStudyPos();
    loadCard();
  };
  await loadCard();
}

async function loadCard() {
  if (!state.bookId) return;
  try {
    state.card = await api(`/api/card?book_id=${state.bookId}&list_no=${state.listNo}&seq=${state.seq}`);
    renderCard();
    syncBookmarkButton();
    syncStormIcon();
    requestAnimationFrame(fitNoteHeight);
    loadNote(state.card.word.id);
    $('sentence-prompt').value = '';
    $('dict-box').classList.add('hidden');
    $('btn-dict').classList.remove('active');
    $('edit-box').classList.add('hidden');
    $('btn-edit').classList.remove('active');
    _ttsStop();                                  // 换词时停掉上一段朗读
    prefetchTts(state.card.word.word);           // 预取当前词语音，点下去立刻出声
  } catch (e) {
    toast(e.message);
  }
}

function bookLang() {
  const b = state.books.find((x) => x.id === state.bookId);
  return b ? b.language : '英语';
}

/* ---------- 搭配 / 短语：合并成一栏并规律排布 ---------- */
function splitPhraseItems(text) {
  return String(text || '')
    .split(/[；;\n]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

/* 排序规则（稳定、可解释）：含本词的在前 → 更短的在前 → 字母序兜底。 */
function mergeCollocations(c) {
  const head = (c.word.word || '').trim();
  let re = null;
  if (head) {
    const esc = head.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    re = new RegExp('(^|[^A-Za-z])' + esc + '(?![A-Za-z])', 'i');
  }
  const seen = new Set();
  const items = [];
  for (const s of splitPhraseItems(c.word.collocations).concat(splitPhraseItems(c.word.phrases))) {
    const key = s.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    items.push({ s, hit: re && re.test(s) ? 1 : 0 });
  }
  return items
    .sort((a, b) => (b.hit - a.hit) || (a.s.length - b.s.length) || a.s.localeCompare(b.s))
    .map((x) => x.s);
}

/* 把条目里的本词标出来（含变形：abatement / abatements） */
function highlightHead(text, head) {
  const esc = escapeHtml(text);
  const h = (head || '').trim();
  if (!h) return esc;
  const re = new RegExp('(' + h.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\w*)', 'gi');
  return esc.replace(re, '<b class="head-hit">$1</b>');
}

function renderCard() {
  const c = state.card;
  if (!c) return;
  $('word').textContent = c.word.word;
  $('phonetic').textContent = c.word.phonetic ? '/' + c.word.phonetic.replace(/\//g, '') + '/' : '';
  const rows = [];
  if (c.word.meaning) {
    rows.push(`
      <div class="field">
        <span class="label">词性释义</span>
        <span class="value">${escapeHtml(c.word.meaning)}</span>
      </div>`);
  }
  const phraseItems = mergeCollocations(c);
  if (phraseItems.length) {
    rows.push(`
      <div class="field">
        <span class="label">搭配 / 短语</span>
        <div class="value"><ul class="phrase-list">${
          phraseItems.map((s) => `<li><span class="ph-text">${highlightHead(s, c.word.word)}</span>`
            + `<button class="icon-btn mini-speak" data-tts="${escapeAttr(s)}" title="朗读这一条">${SPEAKER_ICON}</button></li>`).join('')
        }</ul></div>
      </div>`);
  }
  for (const [label, value] of [['同义词', c.word.synonyms], ['反义词', c.word.antonyms], ['同根词', c.word.root_words]]) {
    if (!value) continue;
    rows.push(`
      <div class="field">
        <span class="label">${label}</span>
        <span class="value">${escapeHtml(value)}</span>
        <button class="icon-btn" data-tts="${escapeAttr(label + '：' + value)}" title="朗读">${SPEAKER_ICON}</button>
      </div>`);
  }
  $('fields').innerHTML = rows.join('');
  document.querySelectorAll('[data-tts]').forEach((b) => {
    b.addEventListener('click', () => {
      if (b === ttsBtnActive) { _ttsStop(); return; }
      speak(b.dataset.tts, b);
    });
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
    const pk = (state.card && state.card.word && state.card.word.phrasal_keys) || '';
    const hits = await api('/api/references?word=' + encodeURIComponent(word)
      + '&limit=8&keys=' + encodeURIComponent(pk));
    if (!hits.length) {
      box.classList.add('hidden');
      return;
    }
    list.innerHTML = hits.map((r) => {
      const display = r.display || r.phrase || r.key || '';
      const senses = (r.senses && r.senses.length)
        ? r.senses
        : [{ zh: r.meaning || '', en: '', example: r.example || '', example_zh: '' }];
      const first = senses[0] || {};
      const headZh = (first.zh || first.en || '').trim();
      const tag = [first.register, first.level].filter(Boolean).join(' · ');
      const spoken = display + '. ' + senses.map((s) => s.example || '').filter(Boolean).join(' ');
      return `
      <div class="ref-item" title="点击展开/收起完整条目">
        <div class="ref-top">
          <b class="ref-phrase">${escapeHtml(display)}</b>
          <span class="ref-mean">${escapeHtml(headZh)}</span>
          ${tag ? `<span class="ref-tag">${escapeHtml(tag)}</span>` : ''}
          ${senses.length > 1 ? `<span class="ref-count">${senses.length} 个义项</span>` : ''}
          <button class="icon-btn" data-ref-tts="${escapeAttr(spoken)}" title="朗读">${SPEAKER_ICON}</button>
        </div>
        <div class="ref-senses hidden">
          ${senses.map((s) => `
            <div class="ref-sense">
              ${s.zh ? `<div class="ref-sense-zh">${escapeHtml(s.zh)}</div>` : ''}
              ${s.en ? `<div class="ref-sense-en">${escapeHtml(s.en)}</div>` : ''}
              ${s.example ? `<div class="ref-ex">${escapeHtml(s.example)}</div>` : ''}
              ${s.example_zh ? `<div class="ref-ex-zh">${escapeHtml(s.example_zh)}</div>` : ''}
              ${s.register || s.level ? `<div class="ref-sense-tag">${escapeHtml([s.register, s.level].filter(Boolean).join(' · '))}</div>` : ''}
            </div>`).join('')}
        </div>
      </div>`;
    }).join('');
    box.classList.remove('hidden');
    list.querySelectorAll('[data-ref-tts]').forEach((b) => {
      b.addEventListener('click', () => speak(b.dataset.refTts));
    });
    list.querySelectorAll('.ref-item').forEach((item) => {
      item.addEventListener('click', (e) => {
        if (e.target.closest('button')) return;
        const s = item.querySelector('.ref-senses');
        if (s) s.classList.toggle('hidden');
      });
    });
  } catch (e) {
    box.classList.add('hidden');
  }
}

function renderStatus(s) {
  $('btn-learn').classList.toggle('active', !!s.learned);
  $('btn-unfamiliar').classList.toggle('active', !!s.unfamiliar);
  $('btn-favorite').classList.toggle('active-fav', !!s.favorite);
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
$('btn-unfamiliar').addEventListener('click', () => setStatus('unfamiliar', !state.card.status.unfamiliar));
$('btn-favorite').addEventListener('click', () => setStatus('favorite', !state.card.status.favorite));

function go(delta) {
  const total = state.card.progress.total;
  let n = state.seq + delta;
  if (n < 1) n = 1;
  if (n > total) n = total;
  state.seq = n;
  saveStudyPos();
  loadCard();
}
$('btn-next').addEventListener('click', () => go(1));
$('btn-prev').addEventListener('click', () => go(-1));
document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  if (e.key === 'ArrowRight') go(1);
  if (e.key === 'ArrowLeft') go(-1);
});

/* ---------- 书签 ---------- */
function currentBookmark() {
  if (!state.card || !state.card.word) return null;
  return state.bookmarks.find(
    (b) => b.book_id === state.bookId && b.list_no === state.listNo && b.seq === state.seq,
  ) || null;
}

function syncBookmarkButton() {
  const btn = $('btn-bookmark');
  const bm = currentBookmark();
  btn.classList.toggle('active', !!bm);
  btn.title = bm ? '已在此位置留书签（点击移除）' : '书签：记住这个位置';
}

function syncStormIcon() {
  const btn = $('btn-storm-view');
  if (!btn || !state.card) return;
  const w = state.card.word.word.toLowerCase();
  btn.classList.toggle('active', state.storms.some((x) => x.word.toLowerCase() === w));
}

function fitNoteHeight() {
  const card = document.querySelector('.card');
  const notes = document.querySelector('.note-panel .notes');
  if (!card || !notes) return;
  const split = document.querySelector('.study-split');
  if (split && getComputedStyle(split).flexDirection !== 'row') {
    notes.style.height = '';
    return;
  }
  notes.style.height = Math.max(card.offsetHeight, 320) + 'px';
}

function populateBookmarkSelect() {
  const sel = $('bookmark-select');
  const multiBook = new Set(state.bookmarks.map((b) => b.book_id)).size > 1;
  sel.innerHTML = '<option value="">书签 ▾（' + state.bookmarks.length + '）</option>'
    + state.bookmarks.map((b) => {
      const head = multiBook ? b.book_name + ' · ' : '';
      return `<option value="${b.id}">${escapeHtml(head + 'List ' + b.list_no + ' · ' + b.word + '（#' + b.seq + '）')}</option>`;
    }).join('');
}

async function reloadBookmarks() {
  try {
    state.bookmarks = await api('/api/bookmarks');
  } catch (e) {
    state.bookmarks = [];
  }
  populateBookmarkSelect();
  syncBookmarkButton();
}

async function jumpToBookmark(id) {
  const bm = state.bookmarks.find((x) => x.id === id);
  if (!bm) return;
  const switchBook = bm.book_id !== state.bookId || !state.lists.length;
  if (switchBook) saveStudyPos();
  state.bookId = bm.book_id;
  state.listNo = bm.list_no;
  state.seq = bm.seq;
  try {
    if (switchBook) {
      const meta = await api(`/api/books/${state.bookId}/lists`);
      if (!meta.some((l) => l.list_no === state.listNo)) {
        toast('书签位置已失效，已刷新书签列表');
        await reloadBookmarks();
        return;
      }
      await renderLists(meta);
      $('book-select').value = String(state.bookId);
    } else {
      $('list-select').value = String(state.listNo);
      await loadCard();
    }
    saveStudyPos();
  } catch (e) {
    toast(e.message);
  }
}

$('btn-bookmark').addEventListener('click', async () => {
  const w = state.card && state.card.word;
  if (!w) { toast('还没有单词'); return; }
  const bm = currentBookmark();
  try {
    if (bm) {
      await api('/api/bookmarks/' + bm.id, { method: 'DELETE' });
      toast('已移除书签');
    } else {
      await api('/api/bookmarks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          book_id: state.bookId,
          list_no: state.listNo,
          seq: state.seq,
          word: w.word,
        }),
      });
      toast('已在此处留下书签');
    }
    await reloadBookmarks();
  } catch (e) {
    toast(e.message);
  }
});

$('bookmark-select').addEventListener('change', () => {
  const id = Number($('bookmark-select').value);
  $('bookmark-select').value = '';
  if (id) jumpToBookmark(id);
});

/* ---------- 造句 ---------- */
function highlightWord(sentence, word, roots) {
  const bases = [word.replace(/[()].*/, '').trim()];
  (roots || '').split('；').forEach((r) => {
    const rw = (r || '').replace(/[()].*/, '').trim();
    if (rw && !bases.includes(rw)) bases.push(rw);
  });
  const lower = sentence.toLowerCase();
  let target = null;
  for (const b of bases) {
    if (b && lower.includes(b.toLowerCase())) { target = b; break; }
  }
  if (!target) {
    const suffixes = ['s', 'es', 'ed', 'd', 'ing', 'ies'];
    outer:
    for (const b of bases) {
      for (const sf of suffixes) {
        const cand = b + sf;
        if (cand && lower.includes(cand.toLowerCase())) { target = cand; break outer; }
      }
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
      <div class="en">${highlightWord(s.sentence, state.card.word.word, state.card.word.root_words)}</div>
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
  const btn = $('btn-dict');
  if (!box.classList.contains('hidden')) {
    box.classList.add('hidden');
    btn.classList.remove('active');
    return;
  }
  btn.classList.add('active');
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
      (d.exchange_text || d.exchange ? `\n词形变化：${d.exchange_text || d.exchange}` : '')
    );
  } catch (e) {
    box.textContent = '查询失败：' + e.message;
  }
});

/* ---------- 词条编辑 ---------- */
const EDIT_FORM_FIELDS = [
  ['word', '单词', 'input'],
  ['phonetic', '音标', 'input'],
  ['meaning', '词性释义', 'textarea'],
  ['collocations', '搭配', 'textarea'],
  ['phrases', '短语', 'textarea'],
  ['synonyms', '同义词', 'textarea'],
  ['antonyms', '反义词', 'textarea'],
  ['root_words', '同根词', 'textarea'],
];

function renderEditBox() {
  const w = state.card.word;
  const rows = EDIT_FORM_FIELDS.map(([k, label, kind]) => {
    const val = w[k] || '';
    const input = kind === 'input'
      ? `<input class="edit-input" data-edit="${k}" value="${escapeAttr(val)}">`
      : `<textarea class="edit-input" data-edit="${k}" rows="2">${escapeHtml(val)}</textarea>`;
    return `<label class="edit-row"><span class="edit-label">${label}</span>${input}</label>`;
  }).join('');
  $('edit-box').innerHTML = `
    <div class="edit-head">
      <b>编辑：${escapeHtml(w.word)}</b>
      <span class="edit-meta">List ${w.list_no} · 第 ${w.seq} 个 · 保存后同步本地库与词书 Excel</span>
    </div>
    <div class="edit-grid">${rows}</div>
    <div class="edit-actions">
      <button class="btn primary" id="btn-edit-save">保存并回写词书</button>
      <button class="btn" id="btn-edit-cancel">取消</button>
    </div>`;
  $('btn-edit-save').addEventListener('click', saveEdit);
  $('btn-edit-cancel').addEventListener('click', () => toggleEditBox(false));
}

function toggleEditBox(force) {
  const box = $('edit-box');
  const btn = $('btn-edit');
  const show = force === undefined ? box.classList.contains('hidden') : force;
  if (show) {
    renderEditBox();
    box.classList.remove('hidden');
    btn.classList.add('active');
  } else {
    box.classList.add('hidden');
    btn.classList.remove('active');
  }
}

async function saveEdit() {
  const payload = {};
  document.querySelectorAll('[data-edit]').forEach((el) => { payload[el.dataset.edit] = el.value; });
  if (!payload.word.trim()) {
    toast('单词不能为空');
    return;
  }
  const btn = $('btn-edit-save');
  btn.disabled = true;
  btn.textContent = '保存中…';
  try {
    const r = await api('/api/word/' + state.card.word.id + '/edit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const ex = r.excel || {};
    await loadCard();
    if (ex.updated) toast('已保存，词书 Excel 已更新');
    else if (ex.message) toast('已存入本地库；' + ex.message);
    else toast('已存入本地库');
  } catch (e) {
    toast('保存失败：' + e.message);
    btn.disabled = false;
    btn.textContent = '保存并回写词书';
  }
}

$('btn-edit').addEventListener('click', () => toggleEditBox());

/* ---------- 自定义查词典 ---------- */
$('btn-custom-dict').addEventListener('click', () => {
  $('custom-modal').classList.remove('hidden');
  requestAnimationFrame(() => $('cd-word').focus());
});
function closeCustomModal() { $('custom-modal').classList.add('hidden'); }
$('btn-custom-modal-close').addEventListener('click', closeCustomModal);
$('custom-modal').addEventListener('click', (e) => { if (e.target === $('custom-modal')) closeCustomModal(); });

let cdState = null;

function cdWordForQuery() {
  return (cdState && cdState.canonical) || (cdState && cdState.typed) || $('cd-word').value.trim();
}

function cdBasicHtml() {
  const s = cdState;
  const d = (s && s.dict) || {};
  const typed = s ? s.typed : '';
  let html = `<b>${escapeHtml(typed)}</b>`;
  if (s && s.canonical) {
    html += `<div style="color:var(--accent);font-size:13px;margin:2px 0">已自动匹配原形：<b>${escapeHtml(s.canonical)}</b></div>`;
  }
  if (d.found) {
    html += d.phonetic ? ` [${escapeHtml(d.phonetic)}]` : '';
    if (d.translation) html += `<br>释义：${escapeHtml(d.translation.replace(/;/g, '；').replace(/\n/g, '<br>'))}`;
    if (d.definition) html += `<br>定义：${escapeHtml(d.definition.replace(/\n/g, '<br>'))}`;
    if (d.exchange_text || d.exchange) html += `<br>词形变化：${escapeHtml(d.exchange_text || d.exchange)}`;
  } else {
    html += '<br><span style="color:var(--muted)">离线词典未收录该拼写</span>';
  }
  return html;
}

function cdWireButtons() {
  const favBtn = $('cd-fav');
  if (favBtn) favBtn.addEventListener('click', async () => {
    try {
      await api('/api/custom-dict/favorite', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ word: cdWordForQuery() }),
      });
      toast('已收藏（按原形处理）');
      cdState.fav = true;
      await cdLookup();
    } catch (e) {
      toast(e.message);
    }
  });
  const addBtn = $('cd-add');
  if (addBtn) addBtn.addEventListener('click', async () => {
    const phrase = !!(cdState && cdState.isPhrase);
    const idleLabel = phrase ? '＋ AI 翻译并加入收藏册' : '＋ 添加到外部单词收藏册';
    addBtn.disabled = true;
    addBtn.textContent = '生成中…';
    try {
      const res = await api('/api/custom-dict/add', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ word: cdWordForQuery() }),
      });
      toast(phrase ? '已用 AI 翻译并加入收藏册' : '已按原形添加到「外部单词收藏册」');
      $('cd-result').innerHTML = `<span class="ok">已加入「外部单词收藏册」：<b>${escapeHtml(res.word || cdWordForQuery())}</b>（${phrase ? 'AI 翻译' : '按原形'}）；当前背诵进度不受影响，可在书单里随时切换到它。</span>`;
      await refreshBooksUI();
    } catch (e) {
      $('cd-result').innerHTML = `<span class="err">${e.message}</span>`;
    } finally {
      addBtn.disabled = false;
      addBtn.textContent = idleLabel;
    }
  });
  document.querySelectorAll('.cd-sug').forEach((el) => el.addEventListener('click', () => {
    $('cd-word').value = el.dataset.sug;
    cdLookup();
  }));
}

/* ---------- 机翻（自动判断中↔英，联网即可用） ---------- */
let cdMtSeq = 0;

async function cdAutoTranslate(text) {
  const box = $('cd-mt');
  if (!box) return;
  const seq = ++cdMtSeq;
  box.classList.remove('hidden');
  box.innerHTML = '<span style="color:var(--muted)">机翻中…</span>';
  try {
    const r = await api('/api/custom-dict/translate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
      timeout: 30000,
    });
    if (seq !== cdMtSeq) return;
    box.innerHTML = `<div class="cd-mt-label">机翻 · ${escapeHtml(r.to)}</div>`
      + `<div class="cd-mt-text">${escapeHtml(r.translation)}</div>`
      + '<button class="btn" id="cd-mt-copy">复制译文</button>';
    $('cd-mt-copy').addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(r.translation);
        toast('译文已复制');
      } catch (e) {
        toast('复制失败，请手动选择文本');
      }
    });
  } catch (e) {
    if (seq !== cdMtSeq) return;
    const msg = /not found/i.test(e.message || '')
      ? '机翻不可用：程序后端还是旧版本，重启程序后重试'
      : e.message;
    box.innerHTML = `<span class="err">${escapeHtml(msg)}</span>`;
  }
}

async function cdLookup() {
  const w = $('cd-word').value.trim();
  const out = $('cd-result');
  if (!w) { toast('请输入单词'); return; }
  cdState = null;
  out.innerHTML = '<span style="color:var(--muted)">查询中…</span>';
  try {
    const r = await api('/api/custom-dict/lookup', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ word: w }),
    });
    cdState = {
      typed: r.word || w,
      canonical: r.canonical || '',
      isPhrase: !!r.is_phrase,
      components: r.components || [],
      dict: r.dict || {},
      books: r.in_books || [],
      fav: r.favorite,
    };
    const names = cdState.books.map((b) => b.book_name).join('、');
    let html = cdBasicHtml();
    if (cdState.components.length) {
      html += '<div style="margin-top:6px;color:var(--muted)">组成词：'
        + cdState.components.map((c) => escapeHtml(
          c.word + (c.translation ? ' ' + c.translation.replace(/\n/g, '；') : '（本地未收录）')
          + (c.in_books && c.in_books.length ? '（' + c.in_books.join('、') + '）' : ''),
        )).join('；')
        + '</div>';
    }
    if (names) {
      html += `<br>所在词书（点击可跳到该位置）：${posChipsHtml(cdState.books)}`;
      html += cdState.fav
        ? '<br><span class="ok">已收藏</span>'
        : '<br><button id="cd-fav" class="btn">☆ 收藏</button>';
    } else {
      html += '<br><span style="color:var(--muted)">'
        + (cdState.isPhrase
          ? '词书未收录该短语；可用 AI 按组成词翻译并加入「外部单词收藏册」'
          : '不在任何已导入词书中（会按原形添加到「外部单词收藏册」）')
        + '</span>'
        + `<br><button id="cd-add" class="btn primary">${cdState.isPhrase ? '＋ 加入词库（只存释义）' : '＋ 添加到外部单词收藏册'}</button>`;
    }
    out.innerHTML = html;
    cdWireButtons();
    wirePosChips(out);
    cdAutoTranslate(w);
    cdAutoOnline(w);
    // 拼写纠错：词典与词书都没命中时给出建议
    if (!cdState.dict.found && !names) {
      try {
        const sug = await api('/api/custom-dict/suggest', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ word: cdState.typed }),
        });
        if (sug.suggestions && sug.suggestions.length) {
          out.innerHTML += '<br><span style="color:var(--muted)">您是不是想搜：</span>'
            + sug.suggestions.map((s) => `<span class="cd-sug" data-sug="${escapeAttr(s)}">${escapeHtml(s)}</span>`).join('');
          cdWireButtons();
        }
      } catch (e) { /* 建议失败不影响主结果 */ }
    }
  } catch (e) {
    out.innerHTML = `<span class="err">${e.message}</span>`;
  }
}

function cdAppendSaveAiButton(text) {
  const out = $('cd-result');
  if (!cdState || !text || (cdState.books && cdState.books.length)) return;
  out.innerHTML += '<div style="margin-top:8px"><button id="cd-save-ai" class="btn primary" data-tip="把这份 AI 整理结果作为词条写入「外部单词收藏册」，完整文本同时存入该词笔记。">＋ 把这份 AI 释义加入外部收藏册</button><span id="cd-save-ai-msg" style="margin-left:8px;font-size:13px"></span></div>';
  $('cd-save-ai').addEventListener('click', async () => {
    const b = $('cd-save-ai');
    b.disabled = true;
    b.textContent = '保存中…';
    try {
      const r = await api('/api/custom-dict/save-ai', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ word: cdWordForQuery(), ai_text: text }),
      });
      $('cd-save-ai-msg').innerHTML = `<span class="ok">已加入：${escapeHtml(r.word)}（${escapeHtml(r.book_name)} · List ${r.list_no}）</span>`;
      b.remove();
      await refreshBooksUI();
    } catch (e) {
      $('cd-save-ai-msg').innerHTML = `<span class="err">${escapeHtml(e.message)}</span>`;
      b.disabled = false;
      b.textContent = '＋ 把这份 AI 释义加入外部收藏册';
    }
  });
}

$('btn-cd-lookup').addEventListener('click', cdLookup);
/* ---------- 在线联想（Datamuse 词汇关系）：查询后自动加载，无需点击 ---------- */
let cdOnlineSeq = 0;

async function cdAutoOnline(word) {
  const box = $('cd-online');
  if (!box) return;
  const seq = ++cdOnlineSeq;
  box.classList.remove('hidden');
  box.innerHTML = '<span style="color:var(--muted)">在线联想中…</span>';
  try {
    const onl = await api('/api/custom-dict/online', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ word }),
      timeout: 30000,
    });
    if (seq !== cdOnlineSeq) return;
    const dm = onl.datamuse || {};
    const lines = [];
    if (dm.related && dm.related.length) lines.push('相关：' + dm.related.slice(0, 8).map(escapeHtml).join('、'));
    if (dm.sounds_like && dm.sounds_like.length) lines.push('同音/近音：' + dm.sounds_like.slice(0, 6).map(escapeHtml).join('、'));
    if (dm.spelled_like && dm.spelled_like.length) lines.push('形似：' + dm.spelled_like.slice(0, 6).map(escapeHtml).join('、'));
    if (!lines.length) {
      box.classList.add('hidden');
      return;
    }
    box.innerHTML = '<div class="cd-mt-label">在线联想 · Datamuse</div>' + lines.join('<br>');
  } catch (e) {
    if (seq !== cdOnlineSeq) return;
    box.classList.add('hidden');
  }
}
$('cd-word').addEventListener('keydown', (e) => { if (e.key === 'Enter') cdLookup(); });

/* 查词页 → 风暴：已有词卡就地预览，没有就跳到风暴页去生成 */
$('btn-cd-storm').addEventListener('click', () => {
  const w = (cdWordForQuery() || '').trim();
  if (!w) { toast('先查询一个单词'); return; }
  const hit = state.storms.find((s) => (s.word || '').toLowerCase() === w.toLowerCase());
  if (hit) {
    openStorm(hit.id);
    return;
  }
  closeCustomModal();
  switchView('storm');
  const inp = $('storm-gen-word') || $('storm-search');
  if (inp) inp.value = w;
  toast('「' + w + '」还没有风暴词卡，在风暴页点生成即可');
});

/* ---------- 风暴词卡 ---------- */
function renderStormHtml(md) {
  const esc = escapeHtml(md || '');
  let html = '';
  let inList = false;
  for (const raw of esc.split(/\r?\n/)) {
    const line = raw.trim();
    if (/^# /.test(line)) {
      if (inList) { html += '</ul>'; inList = false; }
      html += '<h2>' + line.replace(/^# /, '') + '</h2>';
    } else if (/^## /.test(line)) {
      if (inList) { html += '</ul>'; inList = false; }
      html += '<h3>' + line.replace(/^## /, '') + '</h3>';
    } else if (/^###+ /.test(line)) {
      if (inList) { html += '</ul>'; inList = false; }
      html += '<h3>' + line.replace(/^###+ /, '') + '</h3>';
    } else if (/^- /.test(line)) {
      if (!inList) { html += '<ul>'; inList = true; }
      html += '<li>' + line.slice(2) + '</li>';
    } else if (/^> /.test(line)) {
      if (inList) { html += '</ul>'; inList = false; }
      html += '<blockquote>' + line.slice(2) + '</blockquote>';
    } else if (line === '') {
      if (inList) { html += '</ul>'; inList = false; }
    } else {
      if (inList) { html += '</ul>'; inList = false; }
      html += '<p>' + line + '</p>';
    }
  }
  if (inList) html += '</ul>';
  return html.replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>').replace(/==([^=\n]+)==/g, '<mark>$1</mark>');
}

async function loadStorms() {
  try { state.storms = await api('/api/storm'); } catch (e) { state.storms = []; }
  renderStormList();
  syncStormIcon();
}

function renderStormList() {
  const el = $('storm-list');
  const kw = ($('storm-search').value || '').trim().toLowerCase();
  const items = kw
    ? state.storms.filter((s) => s.word.toLowerCase().includes(kw) || (s.language || '').toLowerCase().includes(kw))
    : state.storms;
  if (!items.length) {
    el.innerHTML = '<p style="color:var(--muted);font-size:13px">'
      + (state.storms.length ? '没有匹配的风暴词卡。' : '还没有风暴词卡。输入一个单词点“生成”试试。')
      + '</p>';
    return;
  }
  el.innerHTML = items.map((s) => `
    <div class="storm-item">
      <input type="checkbox" class="storm-check" value="${s.id}">
      <span class="storm-name">
        <span class="sw storm-word" data-open="${s.id}" data-tip="点击查看该词的风暴词卡全文（弹出覆盖层）。">${escapeHtml(s.word)}</span>
        ${(s.positions && s.positions.length)
          ? posChipsHtml(s.positions)
          : ((s.in_books && s.in_books.length)
            ? s.in_books.map((n) => `<span class="pos-none">${escapeHtml(n)}</span>`).join('')
            : '<span class="pos-none">不在词书</span>')}
      </span>
      <button class="btn" data-open="${s.id}" data-tip="展开该词的风暴词卡全文；生成后离线也可查看。">查看</button>
      <button class="btn danger" data-del="${s.id}" data-tip="删除这张风暴词卡；不影响任何单词书内容。">删除</button>
    </div>`).join('');
  el.querySelectorAll('[data-open]').forEach((b) => b.addEventListener('click', () => openStorm(Number(b.dataset.open))));
  wirePosChips(el);
  el.querySelectorAll('[data-del]').forEach((b) => b.addEventListener('click', async () => {
    if (!confirm('删除这张风暴词卡？')) return;
    await api('/api/storm/' + b.dataset.del, { method: 'DELETE' });
    await loadStorms();
  }));
}

async function openStorm(id) {
  try {
    const s = await api('/api/storm/' + id);
    const meta = state.storms.find((x) => x.id === id) || {};
    const chips = (meta.positions && meta.positions.length) ? posChipsHtml(meta.positions) : '';
    $('storm-modal-title').innerHTML = '风暴词卡 · ' + escapeHtml(s.word) + (chips ? ' ' + chips : '');
    $('storm-modal-body').innerHTML = `<div class="storm-detail">${renderStormHtml(s.markdown)}</div>`;
    $('storm-modal').classList.remove('hidden');
    wirePosChips($('storm-modal'));
  } catch (e) {
    toast(e.message);
  }
}

function closeStormModal() {
  $('storm-modal').classList.add('hidden');
}
$('btn-storm-modal-close').addEventListener('click', closeStormModal);
$('storm-modal').addEventListener('click', (e) => { if (e.target === $('storm-modal')) closeStormModal(); });
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  if (!$('storm-modal').classList.contains('hidden')) closeStormModal();
  if (!$('custom-modal').classList.contains('hidden')) closeCustomModal();
});

async function generateStorm(word, silent) {
  const btn = $('btn-storm-gen');
  const msg = $('storm-gen-msg');
  if (!silent) {
    btn.disabled = true;
    btn.textContent = '生成中…';
    msg.textContent = '正在检索本地词库 + 免费开源在线词源，并用 AI 整理（约需几秒）…';
  }
  try {
    const r = await api('/api/storm/generate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ word, language: bookLang() }),
    });
    await loadStorms();
    openStorm(r.id);
    if (!silent) msg.innerHTML = '<span class="ok">已生成风暴词卡：' + escapeHtml(r.word) + '</span>';
  } catch (e) {
    if (!silent) msg.innerHTML = `<span class="err">${escapeHtml(e.message)}</span>`;
    toast(e.message);
  } finally {
    if (!silent) { btn.disabled = false; btn.textContent = '生成 / 更新风暴词卡'; }
  }
}

function selectedStormIds() {
  return [...document.querySelectorAll('.storm-check:checked')].map((x) => x.value).join(',');
}

$('btn-storm-gen').addEventListener('click', () => {
  const w = $('storm-word').value.trim();
  if (!w) { toast('请输入单词'); return; }
  generateStorm(w, false);
});
$('storm-word').addEventListener('keydown', (e) => { if (e.key === 'Enter') $('btn-storm-gen').click(); });
$('storm-search').addEventListener('input', renderStormList);
$('btn-storm-exp-md').addEventListener('click', () => {
  window.location.href = '/api/storm/export?fmt=md&ids=' + encodeURIComponent(selectedStormIds());
});
$('btn-storm-exp-xlsx').addEventListener('click', () => {
  window.location.href = '/api/storm/export?fmt=excel&ids=' + encodeURIComponent(selectedStormIds());
});
$('btn-storm-view').addEventListener('click', async () => {
  const w = state.card.word.word;
  const s = state.storms.find((x) => x.word.toLowerCase() === w.toLowerCase());
  if (s) { openStorm(s.id); return; }
  if (!confirm('该词还没有风暴词卡，立即生成？')) return;
  await generateStorm(w, true);
});

/* ---------- 朗读 ---------- */
function ttsClean(text) {
  // 只朗读英文/法文部分：多条内容（；分隔）先加逗号停顿，再去掉中文翻译与全角符号
  return String(text || '').replace(/；/g, ', ').replace(/[\u3000-\u303F\uFF00-\uFFEF\u3400-\u4DBF\u4E00-\u9FFF]/g, ' ').replace(/\s+/g, ' ').trim();
}
function ttsNum(v, dft) {
  const n = Number(v);
  return isFinite(n) ? n : dft;
}
/* ---------- 朗读：带"正在播"反馈，可再次点击停止 ---------- */
let ttsAudio = null;
let ttsBtnActive = null;
let ttsAbort = null;
let ttsToken = 0;
const ttsCache = new Map();   // 键 -> blob URL（同一句反复点不重复合成）

function _ttsClear() {
  if (ttsBtnActive) {
    ttsBtnActive.classList.remove('speaking');
    ttsBtnActive = null;
  }
}

function _ttsStop() {
  ttsToken += 1;                     // 让在途请求失效，避免连点叠音
  if (ttsAbort) {
    try { ttsAbort.abort(); } catch (e) { /* ignore */ }
    ttsAbort = null;
  }
  if (ttsAudio) {
    try { ttsAudio.pause(); ttsAudio.currentTime = 0; } catch (e) { /* ignore */ }
    ttsAudio = null;
  }
  try { speechSynthesis.cancel(); } catch (e) { /* ignore */ }
  _ttsClear();
}

function _ttsKey(lang, clean) {
  const s = state.settings || {};
  return [lang, s.tts_voice_en || '', s.tts_voice_fr || '', s.tts_rate || '', s.tts_pitch || '',
          s.tts_volume || '', clean].join('|');
}

function _ttsCachePut(key, url) {
  ttsCache.set(key, url);
  while (ttsCache.size > 8) {
    const [k0, u0] = ttsCache.entries().next().value;
    ttsCache.delete(k0);
    try { URL.revokeObjectURL(u0); } catch (e) { /* ignore */ }
  }
}

async function _ttsFetchBlob(lang, clean, signal) {
  const res = await fetch('/api/tts?text=' + encodeURIComponent(clean) +
    '&lang=' + encodeURIComponent(lang) + '&t=' + Date.now(), { signal });
  if (!res.ok) throw new Error('合成失败');
  return await res.blob();
}

/* 卡片出现时预取当前词的语音：点下去就能立刻出声 */
async function prefetchTts(text) {
  const s = state.settings || {};
  if ((s.tts_provider || 'edge-tts') === 'browser') return;
  const clean = ttsClean(text);
  if (!clean) return;
  const lang = bookLang();
  const key = _ttsKey(lang, clean);
  if (ttsCache.has(key)) return;
  try {
    const blob = await _ttsFetchBlob(lang, clean, undefined);
    if (!ttsCache.has(key)) _ttsCachePut(key, URL.createObjectURL(blob));
  } catch (e) { /* 预取失败不影响使用 */ }
}

async function speak(text, btn) {
  const lang = bookLang();
  const s = state.settings || {};
  const clean = ttsClean(text);
  if (!clean) { toast('没有可朗读的内容'); return; }
  _ttsStop();                       // 连点：先停掉上一次（含在途请求）
  const token = ttsToken;
  if (btn) {
    btn.classList.add('speaking');
    ttsBtnActive = btn;
  }
  if (s.tts_provider === 'browser') {
    const u = new SpeechSynthesisUtterance(clean);
    u.rate = Math.min(2, Math.max(0.5, ttsNum(s.tts_rate, 0) / 100 + 1));
    u.pitch = Math.min(2, Math.max(0, ttsNum(s.tts_pitch, 0) / 50 + 1));
    u.volume = Math.min(1, Math.max(0, ttsNum(s.tts_volume, 100) / 100));
    if (lang === '法语') {
      u.lang = 'fr-FR';
    } else {
      const voiceKey = s.tts_voice_en || '美音·男';
      const uk = voiceKey.includes('英音');
      const male = voiceKey.includes('男');
      u.lang = uk ? 'en-GB' : 'en-US';
      const voices = speechSynthesis.getVoices();
      let v = voices.find((x) => x.lang.toLowerCase().startsWith(u.lang) &&
        (male ? /male/i.test(x.name) : /female/i.test(x.name)));
      if (!v) v = voices.find((x) => x.lang.toLowerCase().startsWith(u.lang));
      if (v) u.voice = v;
    }
    u.onend = () => { if (token === ttsToken) _ttsClear(); };
    u.onerror = () => { if (token === ttsToken) { _ttsClear(); toast('浏览器语音播放失败'); } };
    speechSynthesis.speak(u);
    return;
  }
  const key = _ttsKey(lang, clean);
  try {
    let url = ttsCache.get(key);
    if (!url) {
      const ctrl = new AbortController();
      ttsAbort = ctrl;
      const blob = await _ttsFetchBlob(lang, clean, ctrl.signal);
      if (token !== ttsToken) return;          // 期间又点了别的
      ttsAbort = null;
      url = URL.createObjectURL(blob);
      _ttsCachePut(key, url);
    }
    if (token !== ttsToken) return;
    ttsAudio = new Audio(url);
    ttsAudio.onended = () => { if (token === ttsToken) _ttsClear(); };
    ttsAudio.onerror = () => { if (token === ttsToken) { _ttsClear(); toast('播放失败'); } };
    await ttsAudio.play();
  } catch (e) {
    if (token !== ttsToken) return;            // 被更晚的点击取消了，静默退出
    ttsAbort = null;
    _ttsClear();
    if (!e || e.name !== 'AbortError') toast('语音合成失败：' + ((e && e.message) || '需要联网'));
  }
}
$('btn-word-tts').addEventListener('click', () => {
  const btn = $('btn-word-tts');
  if (btn === ttsBtnActive) { _ttsStop(); return; }   // 再点一次＝停止
  speak(state.card.word.word, btn);
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
      html += `<details class="list-group">
        <summary>Word List ${ln}<span class="cnt">（${listRows.length} 词）</span></summary>
        <table><thead><tr>
          <th>序号</th><th>单词</th><th>音标</th><th>状态</th><th>句子</th><th>操作</th>
        </tr></thead><tbody>`;
      for (const r of listRows) {
        const tags = [];
        if (r.unfamiliar) tags.push('<span class="tag off">不熟悉</span>');
        if (r.favorite) tags.push('<span class="tag fav">收藏</span>');
        if (r.learned) tags.push('<span class="tag learn">已背</span>');
        if (r.has_note) tags.push('<span class="tag learn">笔记</span>');
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
/* ---------- 导出词汇 ---------- */
let exportScope = 'unfamiliar';

function refreshExportSelects() {
  const bs = $('export-book');
  if (!bs) return;
  const cur = bs.value;
  bs.innerHTML = '<option value="">全部词书</option>' + state.books.map((b) =>
    `<option value="${b.id}">${escapeHtml(b.name)}</option>`).join('');
  if (cur !== '' && state.books.some((b) => String(b.id) === cur)) bs.value = cur;
  refreshExportLists();
}

async function refreshExportLists() {
  const ls = $('export-list');
  const bookId = Number($('export-book').value || 0);
  if (!bookId) {
    ls.innerHTML = '<option value="">全部 List</option>';
    return;
  }
  try {
    const meta = await api(`/api/books/${bookId}/lists`);
    ls.innerHTML = '<option value="">全部 List</option>' + meta.map((l) =>
      `<option value="${l.list_no}">List ${l.list_no}</option>`).join('');
  } catch (e) {
    ls.innerHTML = '<option value="">全部 List</option>';
  }
}

function setExportScope(scope) {
  exportScope = scope;
  ['unfamiliar', 'favorite', 'both'].forEach((s) => {
    $('btn-export-' + s).classList.toggle('active', s === scope);
  });
}

async function exportWords() {
  try {
    const bookId = $('export-book').value;
    const listNo = $('export-list').value;
    let apiUrl = '/api/export?scope=' + encodeURIComponent(exportScope);
    if (bookId) apiUrl += '&book_id=' + encodeURIComponent(bookId);
    if (listNo) apiUrl += '&list_no=' + encodeURIComponent(listNo);
    const res = await fetch(apiUrl);
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      throw new Error(d.detail || '导出失败');
    }
    const blob = await res.blob();
    const cd = res.headers.get('Content-Disposition') || '';
    let fname = 'KTRT_export.xlsx';
    const m = cd.match(/filename\*=UTF-8''([^;]+)/i) || cd.match(/filename="?([^";]+)"?/i);
    if (m) fname = decodeURIComponent(m[1]);
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = fname;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    toast('已导出：' + fname);
  } catch (e) {
    toast('导出失败：' + e.message);
  }
}
$('btn-export-unfamiliar').addEventListener('click', () => setExportScope('unfamiliar'));
$('btn-export-favorite').addEventListener('click', () => setExportScope('favorite'));
$('btn-export-both').addEventListener('click', () => setExportScope('both'));
$('btn-export-go').addEventListener('click', exportWords);
$('export-book').addEventListener('change', refreshExportLists);

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
      ${b.name === '外部单词收藏册'
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

/* ---------- 词书资源 ---------- */
const BOOK_RESOURCES = [
  { name: 'GRE 必背（6519 词）', file: 'GRE_Wordbook.xlsx' },
  { name: '雅思词汇真经（3608 词）', file: 'IELTS_Wordbook.xlsx' },
  { name: '考研英语词汇词根+联想记忆法（5905 词）', file: 'KAOYAN_Wordbook.xlsx' },
];
const REPO_URL = 'https://github.com/HoweyYang/KTRT';

function renderResources() {
  const box = $('resource-list');
  if (!box) return;
  box.innerHTML = BOOK_RESOURCES.map((b) => `
    <div class="resource-item">
      <span>${b.name}</span>
      <a class="btn" href="${REPO_URL}/raw/main/wordbooks/${b.file}">下载</a>
    </div>`).join('') + `
    <div class="resource-item">
      <span>仓库 wordbooks/ 目录（全部词书资源）</span>
      <a class="btn" href="${REPO_URL}/tree/main/wordbooks" target="_blank" rel="noopener">打开</a>
    </div>`;
}

$('btn-copy-prompt').addEventListener('click', async () => {
  const msg = $('prompt-msg');
  try {
    const text = await (await fetch('/static/docs/词书整理提示词.md')).text();
    await navigator.clipboard.writeText(text);
    msg.textContent = '已复制，粘贴给本地 AI 就能整理你自己的单词书。';
  } catch (e) {
    msg.textContent = '复制失败，点右边「查看提示词全文」可手动复制。';
  }
});
renderResources();

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
  $('s-voice-en').value = s.tts_voice_en || '美音·男';
  $('s-voice-fr').value = s.tts_voice_fr || '女声';
  $('s-rate').value = String(Math.min(150, Math.max(50, ttsNum(s.tts_rate, 0) + 100)));
  $('s-pitch').value = s.tts_pitch || '0';
  $('s-volume').value = s.tts_volume || '100';
  syncTtsLabels();
  ['s-rate', 's-pitch', 's-volume'].forEach((id) => $(id).addEventListener('input', syncTtsLabels));
  $('s-theme').value = s.theme === 'paper' ? 'light' : (s.theme || 'light');
  syncPageButtons();
  syncThemeLabels();
  $('page-normal').addEventListener('click', () => setPageMode('minimal'));
  $('page-paper').addEventListener('click', () => setPageMode('paper'));
  const cyberBtn = $('page-cyber');
  if (cyberBtn) cyberBtn.addEventListener('click', () => setPageMode('cyber'));
  sel.onchange = () => {
    const p = state.presets[sel.value];
    if (p) {
      $('s-base').value = p.base;
      $('s-model').value = p.model;
    }
  };
  $('s-theme').onchange = () => {
    applyTheme($('s-theme').value);
    state.settings = { ...(state.settings || {}), theme: $('s-theme').value };
    syncThemeButtons();   // 让侧栏三个配色按钮的高亮跟着走
  };
}

function syncTtsLabels() {
  const rate = $('s-rate'), pitch = $('s-pitch'), volume = $('s-volume');
  if (rate) $('rate-val').textContent = rate.value + '%';
  if (pitch) $('pitch-val').textContent = (Number(pitch.value) > 0 ? '+' : '') + pitch.value + 'Hz';
  if (volume) $('volume-val').textContent = volume.value + '%';
}

function syncThemeButtons() {
  const t = (state.settings && state.settings.theme) || 'dark-blue';
  $('theme-light').classList.toggle('on', t === 'light');
  $('theme-dark').classList.toggle('on', t === 'dark');
  $('theme-blue').classList.toggle('on', t === 'dark-blue');
}

function syncPageButtons() {
  const raw = (state.settings && state.settings.theme_page) || 'minimal';
  const p = PAGE_MODES.includes(raw) ? raw : (raw === 'paper' ? 'paper' : 'minimal');
  $('page-normal').classList.toggle('active', p === 'minimal');
  $('page-paper').classList.toggle('active', p === 'paper');
  const cyber = $('page-cyber');
  if (cyber) cyber.classList.toggle('active', p === 'cyber');
}

function setPageMode(mode) {
  const m = applyPageMode(mode);
  $('page-normal').classList.toggle('active', m === 'minimal');
  $('page-paper').classList.toggle('active', m === 'paper');
  const cyber = $('page-cyber');
  if (cyber) cyber.classList.toggle('active', m === 'cyber');
}

function setTheme(theme) {
  const t = theme === 'paper' ? 'light' : theme;
  applyTheme(t);
  $('s-theme').value = t;
  const s = state.settings || {};
  api('/api/settings', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      api_key: s.api_key || '', base_url: s.base_url || '', model: s.model || '', vendor: s.vendor || 'ds',
      tts_provider: s.tts_provider || 'edge-tts', tts_voice_en: s.tts_voice_en || '美音·男', tts_voice_fr: s.tts_voice_fr || '女声',
      tts_rate: s.tts_rate || '0', tts_pitch: s.tts_pitch || '0', tts_volume: s.tts_volume || '100',
      theme: t,
      theme_page: currentPageMode(),
    }),
  }).then((r) => { state.settings = r; syncThemeButtons(); }).catch(() => {});
}

$('theme-light').addEventListener('click', () => setTheme('light'));
$('theme-dark').addEventListener('click', () => setTheme('dark'));
$('theme-blue').addEventListener('click', () => setTheme('dark-blue'));

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
        tts_voice_en: $('s-voice-en').value,
        tts_voice_fr: $('s-voice-fr').value,
        tts_rate: String(Number($('s-rate').value) - 100),
        tts_pitch: $('s-pitch').value,
        tts_volume: $('s-volume').value,
        theme: $('s-theme').value,
        theme_page: currentPageMode(),
      }),
    });
    applyTheme($('s-theme').value);
    applyPageMode(state.settings.theme_page);
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

/* ---------- 更新 ---------- */
/* 版本号比较：数字段逐位比，相同再比后缀字母（0.1.6b > 0.1.6 > 0.1.6a）。 */
function versionKey(v) {
  const m = String(v || '').replace(/^v/i, '').trim().match(/^(\d+(?:\.\d+)*)([a-z]*)/i);
  if (!m) return [0, 0, 0, ''];
  const nums = m[1].split('.').map(Number);
  return [nums[0] || 0, nums[1] || 0, nums[2] || 0, (m[2] || '').toLowerCase()];
}

function versionNewer(rel, cur) {
  const a = versionKey(rel);
  const b = versionKey(cur);
  for (let i = 0; i < 3; i++) {
    if (a[i] > b[i]) return true;
    if (a[i] < b[i]) return false;
  }
  return a[3] > b[3];
}

const upd = { info: null, kind: '', timer: null };

function updKindLabel(kind, ver) {
  return kind === 'full' ? `下载并安装 v${ver}` : '应用热补丁';
}

function updDetailHtml(info) {
  let html = '';
  if (info.applied_patch) {
    const ap = info.applied_patch;
    html += `<p class="ok">已应用热补丁：v${escapeHtml(ap.version || '')} ·`
      + ` ${escapeHtml(String(ap.files || 0))} 个文件 · ${escapeHtml(ap.applied_at || '')}</p>`;
  }
  const latest = info.latest;
  if (!latest) return html;
  html += `<p>最新发布：<b>${escapeHtml(latest.tag || '')}</b>`
    + `（${escapeHtml((latest.published_at || '').slice(0, 10))}）`
    + (latest.newer ? ' · <span class="ok">有新版本</span>' : ' · 已是最新') + '</p>';
  if (latest.installer) {
    html += `<p class="muted">安装包：${escapeHtml(latest.installer.name)}`
      + `（${(latest.installer.size / 1048576).toFixed(1)} MB）</p>`;
  }
  if (latest.patch) {
    html += `<p class="muted">热补丁：${escapeHtml(latest.patch.name)}`
      + `（${(latest.patch.size / 1024).toFixed(0)} KB）</p>`;
  }
  if (latest.notes) {
    html += `<details><summary>更新说明</summary><pre class="upd-notes">${
      escapeHtml(latest.notes.slice(0, 800))}</pre></details>`;
  }
  if (latest.html_url) {
    html += `<p><a href="${escapeAttr(latest.html_url)}" target="_blank" rel="noopener">在 GitHub 查看</a></p>`;
  }
  if (info.commit) {
    html += `<p class="muted">main 最新提交：${escapeHtml(info.commit.sha)} · ${escapeHtml(info.commit.message)}</p>`;
  }
  return html;
}

function updRender() {
  const info = upd.info;
  if (!info) return;
  $('upd-version').textContent = `当前版本：v${info.current_version}（`
    + (info.mode === 'packaged' ? '安装版' : '源码版') + '）';
  $('upd-detail').innerHTML = updDetailHtml(info);
  const latest = info.latest || {};
  const canPatch = !!(info.patch && info.patch.applicable);
  const canFull = !!(latest.newer && info.installer && info.mode === 'packaged');
  upd.kind = canFull ? 'full' : (canPatch ? 'patch' : '');
  const btn = $('btn-upd-apply');
  btn.classList.toggle('hidden', !upd.kind);
  if (upd.kind) btn.textContent = updKindLabel(upd.kind, latest.version || info.current_version);
  const link = $('upd-page-link');
  const showLink = !!latest.html_url && (!upd.kind || info.mode !== 'packaged');
  link.classList.toggle('hidden', !showLink);
  if (showLink) link.href = latest.html_url;
}

async function updCheck(manual) {
  const box = $('upd-msg');
  if (manual) box.innerHTML = '<p class="muted">检查中…</p>';
  try {
    const info = await api('/api/update/status', { timeout: 30000 });
    upd.info = info;
    updRender();
    if (manual) {
      box.innerHTML = !info.ok
        ? `<p class="err">${escapeHtml(info.error || '检查失败')}</p>`
        : (upd.kind
          ? '<p class="ok">发现可更新的内容，点「立即更新」开始。</p>'
          : '<p class="ok">已是最新版本。</p>');
    }
    return info;
  } catch (e) {
    if (manual) box.innerHTML = `<p class="err">${escapeHtml(e.message)}</p>`;
    return null;
  }
}

function updPoll(kind) {
  clearInterval(upd.timer);
  const wrap = $('upd-bar-wrap');
  const bar = $('upd-bar');
  const box = $('upd-msg');
  wrap.classList.remove('hidden');
  upd.timer = setInterval(async () => {
    let j;
    try {
      j = await api('/api/update/progress');
    } catch (e) {
      return;
    }
    const pct = j.total ? Math.round((j.received * 100) / j.total) : 0;
    bar.style.width = (j.state === 'downloading' ? pct : 100) + '%';
    box.innerHTML = `<p class="${j.state === 'error' ? 'err' : 'muted'}">${escapeHtml(j.message || '')}</p>`;
    if (j.state === 'done') {
      clearInterval(upd.timer);
      if (kind === 'patch') {
        toast('补丁已应用，正在重新载入…');
        setTimeout(() => location.reload(), 1200);
      } else {
        wrap.classList.add('hidden');
      }
    } else if (j.state === 'error') {
      clearInterval(upd.timer);
      wrap.classList.add('hidden');
    }
  }, 700);
}

async function updApply(kind) {
  const box = $('upd-msg');
  const latest = (upd.info && upd.info.latest) || {};
  if (kind === 'full') {
    const name = latest.installer ? latest.installer.name : '安装包';
    if (!confirm(`将下载 ${name} 并静默安装。\n`
      + '过程中会弹出系统授权框，点“是”即可；装完程序会自动重开，学习数据不受影响。\n\n继续吗？')) return;
  }
  box.innerHTML = '<p class="muted">准备中…</p>';
  try {
    await api('/api/update/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind }),
      timeout: 30000,
    });
  } catch (e) {
    box.innerHTML = `<p class="err">${escapeHtml(e.message)}</p>`;
    return;
  }
  updPoll(kind);
}

function updPopup(info) {
  try {
    sessionStorage.setItem('updShown', '1');   // 同一次会话里只弹一次，刷新不重复打扰
  } catch (e) { /* 隐私模式下忽略 */ }
  const latest = info.latest || {};
  const lines = [`<p>发现 <b>${escapeHtml(latest.tag || ('v' + (latest.version || '')))}</b>`
    + `（当前 v${escapeHtml(info.current_version)}）。</p>`];
  if (latest.newer && info.installer && info.mode === 'packaged') {
    lines.push('<p class="muted">可以一键下载安装，装完自动重开，学习数据不受影响。</p>');
  } else if (info.patch && info.patch.applicable) {
    lines.push('<p class="muted">有热补丁可直接应用，不用重启。</p>');
  }
  if (latest.notes) {
    lines.push(`<pre class="upd-notes">${escapeHtml(latest.notes.slice(0, 400))}</pre>`);
  }
  $('update-modal-title').textContent = latest.newer ? '发现新版本' : '发现新补丁';
  $('update-modal-body').innerHTML = lines.join('');
  $('update-modal').classList.remove('hidden');
}

async function updInit() {
  const s = state.settings || {};
  const box = $('upd-auto');
  if (box) box.checked = s.auto_update_check !== '0';
  if (s.auto_update_check === '0') {
    updCheck(false);                     // 关了自动弹窗也把版本信息刷出来
    return;
  }
  const info = await updCheck(false);
  if (!info || !info.latest) return;
  const latest = info.latest;
  const hasPatch = !!(info.patch && info.patch.applicable);
  if (!latest.newer && !hasPatch) return;
  if ((s.update_snooze || '') === latest.version) return;
  try {
    if (sessionStorage.getItem('updShown') === '1') return;
  } catch (e) { /* 忽略 */ }
  // 同版本的热补丁已经装过就不再打扰
  if (!latest.newer && info.applied_patch && info.applied_patch.version === latest.version) return;
  updPopup(info);
}

$('btn-upd-check').addEventListener('click', () => updCheck(true));
$('btn-upd-apply').addEventListener('click', () => { if (upd.kind) updApply(upd.kind); });
$('btn-upd-modal-now').addEventListener('click', () => {
  $('update-modal').classList.add('hidden');
  if (upd.kind) updApply(upd.kind);
});
$('btn-upd-modal-later').addEventListener('click', () => $('update-modal').classList.add('hidden'));
$('btn-upd-modal-snooze').addEventListener('click', async () => {
  const v = (upd.info && upd.info.latest && upd.info.latest.version) || '';
  $('update-modal').classList.add('hidden');
  if (!v) return;
  if (state.settings) state.settings.update_snooze = v;
  try {
    await api('/api/update/prefs', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ snooze: v }),
    });
    toast('本版本不再提醒');
  } catch (e) {
    toast('保存失败：' + e.message);
  }
});
$('upd-auto').addEventListener('change', async (e) => {
  const on = e.target.checked ? '1' : '0';
  if (state.settings) state.settings.auto_update_check = on;
  try {
    await api('/api/update/prefs', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ auto_check: on }),
    });
  } catch (err) {
    toast('保存失败：' + err.message);
  }
});

/* ---------- 笔记本 ---------- */
/* ---------- 笔记本（所见即所得：原生 Markdown 输入即渲染） ---------- */
function noteInlineToHtml(esc) {
  return esc
    .replace(/==([^=\n]+)==/g, '<mark>$1</mark>')
    .replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>')
    .replace(/\*([^*\n]+)\*/g, '<i>$1</i>');
}

function noteMdToHtml(md) {
  const esc = escapeHtml(md || '');
  if (!esc.trim()) return '';
  return esc.split(/\r?\n/).map((line) => {
    if (/^##\s+/.test(line)) return '<h4 data-block>' + noteInlineToHtml(line.replace(/^##\s+/, '')) + '</h4>';
    if (/^#\s+/.test(line)) return '<h3 data-block>' + noteInlineToHtml(line.replace(/^#\s+/, '')) + '</h3>';
    if (line.trim() === '') return '<div data-block><br></div>';
    return '<div data-block>' + noteInlineToHtml(line) + '</div>';
  }).join('');
}

function noteInlineToMd(el) {
  let s = '';
  el.childNodes.forEach((n) => {
    if (n.nodeType === 3) { s += n.textContent; return; }
    if (n.nodeType !== 1) return;
    const tag = n.tagName;
    const inner = noteInlineToMd(n);
    if (tag === 'B' || tag === 'STRONG') s += '**' + inner + '**';
    else if (tag === 'I' || tag === 'EM') s += '*' + inner + '*';
    else if (tag === 'MARK') s += '==' + inner + '==';
    else if (tag === 'SPAN' && /background/i.test((n.style && n.style.cssText) || '')) s += '==' + inner + '==';
    else if (tag === 'BR') { /* 忽略块内换行 */ }
    else s += inner;
  });
  return s;
}

function noteToMd() {
  const box = $('note-editor');
  const lines = [];
  Array.from(box.childNodes).forEach((n) => {
    if (n.nodeType === 3) { if (n.textContent.trim()) lines.push(n.textContent.trim()); return; }
    if (n.nodeType !== 1) return;
    if (n.tagName === 'H3') lines.push('# ' + noteInlineToMd(n).trim());
    else if (n.tagName === 'H4') lines.push('## ' + noteInlineToMd(n).trim());
    else lines.push(noteInlineToMd(n).replace(/^[ \t]+|[ \t]+$/g, ''));
  });
  return lines.join('\n').replace(/\n{3,}/g, '\n\n');
}

function noteBlockAt() {
  const sel = window.getSelection();
  if (!sel || !sel.anchorNode) return null;
  let el = sel.anchorNode.nodeType === 1 ? sel.anchorNode : sel.anchorNode.parentElement;
  return el && el.closest ? el.closest('[data-block]') : null;
}

function noteTextBeforeCaret() {
  const sel = window.getSelection();
  if (!sel || !sel.rangeCount) return '';
  const r = sel.getRangeAt(0);
  const b = noteBlockAt();
  if (!b) return '';
  const pre = document.createRange();
  pre.selectNodeContents(b);
  pre.setEnd(r.startContainer, r.startOffset);
  return pre.toString();
}

async function loadNote(wordId) {
  state.noteDirty = false;
  let content = '';
  try {
    const n = await api('/api/notes/' + wordId);
    content = n.content || '';
  } catch (e) { /* 还没有笔记 */ }
  $('note-editor').innerHTML = noteMdToHtml(content);
  $('note-cur-word').textContent = state.card && state.card.word ? '· ' + state.card.word.word : '';
}

function closeNoteContext() {
  $('note-context').classList.add('hidden');
}

function showNoteContext(x, y, actions) {
  const menu = $('note-context');
  menu.innerHTML = '';
  actions.forEach((a) => {
    const b = document.createElement('button');
    b.textContent = a.label;
    b.addEventListener('click', () => { closeNoteContext(); a.run(); });
    menu.appendChild(b);
  });
  menu.classList.remove('hidden');
  menu.style.left = x + 'px';
  menu.style.top = y + 'px';
  document.addEventListener('click', closeNoteContext, { once: true });
}

const NE = $('note-editor');

NE.addEventListener('input', () => {
  state.noteDirty = true;
  // 行首输入 # 或 ## 自动变成标题
  const b = noteBlockAt();
  if (!b || b.tagName !== 'DIV') return;
  const text = b.textContent;
  let level = 0;
  if (/^##\s/.test(text)) level = 2;
  else if (/^#\s/.test(text)) level = 1;
  if (!level) return;
  const prefix = level === 1 ? 2 : 3;
  if (noteTextBeforeCaret().length < prefix) return;
  const h = document.createElement(level === 1 ? 'H3' : 'H4');
  h.setAttribute('data-block', '');
  const lead = b.firstChild;
  if (lead && lead.nodeType === 3 && lead.nodeValue) lead.nodeValue = lead.nodeValue.slice(prefix);
  b.before(h);
  while (b.firstChild) h.appendChild(b.firstChild);
  b.remove();
  const sel = window.getSelection();
  const range = document.createRange();
  range.selectNodeContents(h);
  range.collapse(false);
  sel.removeAllRanges();
  sel.addRange(range);
});

NE.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && !e.altKey) {
    const k = e.key.toLowerCase();
    if (k === 'b') { e.preventDefault(); document.execCommand('bold'); return; }
    if (k === 'i') { e.preventDefault(); document.execCommand('italic'); return; }
  }
  if (e.key !== 'Enter' || e.shiftKey) return;
  const b = noteBlockAt();
  if (!b || (b.tagName !== 'H3' && b.tagName !== 'H4')) return; // 普通段落交给浏览器默认换行
  e.preventDefault();
  const sel = window.getSelection();
  if (!sel.rangeCount) return;
  const range = sel.getRangeAt(0);
  const tail = document.createRange();
  tail.setStart(range.startContainer, range.startOffset);
  tail.setEndAfter(b);
  const frag = tail.extractContents();
  const div = document.createElement('div');
  div.setAttribute('data-block', '');
  div.appendChild(frag);
  b.after(div);
  const r = document.createRange();
  r.selectNodeContents(div);
  r.collapse(true);
  sel.removeAllRanges();
  sel.addRange(r);
});

NE.addEventListener('paste', (e) => {
  e.preventDefault();
  const txt = (e.clipboardData || window.clipboardData).getData('text/plain');
  document.execCommand('insertText', false, txt);
});

NE.addEventListener('contextmenu', (ev) => {
  const sel = window.getSelection();
  const selText = sel && !sel.isCollapsed ? sel.toString().trim() : '';
  let hlEl = ev.target && ev.target.closest ? ev.target.closest('mark, span[style*="background"]') : null;
  if (!selText && !hlEl) return; // 交给浏览器默认菜单
  ev.preventDefault();
  const saved = sel && sel.rangeCount ? sel.getRangeAt(0).cloneRange() : null;
  const actions = [];
  if (selText && !(hlEl && hlEl.textContent.trim() === selText)) {
    const t = selText.length > 12 ? selText.slice(0, 12) + '…' : selText;
    actions.push({
      label: '高亮「' + t + '」',
      run: () => {
        const s = window.getSelection();
        s.removeAllRanges();
        s.addRange(saved);
        document.execCommand('hiliteColor', false, '#ffe14d');
        state.noteDirty = true;
      },
    });
  }
  if (hlEl) {
    actions.push({
      label: '取消高亮',
      run: () => {
        const p = hlEl.parentNode;
        if (p) {
          while (hlEl.firstChild) p.insertBefore(hlEl.firstChild, hlEl);
          p.removeChild(hlEl);
        }
        state.noteDirty = true;
      },
    });
  }
  if (actions.length) showNoteContext(ev.clientX, ev.clientY, actions);
});

$('btn-note-save').addEventListener('click', async () => {
  if (!state.card || !state.card.word) { toast('还没有单词'); return; }
  try {
    await api('/api/notes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ word_id: state.card.word.id, content: noteToMd() }),
    });
    state.noteDirty = false;
    toast('笔记已保存');
  } catch (e) {
    toast('保存失败：' + e.message);
  }
});
$('btn-clear-notes').addEventListener('click', async () => {
  const bookId = Number($('clear-book').value);
  const listNo = Number($('clear-list').value);
  if (!bookId) { toast('请先选择单词书'); return; }
  if (!confirm('确定清空所选范围的笔记？（不可恢复）')) return;
  try {
    await api('/api/notes/clear', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ book_id: bookId, list_no: listNo || 0 }),
    });
    toast('笔记已清空');
    loadManage();
  } catch (e) {
    toast('清空失败：' + e.message);
  }
});

$('btn-export-notes').addEventListener('click', async () => {
  try {
    const bookId = $('export-book').value;
    const listNo = $('export-list').value;
    let url = '/api/export/notes?';
    if (bookId) url += 'book_id=' + encodeURIComponent(bookId) + '&';
    if (listNo) url += 'list_no=' + encodeURIComponent(listNo);
    const res = await fetch(url);
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      throw new Error(d.detail || '导出失败');
    }
    const blob = await res.blob();
    const cd = res.headers.get('Content-Disposition') || '';
    let fname = 'KTRT_笔记.md';
    const m = cd.match(/filename\*=UTF-8''([^;]+)/i) || cd.match(/filename="?([^";]+)"?/i);
    if (m) fname = decodeURIComponent(m[1]);
    const objUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = objUrl;
    a.download = fname;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(objUrl);
    toast('笔记已导出：' + fname);
  } catch (e) {
    toast(e.message);
  }
});

/* ---------- 杀词 ---------- */
let chg = { mode: 'word', q: [], i: 0, wrong: [], correct: 0, removed: [], bookId: 0, listNo: 0, mistake: false, active: false };

function refreshChallengeBooks() {
  ['chg-book', 'chg-mbook'].forEach((id) => {
    const s = $(id);
    if (!s) return;
    s.innerHTML = state.books.map((b) => `<option value="${b.id}">${escapeHtml(b.name)}</option>`).join('');
  });
  if (state.books.length) {
    $('chg-book').value = state.books[0].id;
    $('chg-mbook').value = state.books[0].id;
    loadChallengeLists();
    loadMistakeLists();
  }
}

async function loadChallengeLists() {
  const bookId = Number($('chg-book').value);
  if (!bookId) { $('chg-list').innerHTML = ''; return; }
  const meta = await api(`/api/books/${bookId}/lists`);
  $('chg-list').innerHTML = meta.map((l) => `<option value="${l.list_no}">Word List ${l.list_no}</option>`).join('');
}

async function loadMistakeLists() {
  const bookId = Number($('chg-mbook').value);
  const box = $('chg-mlists');
  if (!bookId) { box.innerHTML = ''; return; }
  const lists = await api(`/api/mistakes/lists?book_id=${bookId}`);
  box.innerHTML = lists.length
    ? lists.map((l) => `<label><input type="checkbox" value="${l.list_no}"> WL${l.list_no}(${l.c})</label>`).join('')
    : '<span style="color:var(--muted);font-size:13px">暂无错题</span>';
}

function setChallengeMode(mode) {
  chg.mode = mode;
  $('chg-mode-word').classList.toggle('active', mode === 'word');
  $('chg-mode-mistake').classList.toggle('active', mode === 'mistake');
  $('chg-word-panel').classList.toggle('hidden', mode !== 'word');
  $('chg-mistake-panel').classList.toggle('hidden', mode !== 'mistake');
  $('chg-stage').classList.add('hidden');
  $('chg-result').classList.add('hidden');
}

function resetChallengeState() {
  chg.active = false;
  chg.q = []; chg.i = 0; chg.wrong = []; chg.correct = 0; chg.removed = [];
  document.body.classList.remove('chg-focus');
  $('chg-stage').classList.add('hidden');
  $('chg-result').classList.add('hidden');
}

function showChallengeQuestion() {
  if (chg.i >= chg.q.length) { finishChallenge(); return; }
  const q = chg.q[chg.i];
  $('chg-progress').textContent = `${chg.i + 1} / ${chg.q.length}`;
  $('chg-fill').style.width = (chg.i / chg.q.length * 100) + '%';
  const opts = q.options.map((o, idx) => `<button class="opt" data-idx="${idx}">${escapeHtml(o)}</button>`).join('');
  $('chg-question').innerHTML = `<div style="font-size:28px;font-weight:800;margin-bottom:14px">${escapeHtml(q.word)}</div>${opts}`;
  $('chg-question').querySelectorAll('.opt').forEach((b) => {
    b.addEventListener('click', () => answerChallenge(q, Number(b.dataset.idx), b));
  });
}

function answerChallenge(q, idx, btn) {
  const correct = idx === q.correct;
  const btns = $('chg-question').querySelectorAll('.opt');
  btns.forEach((x) => x.disabled = true);
  btns[q.correct].classList.add('right');
  if (correct) {
    chg.correct++;
  } else {
    btn.classList.add('wrong');
    chg.wrong.push(q.word_id);
    if (!chg.mistake) {
      api('/api/mistakes/add', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ word_id: q.word_id }),
      }).catch(() => {});
    }
  }
  if (chg.mistake && correct) {
    const bar = document.createElement('div');
    bar.style.cssText = 'margin-top:12px;display:flex;gap:8px';
    bar.innerHTML = '<button class="btn" id="chg-keep">保留</button><button class="btn danger" id="chg-remove">移出错题本</button>';
    btn.parentElement.appendChild(bar);
    $('chg-remove').addEventListener('click', () => { chg.removed.push(q.word_id); chg.i++; showChallengeQuestion(); });
    $('chg-keep').addEventListener('click', () => { chg.i++; showChallengeQuestion(); });
    return;
  }
  chg.i++;
  setTimeout(showChallengeQuestion, correct ? 220 : 340);
}

async function finishChallenge() {
  chg.active = false;
  document.body.classList.remove('chg-focus');
  $('chg-stage').classList.add('hidden');
  const res = $('chg-result');
  res.classList.remove('hidden');
  if (!chg.mistake) {
    const r = await api('/api/challenge/result', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ book_id: chg.bookId, list_no: chg.listNo, wrong_ids: chg.wrong, total: chg.q.length, correct: chg.correct }),
    });
    res.innerHTML = `<p class="ok">本轮 ${chg.correct} / ${chg.q.length}，历史最高 ${r.best}</p><p style="font-size:13px;color:var(--muted)">答错的词已自动标为「不熟悉」并进入错题本</p>`;
  } else {
    await api('/api/mistakes/result', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ removed_ids: chg.removed }),
    });
    res.innerHTML = `<p class="ok">本轮答对 ${chg.correct} / ${chg.q.length}，移出错题本 ${chg.removed.length} 个</p>`;
  }
  loadMistakeLists();
}

async function startWordChallenge() {
  chg.mistake = false;
  chg.bookId = Number($('chg-book').value);
  chg.listNo = Number($('chg-list').value);
  if (!chg.bookId || !chg.listNo) { toast('请选择单词书和 List'); return; }
  const r = await api(`/api/challenge?book_id=${chg.bookId}&list_no=${chg.listNo}`);
  if (!r.questions.length) { toast('该 List 没有可闯关的单词'); return; }
  chg.q = r.questions; chg.i = 0; chg.wrong = []; chg.correct = 0;
  chg.active = true;
  document.body.classList.add('chg-focus');
  $('chg-result').classList.add('hidden');
  $('chg-stage').classList.remove('hidden');
  showChallengeQuestion();
}

async function startMistakeChallenge() {
  chg.mistake = true;
  chg.bookId = Number($('chg-mbook').value);
  const listNos = [...$('chg-mlists').querySelectorAll('input:checked')].map((x) => Number(x.value));
  if (!listNos.length) { toast('请勾选至少一个 List'); return; }
  const r = await api('/api/mistakes/start', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ book_id: chg.bookId, list_nos: listNos }),
  });
  if (!r.questions.length) { toast('所选 List 没有错题'); return; }
  chg.q = r.questions; chg.i = 0; chg.wrong = []; chg.correct = 0; chg.removed = [];
  chg.active = true;
  document.body.classList.add('chg-focus');
  $('chg-result').classList.add('hidden');
  $('chg-stage').classList.remove('hidden');
  showChallengeQuestion();
}

$('chg-mode-word').addEventListener('click', () => setChallengeMode('word'));
$('chg-mode-mistake').addEventListener('click', () => setChallengeMode('mistake'));
$('chg-book').addEventListener('change', loadChallengeLists);
$('chg-mbook').addEventListener('change', loadMistakeLists);
$('chg-start-word').addEventListener('click', startWordChallenge);
$('chg-start-mistake').addEventListener('click', startMistakeChallenge);
$('chg-exit').addEventListener('click', () => { resetChallengeState(); setChallengeMode(chg.mode); });

/* ---------- 启动 ---------- */
init();
