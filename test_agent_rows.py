#!/usr/bin/env python3
"""
Tests for claude-agent-rows.py.

    python3 test_agent_rows.py
"""
import importlib.util, json, os, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "claude-agent-rows.py")

spec = importlib.util.spec_from_file_location("agent_rows", SCRIPT)
rows = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rows)

NOW = 1_790_103_300.0


def task(**over):
    return {"id": "a2f1", "type": "local_agent", "status": "running",
            "description": "Final-review fix dispatch", "label": "Committing porSpan clamp fix",
            "startTime": int((NOW - 127) * 1000), "model": "claude-opus-5-5[1m]",
            "contextWindowSize": 1_000_000, "tokenCount": 110_900, **over}


class Fixture(unittest.TestCase):
    """A session directory with one subagent's metadata file."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        sub = os.path.join(self.dir.name, "sess", "subagents")
        os.makedirs(sub)
        with open(os.path.join(sub, "agent-a2f1.meta.json"), "w") as f:
            json.dump({"agentType": "general-purpose"}, f)
        self.transcript = os.path.join(self.dir.name, "sess.jsonl")

    def tearDown(self):
        self.dir.cleanup()

    def payload(self, *tasks, columns=100):
        return {"session_id": "sess", "transcript_path": self.transcript,
                "columns": columns, "tasks": list(tasks) or [task()]}

    def content(self, *tasks, **kw):
        return [json.loads(l)["content"] for l in rows.render(self.payload(*tasks, **kw), now=NOW)]


class TestModelName(unittest.TestCase):
    def test_names(self):
        for ident, want in [("claude-opus-5-5[1m]", "Opus 5.5"),
                            ("claude-opus-5", "Opus 5"),
                            ("claude-sonnet-5", "Sonnet 5"),
                            ("claude-fable-5-1", "Fable 5.1"),
                            ("claude-haiku-4-5-20251001", "Haiku 4.5")]:
            self.assertEqual(rows.model_name(ident), want)


class TestFormat(unittest.TestCase):
    def test_elapsed(self):
        self.assertEqual(rows.elapsed((NOW - 45) * 1000, NOW), "45s")
        self.assertEqual(rows.elapsed((NOW - 127) * 1000, NOW), "2m 7s")
        self.assertEqual(rows.elapsed((NOW - 3725) * 1000, NOW), "1h 2m")

    def test_tokens(self):
        self.assertEqual(rows.tokens(0), "0")
        self.assertEqual(rows.tokens(110_900), "110.9k")
        self.assertEqual(rows.tokens(1_250_000), "1.2M")


class TestRender(Fixture):
    def test_default_row_plus_model(self):
        [line] = self.content()
        self.assertTrue(line.startswith("general-purpose  Committing porSpan clamp fix  "))
        self.assertTrue(line.endswith("Opus 5.5 · 2m 7s · ↓ 110.9k tokens"))
        self.assertEqual(len(line), 100)

    def test_long_label_is_shortened_to_fit(self):
        [line] = self.content(task(label="x" * 200), columns=80)
        self.assertEqual(len(line), 80)
        self.assertIn("…", line)
        self.assertTrue(line.endswith("↓ 110.9k tokens"))

    def test_narrow_panel_drops_label(self):
        [line] = self.content(columns=50)
        self.assertNotIn("Committing", line)
        self.assertTrue(line.startswith("general-purpose"))

    def test_falls_back_to_description(self):
        [line] = self.content(task(label=""))
        self.assertIn("Final-review fix dispatch", line)

    def test_missing_metadata_uses_task_type(self):
        [line] = self.content(task(id="nope"))
        self.assertTrue(line.startswith("local_agent  "))

    def test_finished_and_unresolved_rows_keep_the_default(self):
        self.assertEqual(self.content(task(status="completed"), task(model=None)), [])


class TestScript(Fixture):
    def run_script(self, stdin):
        return subprocess.run([sys.executable, SCRIPT], input=stdin,
                              capture_output=True, text=True, check=True).stdout

    def test_emits_one_json_line_per_row(self):
        out = self.run_script(json.dumps(self.payload()))
        [line] = out.splitlines()
        self.assertEqual(json.loads(line)["id"], "a2f1")

    def test_bad_input_prints_nothing(self):
        self.assertEqual(self.run_script("not json").strip(), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
