#!/usr/bin/env python3
"""Build a relocatable ZIP from the explicit bundle contents; no source secrets."""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE_MAP = {
    "prompts/character.md": "prompts/character.md",
    "prompts/conversation.md": "prompts/conversation.md",
    "prompts/anti_template.md": "prompts/anti_template.md",
    "plugins/natural-dialogue/index.js": "natural-dialogue.mjs",
    "plugins/natural-dialogue/plugin.json": "plugin.json",
    "src/expression-memory.js": "expression-memory.js.txt",
    "src/send-guard.js": "send-guard.js.txt",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", help="Optional read-only verification of the seven known source files")
    parser.add_argument("--include-runs", action="store_true", help="Include synthetic test inputs and collected bot replies in the ZIP")
    args = parser.parse_args()
    evidence = []
    for source, snapshot in SOURCE_MAP.items():
        path = ROOT / "evidence/source" / snapshot
        if args.source_root and sha(Path(args.source_root) / source) != sha(path):
            raise ValueError("Source differs from snapshot: " + source)
        symbols = []
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"^export (?:async )?(?:function|const) |^const (?:MAX_ITEMS|KEEP_DAYS)", line):
                symbols.append({"line": i, "declaration": line[:150]})
        evidence.append({"source_relative_path": source, "snapshot": "evidence/source/" + snapshot, "sha256": sha(path), "symbols": symbols})
    write(ROOT / "evidence/source-map.json", {"source": "QQ-agent local working tree", "extracted_on": "2026-10-25", "files": evidence})
    dirs = ("scripts", "prompts", "config", "evaluation", "runtime", "references", "assets", "evidence")
    top = ("AGENT.md", "AGENTS.md", "SKILL.md", "开始使用.md", "README.md", "ATTRIBUTION.md", ".gitignore")
    static = [ROOT / name for name in top if (ROOT / name).exists()]
    for directory in dirs:
        static.extend(p for p in (ROOT / directory).rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")
    static = sorted(set(static))
    write(ROOT / "bundle-manifest.json", {"schema_version": 1, "created_at": dt.datetime.now(dt.timezone.utc).isoformat(), "files": [{"path": p.relative_to(ROOT).as_posix(), "sha256": sha(p)} for p in static], "mutable_evidence": "runs are checked by each run's hashes; browser review copies are not static source"})
    files = static + [ROOT / "bundle-manifest.json"]
    if args.include_runs:
        files += [ROOT / name for name in ("人工审核.html", "最新运行.json") if (ROOT / name).exists()]
        files += [p for p in (ROOT / "runs").rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix in {".json", ".jsonl", ".html", ".txt"}]
    output = ROOT / "portable-deai-agent.zip"
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(set(files)):
            archive.write(path, "deai-dialogue/" + path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise ValueError("ZIP CRC failed")
    print(json.dumps({"zip": str(output), "files": len(set(files)), "bytes": output.stat().st_size, "sha256": sha(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
