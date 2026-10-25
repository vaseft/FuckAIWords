---
name: deai-dialogue
description: 载入后自动探测本机可接入的 bot 或 AI，装配去 AI 味表达层，用一百问采集真实回答，经人工审核把纠正回填目标 bot；也可直接按规则改善中文表达。适用于去 AI 味、接入现有 bot、评测表达、整理人工纠正。
---

读取 [AGENT.md](AGENT.md) 并按其执行。不要停在讲解规则：只要用户的目标是接入 bot、做评测或回填，就按下面的流水线往下走。

**人设优先**：只追加表达层，不改目标原有的人设、世界观、关系、口癖、能力边界和禁区；冲突时以目标为准。默认用 `marker` / `json-path` 追加，`replace` 仅限用户明确要求。

## 先分流

| 用户意图 | 动作 |
| --- | --- |
| 改一句话、问表达建议 | 直接按 AGENT.md 的表达规则回答，不跑流水线，不汇报“已去 AI 味” |
| 接入我的 bot / 让 bot 少点 AI 味 | 进入流水线 |
| 跑一百问 / 整理人工反馈 / 回填 | 进入流水线 |

## 流水线

```text
探测 → 问询 → 装配 → 提问 → 人工审核 → 回填 → 复测
```

**1. 探测（只读）**

```sh
python scripts/deai.py probe --root <目标项目根目录>
# 无网络环境加 --no-network；需要更多候选可重复 --root
```

产物：`probe/survey-*.json`、`probe/questions-for-user.md`。密钥只报“是否设置”，不会打印值。

**2. 问询**：候选为 0、候选多于 1、缺提示词入口、缺模型接口、要写全局文件、要动别人项目时，**先问用户**，不要猜。问询清单直接读 `probe/questions-for-user.md`。

**3. 装配（先 dry-run）**

```sh
python scripts/deai.py install --target "<目标提示词文件>" --dry-run
python scripts/deai.py install --target "<目标提示词文件>" --emit "<装配后提示.txt>"
# JSON 配置里的字段：--mode json-path --json-path persona.roleText
# 回滚：python scripts/deai.py rollback --target "<目标提示词文件>"
```

装配前先读目标原人设，并告诉用户“将保留哪些设定、只追加什么”。只维护一个 `<!-- deai:begin … --> … <!-- deai:end -->` 标记块，重复执行是幂等的；自动备份、自动回滚；拒绝改写 `.js/.py` 等代码文件。结果里的 `preserved_original_chars` 与 `persona_policy` 要如实转述。

**4. 提问**：用装配后的完整提示向目标提问，而不是只发本包的 runtime.md。

```sh
python scripts/deai.py collect --system-file "<装配后提示.txt>"
# 接口：DEAI_BASE_URL / DEAI_MODEL / DEAI_API_KEY，或 --qq-config <目标配置>
```

本包**不含作者采集的回答**，必须在这个目标上现采。只想看题可用 `python scripts/deai.py template` 生成 `100问预览.html`（只有问题，不能导出审核）。

**5. 人工审核**：打开该运行目录下的 `runs/<时间>/人工审核.html`，由**人**逐条通过 / 纠正 / 拒绝，填评分、原因、适用范围、审核人。AI 只能标疑点、给候选改写，且必须标为建议。

**6. 回填**：编译人工结论并写回目标。

```sh
python scripts/deai.py apply --run "<runs/...>" --review "<human-review.json>" --out "compiled/v1" --target "<目标提示词文件>"
```

**7. 复测**：用回填后的表达层再采集一轮，对比两轮审核；不宣称普遍改善。

## 随时可查

```sh
python scripts/deai.py status
```

只反映文件产物；人工审核结论不会被程序推断。

## 边界

- 不代替人签认，不把模拟答案当实测，不把 AI 改写当人工结论。
- 不改目标的工具协议、权限、记忆和发送链路，只加一份表达层。
- 人设优先：不改写目标原有的角色设定；本包条目与目标冲突时跳过该条。
- 密钥只从环境变量或目标自身配置读取，不写入本包、不打印、不提交。
- 找不到目标就说明缺什么，不要编一个能跑通的假流程。
