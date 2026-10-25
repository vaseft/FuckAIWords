#!/usr/bin/env python3
"""Isolated workflow tests; synthetic assertions are never human approval."""
import copy
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
import deai
import probe

# Built at runtime so the repository never contains a literal that looks like a real key.
FAKE_TARGET_KEY = "sk-" + "T" * 24
FAKE_ENV_KEY = "sk-" + "E" * 24


def fake_bot(url, model, key, messages, settings):
    return json.dumps({"action": "reply", "text": "测试回答"}, ensure_ascii=False), {"total_tokens": 1}


def fixture_review(run):
    meta, questions, _ = deai.load_run(run)
    records = deai.records_for(run, questions)
    return {
        "schema_version": 1, "run_id": meta["run_id"], "prompt_sha256": meta["prompt_sha256"],
        "questions_sha256": meta["questions_sha256"], "reviewer": "SYNTHETIC TEST FIXTURE, NOT A PERSON",
        "manual_attestation": True,
        "reviews": [{"id": r["id"], "answer_sha256": r["answer_sha256"], "decision": "pass",
                     "scores": {"naturalness": 4, "relevance": 4, "correctness": 4}, "reviewed_at": deai.now()} for r in records],
    }


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="deai-isolated-test-")
        self.base = Path(self.temp.name)
        self.run = deai.new_run(self.base / "run")
        quiet = patch.object(deai, "print", create=True)
        quiet.start()
        self.addCleanup(quiet.stop)

    def tearDown(self):
        self.temp.cleanup()

    def populate(self):
        _, questions, _ = deai.load_run(self.run)
        for q in questions:
            deai.save_record(self.run, {"id": q["id"], "status": "ok", "action": "reply", "answer": "原始测试句",
                                       "raw_response": '{"action":"reply","text":"原始测试句"}', "history": [], "attempts": []})

    def test_hundred_unique_and_focus_not_in_model_input(self):
        _, questions, system = deai.load_run(self.run)
        self.assertEqual(len(questions), 100)
        msg = deai.case_messages(system, questions[0], [])
        self.assertNotIn(questions[0]["focus"], json.dumps(msg, ensure_ascii=False))
        self.assertNotIn('"category"', json.dumps(msg))

    def test_changed_prompt_or_style_invalidates_run(self):
        meta = deai.read_json(self.run / "manifest.json")
        meta["style"]["collection"]["temperature"] = 1.2
        deai.write_json(self.run / "manifest.json", meta)
        with self.assertRaises(ValueError):
            deai.load_run(self.run)

    def test_raw_answer_cannot_be_silently_edited(self):
        self.populate()
        path = self.run / "records/Q001.json"
        record = deai.read_json(path)
        record["answer"] = "篡改"
        deai.write_json(path, record)
        with self.assertRaises(ValueError):
            deai.refresh(self.run)

    def test_no_attestation_or_wrong_hash_rejected(self):
        self.populate()
        meta, qs, _ = deai.load_run(self.run)
        records = deai.records_for(self.run, qs)
        review = fixture_review(self.run)
        review["manual_attestation"] = False
        with self.assertRaises(ValueError):
            deai.validate_review(meta, records, review)
        review["manual_attestation"] = True
        review["reviews"][0]["answer_sha256"] = "wrong"
        with self.assertRaises(ValueError):
            deai.validate_review(meta, records, review)

    def test_pending_rejected_low_score_block_release(self):
        self.populate()
        meta, qs, _ = deai.load_run(self.run)
        records = deai.records_for(self.run, qs)
        review = fixture_review(self.run)
        for changed in ({"decision": "pending"}, {"decision": "reject", "reason": "测试拒绝"}, {"scores": {"naturalness": 2, "relevance": 5, "correctness": 5}}):
            altered = copy.deepcopy(review)
            altered["reviews"][0].update(changed)
            with self.assertRaises(ValueError):
                deai.validate_review(meta, records, altered)

    def test_partial_does_not_claim_release(self):
        self.populate()
        review = fixture_review(self.run)
        review["reviews"][1]["decision"] = "pending"
        path = self.base / "review.json"
        deai.write_json(path, review)
        report = deai.compile_review(self.run, path, self.base / "partial", partial=True)
        self.assertEqual(report["accepted"], 99)
        self.assertFalse(report["release_ready"])

    def test_correction_to_silence_is_valid_but_empty_reply_is_not(self):
        self.populate()
        review = fixture_review(self.run)
        row = review["reviews"][0]
        row.update(decision="correct", corrected_action="no_reply", corrected_text="", reason="无需插话", scope="无人提问的群聊")
        path = self.base / "review.json"
        deai.write_json(path, review)
        report = deai.compile_review(self.run, path, self.base / "compiled")
        self.assertTrue(report["release_ready"])
        self.assertEqual(report["corrected"], 1)
        result = (self.base / "compiled/runtime.md").read_text(encoding="utf-8")
        self.assertNotIn(deai.TRANSPORT, result)
        row["corrected_action"] = "reply"
        deai.write_json(path, review)
        with self.assertRaises(ValueError):
            deai.compile_review(self.run, path, self.base / "invalid")

    def test_error_cannot_be_passed_or_import_overwritten(self):
        self.populate()
        review = fixture_review(self.run)
        _, qs, _ = deai.load_run(self.run)
        records = deai.records_for(self.run, qs)
        records[0]["status"] = "error"
        meta = deai.read_json(self.run / "manifest.json")
        with self.assertRaises(ValueError):
            deai.validate_review(meta, records, review)
        file = self.base / "import.jsonl"
        deai.write_jsonl(file, [{"id": "Q001", "source": "actual_bot", "raw_response": "新的回答"}])
        with self.assertRaises(ValueError):
            deai.import_answers(self.run, file)

    def test_resume_never_repeats_success_and_session_uses_actual_history(self):
        captured = []
        def bot(*args):
            captured.append(copy.deepcopy(args[3]))
            return fake_bot(*args)
        with patch.object(deai, "connection", return_value=("http://localhost/v1/chat/completions", "test", "not-a-real-key")), patch.object(deai, "request_reply", side_effect=bot):
            first = deai.collect(self.run, limit=100, workers=4)
            self.assertEqual(first["collected"], 100)
            self.assertEqual(len(captured), 100)
            again = deai.collect(self.run, limit=100, workers=4)
            self.assertEqual(again["collected"], 100)
            self.assertEqual(len(captured), 100)
        _, qs, system = deai.load_run(self.run)
        r = deai.read_json(self.run / "records/Q092.json")
        self.assertEqual(r["history"][1]["role"], "assistant")
        self.assertIn("测试回答", r["history"][1]["content"])
        single = deai.read_json(self.run / "records/Q002.json")
        self.assertEqual(single["history"], [])
        all_files = "\n".join(p.read_text(encoding="utf-8") for p in self.run.rglob("*.json"))
        self.assertNotIn("not-a-real-key", all_files)

    def test_failed_prior_turn_blocks_later_turns(self):
        def bot(url, model, key, messages, settings):
            if "我的程序提示缺少 config.json" in messages[-1]["content"]:
                raise deai.CallError("TEST_FAILURE")
            return fake_bot(url, model, key, messages, settings)
        with patch.object(deai, "connection", return_value=("http://localhost/v1/chat/completions", "test", "")), patch.object(deai, "request_reply", side_effect=bot):
            deai.collect(self.run, limit=95, workers=4)
        self.assertEqual(deai.read_json(self.run / "records/Q091.json")["status"], "error")
        self.assertEqual(deai.read_json(self.run / "records/Q092.json")["status"], "blocked")

    def test_import_stages_validation_before_writing(self):
        file = self.base / "import.jsonl"
        deai.write_jsonl(file, [{"id": "Q001", "source": "actual_bot", "raw_response": "真实回答"}, {"id": "Q002", "source": "simulated", "raw_response": "假的"}])
        with self.assertRaises(ValueError):
            deai.import_answers(self.run, file)
        self.assertFalse((self.run / "records/Q001.json").exists())


class ProbeTest(unittest.TestCase):
    """Probe must find real targets, exclude protocol adapters, and never leak secrets."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="deai-probe-test-")
        self.base = Path(self.temp.name)
        self.project = self.base / "mybot"
        (self.project / "src").mkdir(parents=True)
        (self.project / "data").mkdir()
        (self.project / "napcat/shell").mkdir(parents=True)
        (self.project / "src/orchestrator.js").write_text("// orchestrator\n", encoding="utf-8")
        deai.write_json(self.project / "package.json", {"name": "my-bot", "dependencies": {"onebot": "1"}})
        deai.write_json(self.project / "data/config.json", {
            "persona": {"roleText": "原有人设"},
            "providers": [{"id": "p1", "apiKey": FAKE_TARGET_KEY}],
            "api": {"provider": "p1", "baseUrl": "https://api.example.com/v1", "model": "m1",
                    "apiKey": FAKE_TARGET_KEY},
        })
        deai.write_json(self.project / "napcat/shell/package.json", {"name": "napcat-shell"})

    def tearDown(self):
        self.temp.cleanup()

    def test_finds_bot_excludes_adapter_and_never_leaks_secret(self):
        with patch.dict(os.environ, {"DEAI_API_KEY": FAKE_ENV_KEY}, clear=False):
            result = probe.survey([self.base], network=False)
        blob = json.dumps(result, ensure_ascii=False)
        self.assertNotIn(FAKE_TARGET_KEY, blob)
        self.assertNotIn(FAKE_ENV_KEY, blob)
        bots = [c for c in result["candidates"] if c["kind"] == "qq-agent"]
        self.assertEqual(len(bots), 1)
        self.assertEqual(bots[0]["install"]["method"], "json-path")
        self.assertEqual(bots[0]["install"]["json_path"], "persona.roleText")
        self.assertEqual(bots[0]["collect"]["method"], "chat-completions")
        self.assertTrue(bots[0]["collect"]["has_key"])
        self.assertFalse(any("napcat" in (c.get("path") or "") for c in result["candidates"]))
        self.assertTrue(result["questions"])

    def test_empty_scan_asks_for_target(self):
        empty = self.base / "empty"
        empty.mkdir()
        with patch.object(probe, "find_skill_hosts", return_value=[]), patch.object(probe, "find_global_instructions", return_value=[]):
            result = probe.survey([empty], network=False)
        self.assertEqual(result["candidates"], [])
        self.assertTrue(any("没有找到" in q["question"] for q in result["questions"]))


class InstallTest(unittest.TestCase):
    """Assembly must be idempotent, reversible, and refuse dangerous targets."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="deai-install-test-")
        self.base = Path(self.temp.name)
        env = patch.dict(os.environ, {"DEAI_STATE_DIR": str(self.base / "state")}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        self.target = self.base / "system.md"
        self.target.write_text("你是测试助手，保留原有性格。\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_marker_is_idempotent_and_replaces_version(self):
        first = deai.install_expression(self.target, label="v1")
        self.assertTrue(first["changed"])
        self.assertEqual(self.target.read_text(encoding="utf-8").count("deai:begin"), 1)
        again = deai.install_expression(self.target, label="v1")
        self.assertFalse(again["changed"])
        v2 = self.base / "v2.md"
        v2.write_text("# v2 表达层\n", encoding="utf-8")
        replaced = deai.install_expression(self.target, express=v2, label="v2")
        self.assertTrue(replaced["changed"])
        text = self.target.read_text(encoding="utf-8")
        self.assertEqual(text.count("deai:begin"), 1)
        self.assertIn("v2 表达层", text)
        self.assertIn("保留原有性格", text)

    def test_rollback_restores_original_text(self):
        original = self.target.read_text(encoding="utf-8")
        deai.install_expression(self.target, label="v1")
        self.assertNotEqual(self.target.read_text(encoding="utf-8"), original)
        result = deai.rollback_install(self.target)
        self.assertEqual(result["restored"], self.target.as_posix())
        self.assertEqual(self.target.read_text(encoding="utf-8"), original)

    def test_dry_run_writes_nothing(self):
        original = self.target.read_text(encoding="utf-8")
        result = deai.install_expression(self.target, label="v1", dry_run=True)
        self.assertTrue(result["changed"])
        self.assertEqual(self.target.read_text(encoding="utf-8"), original)
        self.assertFalse((self.base / "state/install-state.json").exists())

    def test_code_and_secret_targets_rejected(self):
        code = self.base / "bot.js"
        code.write_text("console.log(1)\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            deai.install_expression(code)
        secret = self.base / "leak.md"
        secret.write_text("key: " + FAKE_TARGET_KEY + "\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            deai.install_expression(self.target, express=secret)

    def test_package_own_dirs_rejected(self):
        with self.assertRaises(ValueError):
            deai.install_expression(deai.ROOT / "prompts/runtime.md")

    def test_position_start_puts_layer_first_and_moves_on_switch(self):
        original = self.target.read_text(encoding="utf-8")
        result = deai.install_expression(self.target, label="v1", position="start")
        self.assertEqual(result["position"], "start")
        self.assertEqual(result["cache_mode"], "prefix-first")
        text = self.target.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("<!-- deai:begin"))
        self.assertLess(text.index("deai:begin"), text.index("保留原有性格"))
        self.assertIn(original.strip(), text)
        again = deai.install_expression(self.target, label="v1", position="start")
        self.assertFalse(again["changed"])
        moved = deai.install_expression(self.target, label="v1", position="end")
        self.assertTrue(moved["changed"])
        self.assertEqual(moved["position"], "end")
        end_text = self.target.read_text(encoding="utf-8")
        self.assertTrue(end_text.startswith("你是测试助手"))
        self.assertEqual(end_text.count("deai:begin"), 1)
        self.assertIn(original.strip(), end_text)

    def test_position_start_works_with_json_path(self):
        config = self.base / "config.json"
        deai.write_json(config, {"persona": {"roleText": "原有人设"}})
        result = deai.install_expression(config, json_path="persona.roleText", label="v1", position="start")
        self.assertEqual(result["cache_mode"], "prefix-first")
        field = deai.read_json(config)["persona"]["roleText"]
        self.assertTrue(field.startswith("<!-- deai:begin"))
        self.assertTrue(field.rstrip().endswith("原有人设"))

    def test_cache_plan_flags_early_dynamic_content(self):
        template = self.base / "template.md"
        template.write_text("人设一行。\n\n【记忆】\n{memory}\n", encoding="utf-8")
        plan = deai.cache_plan(template)
        self.assertEqual(plan["recommend"], "start")
        self.assertEqual(plan["gain_level"], "large")
        self.assertGreater(plan["gain_chars"], 0)
        self.assertTrue(plan["start"]["layer_cached"])
        self.assertFalse(plan["end"]["layer_cached"])
        self.assertIn("{memory}", plan["dynamic_markers"])

    def test_cache_plan_reports_no_gain_for_plain_persona(self):
        plan = deai.cache_plan(self.target)
        # No placeholder inside the file means both placements cache the same bytes.
        self.assertEqual(plan["recommend"], "end")
        self.assertEqual(plan["gain_level"], "none")
        self.assertEqual(plan["gain_chars"], 0)
        self.assertIsNone(plan["first_dynamic_at"])
        self.assertTrue(plan["end"]["layer_cached"])
        self.assertTrue(plan["start"]["layer_cached"])

    def test_json_path_preserves_other_fields_and_emits_persona(self):
        config = self.base / "config.json"
        deai.write_json(config, {"persona": {"roleText": "原有人设"}, "api": {"model": "keep-me"}})
        emitted = self.base / "emitted.txt"
        result = deai.install_expression(config, json_path="persona.roleText", label="v1", emit=emitted)
        self.assertEqual(result["mode"], "json-path")
        data = deai.read_json(config)
        self.assertEqual(data["api"]["model"], "keep-me")
        self.assertIn("原有人设", data["persona"]["roleText"])
        self.assertIn("deai:begin", data["persona"]["roleText"])
        self.assertIn("原有人设", emitted.read_text(encoding="utf-8"))
        with self.assertRaises(ValueError):
            deai.install_expression(config, label="v1")  # JSON needs --json-path
        with self.assertRaises(ValueError):
            deai.install_expression(config, json_path="persona.missing", label="v1")


class ApplyAndStatusTest(unittest.TestCase):
    """apply = compile + install; status never claims human approval."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="deai-apply-test-")
        self.base = Path(self.temp.name)
        env = patch.dict(os.environ, {"DEAI_STATE_DIR": str(self.base / "state")}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        quiet = patch.object(deai, "print", create=True)
        quiet.start()
        self.addCleanup(quiet.stop)
        self.run = deai.new_run(self.base / "run")

    def tearDown(self):
        self.temp.cleanup()

    def populate(self):
        _, questions, _ = deai.load_run(self.run)
        for q in questions:
            deai.save_record(self.run, {"id": q["id"], "status": "ok", "action": "reply", "answer": "原始测试句",
                                        "raw_response": '{"action":"reply","text":"原始测试句"}',
                                        "history": [], "attempts": []})

    def test_install_reports_persona_preserved(self):
        target = self.base / "persona.md"
        original = "原有人设：冷淡、话少，不主动找话题。\n"
        target.write_text(original, encoding="utf-8")
        result = deai.install_expression(target, label="v1")
        self.assertEqual(result["persona_policy"], "preserve-existing")
        self.assertEqual(result["preserved_original_chars"], len(original))
        self.assertIn("原有人设：冷淡、话少", target.read_text(encoding="utf-8"))
        legacy = self.base / "legacy.md"
        legacy.write_text("旧设定\n", encoding="utf-8")
        replaced = deai.install_expression(legacy, mode="replace", force=True, label="v1")
        self.assertEqual(replaced["persona_policy"], "replace-all")
        self.assertEqual(replaced["preserved_original_chars"], 0)
        self.assertIn("warning", replaced)

    def test_template_contains_questions_but_no_answers(self):
        html = self.base / "preview.html"
        md = self.base / "questions.md"
        result = deai.review_template(html.as_posix(), md.as_posix())
        self.assertEqual(result["questions"], 100)
        self.assertFalse(result["answers_included"])
        text = html.read_text(encoding="utf-8")
        self.assertIn("这是题单预览", text)
        payload = re.search(r'<script id="run-data" type="application/json">(.*?)</script>', text, re.S)
        data = json.loads(payload.group(1))
        self.assertEqual(len(data["records"]), 100)
        self.assertTrue(all(r["answer"] == "" and r["status"] == "pending" for r in data["records"]))
        body = md.read_text(encoding="utf-8")
        self.assertIn("在吗？", body)
        self.assertIn("不含任何模型的回答", body)

    def test_apply_compiles_then_writes_target(self):
        self.populate()
        review_path = self.base / "review.json"
        deai.write_json(review_path, fixture_review(self.run))
        target = self.base / "system.md"
        target.write_text("原系统提示\n", encoding="utf-8")
        result = deai.apply_review(self.run, review_path, self.base / "compiled/v1", target, label="human-v1")
        self.assertTrue(result["compiled"]["release_ready"])
        self.assertTrue(result["installed"]["changed"])
        text = target.read_text(encoding="utf-8")
        self.assertIn("原系统提示", text)
        self.assertIn("label=human-v1", text)
        self.assertEqual(text.count("deai:begin"), 1)

    def test_status_never_infers_human_review(self):
        status = deai.workspace_status()
        review_stage = next(s for s in status["stages"] if s["stage"] == "human-review")
        self.assertFalse(review_stage["done"])
        self.assertIn("不由程序推断", review_stage["note"])
        self.assertIn("必须由人判断", status["notice"])

    def test_collect_system_file_records_source(self):
        system_file = self.base / "target-prompt.txt"
        system_file.write_text("装好的完整提示\n", encoding="utf-8")
        run = deai.new_run(self.base / "run2", prompt=system_file.as_posix(), source=system_file.as_posix())
        meta = deai.read_json(run / "manifest.json")
        self.assertEqual(meta["system_source"], system_file.as_posix())
        self.assertIn("装好的完整提示", (run / "system-prompt.txt").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
