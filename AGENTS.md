# 本包的维护约定

先读 `AGENT.md`。这是独立的中文表达工程及人工审核工具，不依赖来源 QQ 项目。

## 分离

- 运行指令、维护指令和评测考点分开。不要把整个工程目录注入目标 bot。
- 100 条题目、原始输出、人工修正版分开保存。AI 不得替人签认或自动填通过。
- 成功回答保持原样；重试留记录。审核绑定题库、提示词、运行编号和回答哈希。
- **仓库只发布问题，不发布任何已采集回答**：`runs/`、根目录 `人工审核.html`、`最新运行.json` 都在 `.gitignore`，不得提交。

## 探测与装配

- `scripts/probe.py` 只读：不修改目标，不发送密钥，不写入目标项目。密钥环境变量只记录 `present`，地址只保留 scheme+host。
- `install` / `apply` 必须保持：标记块唯一、重复执行幂等、写入前备份、可 `rollback`、拒绝写代码文件、命中疑似密钥即停。
- 不整份覆盖目标系统提示；`replace` 必须显式 `--force`，且结果要保留 `persona_policy=replace-all` 与 `warning`。
- **人设优先**：原有人设、世界观、关系、口癖、能力边界和禁区必须保留；安装结果要如实报告 `preserved_original_chars`。本包条目与目标冲突时跳过该条。
- `--emit` 导出的是装配后的完整字段内容，采集用它才是“向装了表达层的目标提问”。
- 新增写入目标类型时，先加拒绝条件，再考虑便利性。

## 数据边界

- 不读取或打包聊天存档、密钥、真实群号、账号或角色私有资料。用户指定配置文件仅在发请求时读取，不能复制进本包或打印密钥。
- `probe/`、`backups/`、`install-state.json`、`compiled/`、`human-review.json` 都是本机产物，已在 `.gitignore`，不得提交。

## 实现约束

- 可移植脚本只用 Python 标准库；观察器可选使用 Node.js。所有路径以本包位置或显式参数为基准。
- 新增 CLI 子命令时同步更新 `SKILL.md`、`AGENT.md`、`README.md` 和 `references/`，不要只改代码。
- 修改采集、导入、装配或审核逻辑后，运行 `python scripts/test_workflow.py`，再运行 `python scripts/deai.py verify`。
- 不要声称自动测试证明了自然度或人工审核结果。
