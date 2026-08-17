# KTRT（KillTimeRecitationTool）设计文档

开发者：HoweyYueng ｜ 形态：本地网页应用 ｜ 启动：`KTRT.bat`

## 架构

```
浏览器前端（原生 HTML/CSS/JS，无构建）  ←→  FastAPI 后端（localhost:8000）
                                              │
                              ┌───────────────┼────────────────┐
                          SQLite 学习库    ECDICT 词典库     edge-tts 音频缓存
                       （词书/单词/状态/造句）  （离线查词）      （TTS 缓存）
                              │
                          DeepSeek 等 AI（造句/配置化）
```

## 数据模型

- `word_books`：单词书（名称、语言、来源）。语言决定 TTS 朗读语言（英语书只读英语）。
- `words`：单词条目（book_id、list_no、seq、word、phonetic、meaning、collocations、phrases、synonyms、antonyms、root_words）。
- `word_status`：每词状态（familiar/unfamiliar/favorite/learned），四者独立可组合。
- `sentences`：造句收藏（word_id、prompt、sentence、translation、created_at）；每词最多 3 条，超出自动删除最旧。
- `settings`：AI 配置（api_key、base_url、model、vendor）、TTS 提供方。
- `dictionary`（独立 dictionary.db）：ECDICT 全量离线词典，用于任意词查词。

## 核心页面

1. **学习页**：选书 → 选 List → 进度条（已背/总数）；单词卡（加粗单词、音标、词性释义、搭配、短语、同义词、反义词、同根词）；按钮：朗读/背/熟悉/不熟悉/收藏/上一个/下一个；造句区（指令框自动清空、最多 3 句、展示已有句子与翻译、可删除）。
2. **管理页**：按 熟悉/不熟悉/收藏/已背/造句 筛选；删除记录、取消收藏、清空单个 List 进度、删除造句。
3. **导入页**：上传【】格式 Excel，预览并导入为新单词书。
4. **设置页**：AI 厂商下拉（ds/db/gpt/Gemini/Claude/qw/grok）+ Base URL + 模型 + API Key；TTS 提供方（edge-tts / 浏览器语音）。

## AI 造句

输入中文提示词 → 调用配置的 AI（OpenAI 兼容接口；Claude 走 Anthropic 接口）→ 返回英文句子与中文翻译 → 前端高亮目标词 → 存入造句收藏。

## 朗读（TTS）

默认 edge-tts（免费、联网、支持英/法）；按单词书语言选择音色；选中内容即点即读。备选：浏览器 Web Speech API（离线兜底）。

## 导入格式（【】列名）

`【单词】【音标】【词性释义】【搭配】【短语】【同义词】【反义词】【同根词】【List】【语言】【单词书】`；多值字段以「；」分隔。

## 内存

常驻约 150–250MB；峰值（导入/批量生成）约 300–400MB。
