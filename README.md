# KTRT（KillTimeRecitationTool）

高自由度的本地背单词软件：一页一词、按单元/单词书管理、AI 自定义造句、多格式导入、离线词典、多语言朗读。开发者：HoweyYueng。

## 核心特色（创新点）

- **AI 自定义造句**：输入中文提示，AI 用当前单词造句并高亮目标词，存入个人造句收藏（每词最多 3 句）。
- **高自由度词库**：支持 `【】格式 Excel / CSV / 纯文本` 导入任意单词书，多字段（搭配、短语、同反义词、同根词）自动补全，学习记录按书隔离。
- **离线可用**：ECDICT 离线词典（77 万词条）查词、SQLite 本地存储。
- **可扩展**：AI 厂商/模型/Key 可配置（DeepSeek、豆包、GPT、Gemini、Claude、千问、Grok 等），edge-tts 多语言朗读（英/法）。

## 快速开始

环境：Python 3.10+

```bash
# Windows：直接双击 KTRT.bat（首次运行自动建虚拟环境并安装依赖）
# 或手动：
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python launcher.py
```

启动后浏览器打开 http://127.0.0.1:8000。

> **API Key**：本项目不内置、不提交任何 API Key。首次使用请在「设置」页填写你自己的 Key，并可自由切换厂商/模型。

## 项目结构

```
KTRT.bat            一键启动
launcher.py         启动器（准备词库→启动服务→打开浏览器）
backend/            FastAPI 后端（数据库/导入/AI/朗读）
frontend/static/    前端页面（原生 HTML/CSS/JS）
data/               本地数据（不入库，见 data/README.md）
docs/               设计文档、路线图、教程
```

## 词库导入

把任意单词书整理成标准 Excel 后即可导入。列格式、AI 提取提示词见 [docs/Excel生成教程.md](docs/Excel生成教程.md)，程序操作见 [docs/使用教程.md](docs/使用教程.md)。

## 路线图

校验语料库 → LLM Wiki 知识图谱 → exe 桌面版 → 网站部署 → 微信小程序，详见 [docs/TO_BE_CONTINUED.md](docs/TO_BE_CONTINUED.md)。

## 许可

MIT License，见 [LICENSE](LICENSE)。

> 说明：`data/` 目录（含词库与 API Key）不随仓库分发，请自行准备词库。
