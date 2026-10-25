# FuckAIWords

可移植的中文“去 AI 味”Agent、100 问评测与人工纠正工具。

减少客服套话、空泛复述、固定起手和机械接梗，保留原有性格、事实、工具能力与权限边界。可以直接给能读文本的 AI 加载，也可以接入已有 bot；不要求伪装真人。

## 开始使用

- **直接给 AI 使用**：复制 [AGENT.md](AGENT.md) 的全文到对话中。有文件读取能力的 AI 可以直接读取整个目录，从 `AGENT.md` 开始。
- **接入已有 bot**：将 [prompts/runtime.md](prompts/runtime.md) 合入现有系统提示的表达层，保留工具协议与权限，合并重复或冲突规则。
- **作为 skill 使用**：把本仓库复制为 `deai-dialogue`，放入目标环境的 skills 目录，调用 `$deai-dialogue`。
- **下载整包**：[portable-deai-agent.zip](portable-deai-agent.zip)。解压后即可在本地使用。

完整说明见 [开始使用.md](开始使用.md)。不同平台对提示词的优先级和上下文保留方式不同，本包不承诺所有平台都能自动安装。

## 100 问与人工纠正

仓库包含 100 题，十类各十题，覆盖闲聊、情绪、纠错、技术求助、工具回执、身份归属、格式要求、参与边界及连续会话。

已经使用配置的 `deepseek-chat` 加载本包表达规则，实际采集 **100/100** 个结果。**全部待人工审核**，没有人工评分或通过结论。这是隔离模型测试，未通过生产 QQ 的完整角色、真实工具或发送链路。

下载或克隆后，在本地浏览器打开 [人工审核.html](人工审核.html)。GitHub 文件预览不会运行审核页面。逐条选择原句通过、人工纠正或拒绝，填写评分、修改原因和适用范围，再由实际审核人导出 `human-review.json`。

需要 Python 3.10+，采集和编译只用标准库：

```sh
python scripts/deai.py verify
python scripts/deai.py compile --run runs/20261025-134704-d943f7 --review human-review.json --out compiled/v1
```

编译生成修正版 `runtime.md`、全部接受样本及纠正前后记录。未审或拒绝的条目不会进入正式验收结果；分批整理可显式使用 `--partial`。这只生成提示词和场景示例，不会训练模型权重或自动部署到 bot。

重新采集时，通过当前终端环境变量提供 `DEAI_BASE_URL`、`DEAI_MODEL`、`DEAI_API_KEY`，然后执行：

```sh
python scripts/deai.py collect
```

非兼容 API、网页 bot 或其他通道可导入其真实输出，格式见 [人工审核流程](references/人工审核流程.md)。原始回答、人工修正版和审核结果分开保存，AI 不得替人签认。

## 目录

| 位置 | 用途 |
| --- | --- |
| [AGENT.md](AGENT.md) / [SKILL.md](SKILL.md) | 通用 Agent 与 skill 入口 |
| [config/style.json](config/style.json) | 表达偏好、采集参数和审核门槛 |
| [evaluation/questions.jsonl](evaluation/questions.jsonl) | 100 题及审核考点，考点不送入被测模型 |
| [runs/20261025-134704-d943f7](runs/20261025-134704-d943f7) | 本轮真实输出、上下文、重试记录和哈希 |
| [runtime/quality.mjs](runtime/quality.mjs) | 可选的纯观察适配器，默认不删句、不拦截 |
| [references](references) | 接入、参数、人工审核及验证说明 |
| [evidence](evidence) | 提取来源、哈希与源码快照 |

可选观察器需要 Node.js 18+。离线审核页没有 CDN、后端或网络上传。

```sh
python scripts/test_workflow.py
node scripts/test_observer.mjs
```

已完成 11 项隔离流程测试、观察器不变性检查、审核页 DOM 交互检查和解压迁移验证。实际浏览器截图验收尚未完成；详情见 [交付验证](references/交付验证.md)。

来源与原项目许可见 [ATTRIBUTION.md](ATTRIBUTION.md)。仓库不含 API 密钥、真实聊天存档、账号配置或模型权重。
