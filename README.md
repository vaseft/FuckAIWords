# FuckAIWords

可移植的中文「去 AI 味」Agent：载入后**先探测本机可接入的 bot 或 AI**，问清目标，装一份表达层，用一百问采集真实回答，经**人工审核**后把纠正回填到目标。

减少客服套话、空泛复述、固定起手和机械接梗，保留原有性格、事实、工具能力与权限边界。不要求伪装真人，也不宣称能通过某个检测器。

## 30 秒开始

**只需要聊天窗口**：把 [AGENT.md](AGENT.md) 全文贴进去，然后说「帮我接入我的 bot」。它会先问清目标，再给步骤。

**有文件工具的 AI**（Claude Code、Codex、Cursor、NewMax 等）：克隆本仓库，然后对它说：

> 先读 AGENT.md，按流水线执行：探测本机可接入的 bot/AI → 缺信息就问我 → 装配 → 一百问 → 人工审核 → 回填 → 复测。

**作为 skill**：把整个目录复制为 `deai-dialogue`，放进宿主的 skills 目录（如 `~/.newmax/skills/`、`~/.claude/skills/`），再调用 `$deai-dialogue`。

**离线整包**：[portable-deai-agent.zip](portable-deai-agent.zip)，解压即用。

## 流水线

```text
探测 → 问询 → 装配 → 提问 → 人工审核 → 回填 → 复测
```

| 阶段 | 做什么 | 命令 |
| --- | --- | --- |
| 探测 | 扫描本机 AI 客户端、bot 项目、本地模型端口、环境变量线索。只读，密钥只报是否设置 | `python scripts/deai.py probe --root <项目根>` |
| 问询 | 候选为 0 / 多个、缺提示入口、缺接口、要写文件权限时问用户 | 读 `probe/questions-for-user.md` |
| 装配 | 只加一份表达层，标记块幂等、自动备份、可回滚 | `python scripts/deai.py install --target <提示文件> --dry-run` |
| 提问 | 用**装配后的完整提示**向目标提一百问 | `python scripts/deai.py collect --system-file <emit 文件>` |
| 人工审核 | 由人逐条通过 / 纠正 / 拒绝并签认 | 打开 `人工审核.html` |
| 回填 | 编译人工结论并写回目标 | `python scripts/deai.py apply --run <runs/...> --review <human-review.json> --out compiled/v1 --target <提示文件>` |
| 复测 | 用回填后的表达层再采集一轮，对比两轮审核 | 再跑一次 `collect` |

`python scripts/deai.py status` 随时查看当前位置；它只读文件产物，**不会推断人工审核通过**。

## 装配方式

| 目标 | 模式 |
| --- | --- |
| 文本提示词 `.md` / `.txt` | `--mode marker`（默认），维护唯一的 `<!-- deai:begin … --> … <!-- deai:end -->` 块 |
| JSON 配置字段 | `--mode json-path --json-path persona.roleText`，只改该字段 |
| skill 目录 | 直接复制整个目录为 `deai-dialogue` |
| 整份替换 | `--mode replace --force`，仅用户明确要求时 |

写入前自动备份到 `backups/`，记录在 `install-state.json`，回滚：`python scripts/deai.py rollback --target <文件>`。

详细规则见 [装配与回填](references/装配与回填.md)。

## 一百问与人工纠正

仓库包含 100 题，十类各十题，覆盖日常接话、情绪、纠错、技术求助、工具回执、身份归属、格式要求、参与边界和连续会话。审核考点（`focus`）不会送入被测模型。

已用配置的 `deepseek-chat` 加载本包表达规则，实际采集 **100/100**。**全部待人工审核**，没有人工评分或通过结论。这是隔离模型测试，未接入生产 QQ 的完整角色、真实工具或发送链路。

在本地浏览器打开 [人工审核.html](人工审核.html)（GitHub 预览不会运行页面）。逐条选择原句通过 / 人工纠正 / 拒绝，填写评分、原因、适用范围，由**实际审核人**导出 `human-review.json`。

需要 Python 3.10+，采集和编译只用标准库：

```sh
python scripts/deai.py verify
python scripts/deai.py apply --run runs/20261025-134704-d943f7 --review human-review.json --out compiled/v1 --target <提示文件>
```

重新采集时通过终端环境变量提供接口，密钥不落盘：

```sh
export DEAI_BASE_URL="https://你的服务地址/v1"
export DEAI_MODEL="你的模型名"
export DEAI_API_KEY="你的密钥"
python scripts/deai.py collect
```

非兼容 API、网页 bot 或纯对话环境可导入真实输出，格式见 [人工审核流程](references/人工审核流程.md)。

## 目录

| 位置 | 用途 |
| --- | --- |
| [AGENT.md](AGENT.md) / [SKILL.md](SKILL.md) | Agent 主指令与 skill 入口 |
| [scripts/probe.py](scripts/probe.py) | 本机 bot/AI 探测，输出候选与待问询清单 |
| [scripts/deai.py](scripts/deai.py) | 采集、导入、审核页、编译、装配、回填、状态 |
| [config/style.json](config/style.json) | 表达偏好、采集参数、审核门槛 |
| [evaluation/questions.jsonl](evaluation/questions.jsonl) | 100 题及审核考点 |
| [runs/20261025-134704-d943f7](runs/20261025-134704-d943f7) | 本轮真实输出、上下文、重试记录和哈希 |
| [runtime/quality.mjs](runtime/quality.mjs) | 可选纯观察器，默认不删句、不拦截 |
| [references](references) | 接入、装配回填、人工审核、来源与验证 |
| [evidence](evidence) | 提取来源、哈希与源码快照 |

可选观察器需要 Node.js 18+。离线审核页没有 CDN、后端或网络上传。

```sh
python scripts/test_workflow.py
node scripts/test_observer.mjs
```

## 边界与安全

- 不代替人签认，不把模拟答案当实测，不把 AI 改写当人工结论。
- 不改目标的工具协议、权限、记忆和发送链路，只加一份表达层。
- 密钥只从环境变量或目标自身配置读取，不写入本包、不打印、不提交。
- 探测与装配都有拒绝条件：不写代码文件，不整份覆盖，不猜 JSON 结构，命中疑似密钥就停。
- 回填改变的是上下文示例，不训练模型权重，不自动部署到远端服务。

来源与原项目许可见 [ATTRIBUTION.md](ATTRIBUTION.md)。仓库不含 API 密钥、真实聊天存档、账号配置或模型权重。
