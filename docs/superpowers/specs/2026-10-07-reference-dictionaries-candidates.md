# 离线参考词典 / 学科词库 候选备案

日期：2026-10-07　用途：0.2.2「离线参考库」与后续学科词库的选型依据

## 收录原则

1. **离线可用**：能落成本地文件（SQLite / JSON / TSV），运行时不联网。
2. **许可可查**：优先公有领域 / CC0 / CC BY / MIT；CC BY-SA 可用但要致谢并注意派生数据的传染性；「仅供个人使用」的源只做本机自行导入，不进 GitHub。
3. **有明确词表结构**：词条 + 词性 / 领域 / 释义至少占一项，能塞进现有 `dict` 表或参考库表。
4. 每个源记录：领域 / 许可 / 体积 / 语言 / 获取方式 / 适配成本 / 验证状态。

分发三级：**内置**（随安装包）→ **一键下载**（GitHub 资源，同词书资源）→ **自行导入**（本机文件，许可不明时用这一档）。

## 通用 / 词性层（0.2.2 先用这批）

| 源 | 内容 | 许可 | 体积 | 验证 |
| --- | --- | --- | --- | --- |
| ECDICT（已内置） | 词性标记、英文定义、中文释义、词频（bnc/frq）、考试标签、词形 `exchange` | 仓库 MIT，数据来自 stardict 系 | 已内置（约 107 MB） | 在用 |
| **Moby Part-of-Speech II** | 约 25 万词的词性表（n/v/adj/adv…） | 公有领域（Gutenberg #3201） | 约 2–3 MB | ✅ URL 可达（`gutenberg.org/files/3201/3201-0.txt`） |
| **WordNet 3.0（含 gloss）** | n/v/adj/adv 词元 + **英文原文释义** + 同义/反义 + 义项关系 | WordNet License（宽松，保留声明） | 约 10 MB（NLTK 镜像 `wordnet.zip`） | ✅ URL 可达（`raw.githubusercontent.com/nltk/nltk_data/gh-pages/packages/corpora/wordnet.zip`） |
| English WordNet（备选来源） | 同上，持续维护版 | CC BY 4.0 | 约 10–15 MB | ✅ GitHub 可达 |
| Wiktionary / Kaikki 离线转储 | 词性 + 义项 + 专有名词 + 词组（覆盖最全） | CC BY-SA（需致谢） | 一次性下载 GB 级，抽索引后十～几十 MB | 待试算 |

## 学科词库候选（后续按需接入）

| 领域 | 源 | 语言 | 许可 | 状态 |
| --- | --- | --- | --- | --- |
| 综合术语（中文） | 术语在线 termonline.cn（全国科技名词审定委员会） | 中 | 需确认（个人查阅免费，批量使用待授权） | ✅ 站点可达 |
| 综合术语（多语言） | Wikidata / Wikipedia 转储 | 多语言 | CC0 / CC BY-SA | ✅ 可达（`dumps.wikimedia.org`） |
| 通用百科术语 | 中文维基 / 维基词典转储 | 中 | CC BY-SA | ✅ 可达 |
| 医学 | MeSH（NLM） | 英（中文译名需另找） | 美国政府作品，多可自由使用（需核对） | ✅ 入口可达 |
| 医学（中文） | 中国医学科学院 MeSH 中文版 / 术语在线医学库 | 中 | 需确认 | 待确认 |
| 生物化学 | Gene Ontology（术语 + 定义） | 英（含多语言映射） | CC BY 4.0 | ✅ 可达 |
| 蛋白质 / 基因 | UniProt Keywords；HGNC 基因命名 | 英 | CC BY 4.0 / CC0 | ✅ UniProt 可达 |
| 数学 | NIST DLMF（特殊函数与数学符号，含定义） | 英 | NIST 公有领域 | ✅ 可达 |
| 数学（备选） | PlanetMath | 英 | CC BY-SA | 待验证 |
| 物理 / 常数 | NIST CODATA；PDG 粒子物理综述 | 英 | 公有领域 / 待确认 | 部分可达 |
| 计算机 / AI | GNOME / KDE / Mozilla 中文术语表；Microsoft Learn 术语页（文档多为 CC BY 4.0，逐页核对） | 中/英 | GPL/LGPL/MPL/CC BY | ✅ GNOME 中文团队可达 |
| 金融 | SEC Investor.gov 词表；美联储词表；XBRL 分类标准标签 | 英 | 美国政府公共领域 / 开放 | ✅ investor.gov 可达 |
| 机械 / 工程 | 暂无高质量开源源；建议走「术语在线 + 维基百科术语清单」或自建 | 中/英 | 视来源 | 待定 |
| 职场 / 通用商务 | 维基百科商务术语清单 + 自建表 | 中/英 | CC BY-SA / 自建 | 待定 |

## 落地顺序建议

1. **Tier 1（本次）**：ECDICT + Moby + WordNet 组成「词性增强包」，WordNet 顺带提供高阶学习者要的英文原文释义。
2. **Tier 2**：挑 1–2 个学科库跑通「下载 → 解析 → 参与检索」的完整链路（建议先医学 MeSH 或计算机微软/ GNOME 中文术语表）。
3. **Tier 3**：按需扩展（数学、物理、生化、金融、机械……），每个源都要过一遍许可与体积评估。
4. 所有源一律走同一个检索层（见「统一检索层」章节），避免多源并行后出现"搜不出来"。
