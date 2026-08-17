# data 目录说明

此目录存放用户本地数据，**不会**被提交到 GitHub：

- `ktrt.db`：学习记录（进度/状态/收藏/造句/设置）
- `dictionary.db`：ECDICT 离线词典
- `*.xlsx`：各单词书扩展词库
- `reference_phrasal_verbs.json`：动词短语参考素材
- `config.json`：AI API Key 等配置

克隆项目后，请自行准备词库：

1. 通过应用“导入”页导入你的单词书 Excel（格式见 `docs/Excel生成教程.md`）；
2. 如需离线查词，把 ECDICT 的 `ecdict.csv`（约 66MB）放入本目录，应用首次启动会自动导入。
