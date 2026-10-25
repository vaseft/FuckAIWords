#!/usr/bin/env python3
"""Survey local bots/AIs that can receive the expression layer.

Standard library only. Never prints or stores secret values: API keys are reported
as present/absent, endpoint URLs are reduced to scheme+host+port.

Exit codes: 0 = found at least one candidate, 3 = nothing found, 1 = error.
"""
import argparse
import datetime as dt
import http.client
import json
import os
from pathlib import Path
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]

# name -> what it is used for. Values are never printed.
SECRET_ENV = {
    "DEAI_API_KEY": "本包采集专用密钥",
    "OPENAI_API_KEY": "OpenAI 兼容接口密钥",
    "ANTHROPIC_API_KEY": "Anthropic 接口密钥",
    "DEEPSEEK_API_KEY": "DeepSeek 接口密钥",
    "MOONSHOT_API_KEY": "Moonshot/Kimi 接口密钥",
    "DASHSCOPE_API_KEY": "阿里云百炼接口密钥",
    "ZHIPU_API_KEY": "智谱接口密钥",
    "GEMINI_API_KEY": "Gemini 接口密钥",
    "GOOGLE_API_KEY": "Google 接口密钥",
    "QQ_AGENT_API_KEY": "QQ Agent 模型密钥",
}
ENDPOINT_ENV = [
    ("DEAI_BASE_URL", "DEAI_MODEL", "本包采集专用接口"),
    ("OPENAI_BASE_URL", "OPENAI_MODEL", "OpenAI 兼容接口"),
    ("DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL", "DeepSeek 接口"),
    ("OLLAMA_HOST", None, "本地 Ollama"),
    ("LMSTUDIO_HOST", None, "本地 LM Studio"),
]
DEFAULT_PORTS = [3210, 3001, 11434, 1234, 8000, 8080, 5000, 3000]
SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env", "dist", "build",
    ".next", ".cache", "runs", "probe", "compiled", "backups", "sticker-images",
    "sessions", "logs", ".idea", ".vscode", "site-packages",
}
PROMPT_NAMES = (
    "system.md", "system-prompt.md", "system-prompt.txt", "runtime.md",
    "conversation.md", "persona.md", "prompt.md", "AGENTS.md", "CLAUDE.md",
)
INSTALLABLE_SUFFIX = {".md", ".txt", ".json", ".jsonc", ".yaml", ".yml"}


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def safe_url(value):
    """Reduce an endpoint to scheme://host:port; drop path, query and credentials."""
    try:
        parsed = urllib.parse.urlparse(str(value).strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return ""
        port = ":%d" % parsed.port if parsed.port else ""
        return "%s://%s%s" % (parsed.scheme, parsed.hostname, port)
    except (ValueError, TypeError):
        return ""


def read_json(path, limit=2_000_000):
    try:
        raw = Path(path).read_bytes()
        if len(raw) > limit:
            raw = raw[:limit]
        return json.loads(raw.decode("utf-8-sig", errors="replace"))
    except (OSError, ValueError, UnicodeError):
        return None


def env_facts():
    hints = []
    for name, purpose in SECRET_ENV.items():
        value = os.environ.get(name)
        hints.append({
            "name": name,
            "kind": "secret",
            "purpose": purpose,
            "present": bool(value and value.strip()),
            "value": None,  # never expose
        })
    endpoints = []
    for base_name, model_name, purpose in ENDPOINT_ENV:
        base = os.environ.get(base_name, "")
        model = os.environ.get(model_name, "") if model_name else ""
        if base.strip() or model.strip():
            endpoints.append({
                "base_env": base_name,
                "model_env": model_name,
                "purpose": purpose,
                "base_hint": safe_url(base) or base.strip(),
                "model": model.strip() or None,
            })
    return {"hints": hints, "endpoints": endpoints}


def port_open(port, timeout=0.35):
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


def http_json(port, path, timeout=1.5):
    url = "http://127.0.0.1:%d%s" % (port, path)
    request = urllib.request.Request(url, headers={"User-Agent": "deai-probe/1.0"}, method="GET")
    try:
        with urllib.request.build_opener().open(request, timeout=timeout) as response:
            return json.load(response)
    except (urllib.error.HTTPError, urllib.error.URLError, http.client.HTTPException,
            OSError, ValueError, UnicodeError):
        return None


def probe_port(port):
    """Identify a local AI endpoint without sending credentials."""
    status = http_json(port, "/api/status")
    if isinstance(status, dict) and any(k in status for k in ("model", "onebot", "orchestrator", "persona")):
        model = status.get("model") or ""
        if isinstance(model, dict):
            model = model.get("name") or model.get("id") or ""
        return {
            "kind": "qq-agent-console",
            "label": "QQ Agent 控制台（127.0.0.1:%d）" % port,
            "port": port,
            "confidence": 0.92,
            "models": [str(model)] if model else [],
            "collect": {"method": "console-api", "base_hint": "http://127.0.0.1:%d" % port,
                        "note": "仅可读状态；提问需走其模型配置或外部通道"},
        }
    models = http_json(port, "/v1/models")
    if isinstance(models, dict) and isinstance(models.get("data"), list):
        names = [str(m.get("id")) for m in models["data"] if isinstance(m, dict) and m.get("id")]
        if names:
            return {
                "kind": "openai-compatible",
                "label": "OpenAI 兼容接口（127.0.0.1:%d）" % port,
                "port": port,
                "confidence": 0.9,
                "models": names[:12],
                "collect": {"method": "chat-completions",
                            "base_hint": "http://127.0.0.1:%d/v1" % port,
                            "model_hint": names[0]},
            }
    tags = http_json(port, "/api/tags")
    if isinstance(tags, dict) and isinstance(tags.get("models"), list):
        names = [str(m.get("name")) for m in tags["models"] if isinstance(m, dict) and m.get("name")]
        return {
            "kind": "ollama",
            "label": "Ollama（127.0.0.1:%d）" % port,
            "port": port,
            "confidence": 0.9,
            "models": names[:12],
            "collect": {"method": "chat-completions",
                        "base_hint": "http://127.0.0.1:%d/v1" % port,
                        "model_hint": names[0] if names else None,
                        "note": "Ollama 的 /v1 兼容层；也可用 /api/chat 适配"},
        }
    if port_open(port, 0.5):
        return {
            "kind": "unknown-http-service",
            "label": "本地 HTTP 服务（127.0.0.1:%d）" % port,
            "port": port,
            "confidence": 0.3,
            "models": [],
            "needs": ["确认该端口是否是需要改造的 bot；若是自定义协议，需要提供接口格式"],
        }
    return None


def prompt_candidates(project, limit=8):
    found = []
    for directory in ("prompts", ".", "config", "src"):
        base = project / directory
        if not base.is_dir():
            continue
        for name in PROMPT_NAMES:
            path = base / name
            if path.is_file() and path.stat().st_size < 400_000:
                found.append(path)
        if len(found) >= limit:
            break
    return found[:limit]


def inspect_project(path):
    """Return a candidate when the directory looks like an attachable bot/AI project."""
    # Protocol adapters (NapCat/OneBot implementations) host no expression layer.
    if any(part.lower() in {"napcat", "lagrange", "llonebot"} for part in path.parts[-3:]):
        return None
    evidence, config, install, collect = [], None, None, None
    orchestrator = path / "src" / "orchestrator.js"
    package = read_json(path / "package.json")
    has_plugins = (path / "plugins").is_dir()
    for name in ("data/config.json", "config.json", "config/config.json"):
        candidate = path / name
        if candidate.is_file():
            config, evidence = read_json(candidate), evidence + [name]
            break
    if orchestrator.is_file():
        evidence.append("src/orchestrator.js")
    if has_plugins:
        evidence.append("plugins/")
    package_blob = json.dumps(package, ensure_ascii=False).lower() if package else ""
    looks_bot = bool(
        ("onebot" in package_blob or "napcat" in package_blob or "-bot" in package_blob or '"qq"' in package_blob)
        or has_plugins
    )
    looks_qq_agent = bool(config and isinstance(config, dict)
                          and any(k in config for k in ("providers", "persona", "onebot", "snowluma"))
                          and orchestrator.is_file())
    looks_config_bot = bool(isinstance(config, dict) and any(
        k in config for k in ("persona", "providers", "systemPrompt", "system_prompt", "bot", "onebot")
    ))
    # Only treat an actual project root as a target; src/, data/ and fixture dirs are not.
    is_project_root = (path / "package.json").is_file() or (path / "pyproject.toml").is_file() or (path / ".git").exists()
    if not (looks_qq_agent or (is_project_root and (looks_bot or looks_config_bot))):
        return None
    kind = "qq-agent" if looks_qq_agent else "bot-project"
    label = path.name
    if isinstance(config, dict):
        persona = config.get("persona") if isinstance(config.get("persona"), dict) else {}
        role = persona.get("roleText") or persona.get("role") or ""
        api = config.get("api") if isinstance(config.get("api"), dict) else {}
        providers = config.get("providers") if isinstance(config.get("providers"), list) else []
        pid = str(api.get("provider") or "")
        provider = next((p for p in providers if isinstance(p, dict) and str(p.get("id")) == pid), {})
        has_key = bool(
            (api.get("apiKey") and str(api.get("apiKey")).strip())
            or (provider.get("apiKey") and str(provider.get("apiKey")).strip())
            or (config.get("dshProviderKeys") or {}).get(pid)
        )
        if looks_qq_agent and role:
            install = {
                "method": "json-path",
                "target": "data/config.json" if (path / "data/config.json").is_file() else "config.json",
                "json_path": "persona.roleText",
                "note": "只在该字段内维护 deai 标记块，保留角色其余设定与工具协议",
            }
        if api.get("baseUrl") and api.get("model"):
            collect = {
                "method": "chat-completions",
                "base_hint": safe_url(api.get("baseUrl")),
                "model_hint": str(api.get("model")),
                "has_key": has_key,
                "key_note": "密钥已在目标配置中；采集时只读，不复制不打印" if has_key else "目标配置未填密钥，需要用户提供",
            }
        if role:
            evidence.append("persona.roleText(%d 字)" % len(str(role)))
    prompts = prompt_candidates(path)
    if prompts:
        evidence.extend("prompts/" + p.name if p.parent.name == "prompts" else p.name for p in prompts[:4])
        if not install and kind == "bot-project":
            preferred = next((p for p in prompts if p.name in {"system.md", "system-prompt.md", "system-prompt.txt", "runtime.md"}), None)
            if preferred:
                install = {
                    "method": "marker",
                    "target": preferred.relative_to(path).as_posix(),
                    "note": "在系统提示文件中维护 deai 标记块；需用户确认这就是运行时加载的提示",
                }
    needs = []
    if not install:
        needs.append("目标项目的系统提示入口未确定；请指出实际加载的提示词文件")
    if not collect:
        needs.append("未找到可直接调用的模型接口；需要 base_url + model（密钥用环境变量提供）")
    return {
        "kind": kind,
        "label": label,
        "path": path.as_posix(),
        "confidence": 0.95 if kind == "qq-agent" else 0.6,
        "evidence": evidence,
        "install": install,
        "collect": collect,
        "needs": needs,
    }


def scan_projects(roots, max_depth=3):
    seen, found = set(), []
    for root in roots:
        root = Path(root).expanduser().resolve()
        if not root.is_dir():
            continue
        base_depth = len(root.parts)
        for current, dirs, _files in os.walk(root):
            current_path = Path(current)
            depth = len(current_path.parts) - base_depth
            dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS and not d.startswith(".git")]
            if depth > max_depth:
                dirs[:] = []
                continue
            if current_path.resolve() == ROOT:
                dirs[:] = []
                continue
            if current_path in seen:
                dirs[:] = []
                continue
            seen.add(current_path)
            item = inspect_project(current_path)
            if item:
                item["id"] = "project-%d" % (len(found) + 1)
                found.append(item)
                dirs[:] = []
    return sorted(found, key=lambda x: -x["confidence"])


def find_skill_hosts(roots):
    homes = [
        (Path.home() / ".newmax/skills", "NewMax"),
        (Path.home() / ".claude/skills", "Claude Code"),
        (Path.home() / ".codex/skills", "Codex"),
        (Path.home() / ".cursor/skills", "Cursor"),
    ]
    for root in roots:
        homes.append((Path(root).expanduser() / ".claude/skills", "当前项目 Claude Code"))
    found = []
    for home, host in homes:
        if not home.is_dir():
            continue
        installed = (home / "deai-dialogue" / "SKILL.md").is_file()
        found.append({
            "id": "skill-%d" % (len(found) + 1),
            "kind": "skill-host",
            "label": "%s skill 目录" % host,
            "path": home.as_posix(),
            "confidence": 0.85,
            "evidence": ["deai-dialogue 已安装" if installed else "可安装 skill"],
            "install": {"method": "copy-skill-dir", "target": (home / "deai-dialogue").as_posix(),
                        "installed": installed},
            "collect": None,
            "needs": [] if installed else ["确认可以写入该目录"],
        })
    return found


def find_global_instructions():
    candidates = [
        (Path.home() / ".claude/CLAUDE.md", "Claude Code 全局指令"),
        (Path.home() / ".codex/AGENTS.md", "Codex 全局指令"),
    ]
    found = []
    for path, label in candidates:
        if path.is_file():
            found.append({
                "id": "global-%d" % (len(found) + 1),
                "kind": "global-instruction",
                "label": label,
                "path": path.as_posix(),
                "confidence": 0.55,
                "evidence": ["%d 字节" % path.stat().st_size],
                "install": {"method": "marker", "target": path.as_posix(),
                            "note": "会影响该客户端的所有会话；需用户明确同意"},
                "collect": None,
                "needs": ["确认是否允许改写全局指令文件（会作用于所有项目）"],
            })
    return found


def build_questions(survey):
    items = []
    candidates = survey["candidates"]
    if not candidates:
        items.append({
            "id": "Q-target",
            "question": "本机没有找到可接入的 bot 或 AI。请提供其中一种：目标 bot 的提示词文件路径；模型接口 base_url + model（密钥设为环境变量）；或直接改用对话模式。",
            "options": ["提供提示词文件路径", "提供模型接口地址和模型名", "只做对话改写，不接入"],
        })
        return items
    actionable = [c for c in candidates if c.get("install")]
    if not actionable:
        items.append({
            "id": "Q-install-point",
            "question": "找到了目标，但无法确定系统提示入口。请指出运行时实际加载的提示词文件。",
            "options": [c["path"] for c in candidates[:4]],
        })
    elif len(actionable) > 1:
        items.append({
            "id": "Q-choose-target",
            "question": "发现多个可接入目标，请选择要先改造的一个。",
            "options": ["%s（%s）" % (c["label"], c["path"]) for c in actionable[:5]],
        })
    primary = sorted(actionable, key=lambda c: -c["confidence"])[0] if actionable else None
    if primary:
        for need in primary.get("needs", [])[:3]:
            items.append({
                "id": "Q-" + primary["id"] + "-need",
                "question": "%s：%s" % (primary["label"], need),
                "options": ["确认，可以继续", "先跳过这个目标"],
            })
    items.append({
        "id": "Q-reviewer",
        "question": "谁来做人工审核？审核结果必须由人签认，AI 不能代填。",
        "options": ["我自己逐条审核", "我找人代为审核"],
        "free_text": True,
    })
    return items


def summarize(survey):
    lines = ["本地可接入目标扫描", "=" * 40]
    if not survey["candidates"]:
        lines.append("未发现目标。")
    for candidate in survey["candidates"]:
        lines.append("[%s] %s" % (candidate["kind"], candidate["label"]))
        lines.append("    路径: %s" % candidate.get("path", "-"))
        if candidate.get("install"):
            lines.append("    装配: %s → %s" % (candidate["install"]["method"], candidate["install"].get("target", "-")))
        if candidate.get("collect"):
            collect = candidate["collect"]
            lines.append("    提问: %s %s %s" % (collect.get("method"), collect.get("base_hint") or "", collect.get("model_hint") or ""))
        for need in candidate.get("needs", []):
            lines.append("    待确认: %s" % need)
    lines.append("")
    lines.append("环境变量线索（密钥只报是否设置）:")
    for hint in survey["env"]["hints"]:
        if hint["present"]:
            lines.append("  ✓ %s — %s" % (hint["name"], hint["purpose"]))
    for endpoint in survey["env"]["endpoints"]:
        lines.append("  · %s → %s %s" % (endpoint["base_env"], endpoint["base_hint"], endpoint.get("model") or ""))
    if survey["questions"]:
        lines.append("")
        lines.append("需要向用户确认 %d 项，详见 questions-for-user.md" % len(survey["questions"]))
    return "\n".join(lines)


def render_questions(survey):
    out = ["# 需要你确认的事项", "", "载入去 AI 味 agent 后，按顺序回答即可：", ""]
    for index, item in enumerate(survey["questions"], 1):
        out.append("%d. **%s**" % (index, item["question"]))
        if item.get("options"):
            out.append("   - " + " / ".join(item["options"]))
        out.append("")
    out.append("回答后请人工确认：任何「审核通过」必须由人签认，AI 只能整理和标疑点。")
    return "\n".join(out)


def survey(roots, ports=None, network=True, timeout=0.35):
    """Build the survey structure. Read-only and secret-free by construction."""
    candidates = scan_projects(roots)
    candidates.extend(find_skill_hosts(roots))
    candidates.extend(find_global_instructions())
    if network:
        for port in (ports or DEFAULT_PORTS):
            if port_open(port, timeout):
                item = probe_port(port)
                if item:
                    item["id"] = "port-%d" % port
                    candidates.append(item)
    result = {
        "schema_version": 1,
        "generated_at": now(),
        "roots": [p.as_posix() for p in roots],
        "package_root": ROOT.as_posix(),
        "candidates": candidates,
        "env": env_facts(),
        "notes": [
            "扫描只读，不修改任何文件，不发送密钥。",
            "扫描结果是候选，不是安装许可；动文件前必须得到用户确认。",
        ],
    }
    result["questions"] = build_questions(result)
    return result


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", action="append", help="要扫描的项目根目录，可重复；默认当前目录")
    parser.add_argument("--json", help="survey.json 输出路径")
    parser.add_argument("--no-network", action="store_true", help="跳过本地端口探测")
    parser.add_argument("--ports", help="自定义端口列表，逗号分隔")
    parser.add_argument("--timeout", type=float, default=0.35, help="端口连接超时秒数")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    roots = [Path(value).expanduser().resolve() for value in (args.root or [str(Path.cwd())])]
    ports = [int(p) for p in args.ports.split(",") if p.strip().isdigit()] if args.ports else DEFAULT_PORTS
    result = survey(roots, ports=ports, network=not args.no_network, timeout=args.timeout)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = Path(args.json).resolve() if args.json else ROOT / "probe" / ("survey-" + stamp + ".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    (out.parent / "questions-for-user.md").write_text(render_questions(result), encoding="utf-8", newline="\n")
    if not args.quiet:
        print(summarize(result))
        print("\nSURVEY", out)
    return 0 if result["candidates"] else 3


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print("ERROR:", str(exc), file=sys.stderr)
        sys.exit(1)
