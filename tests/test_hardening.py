import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mcp_ward.cli import _git_show
from mcp_ward.diff import DiffReport, Finding, diff_surfaces
from mcp_ward.policy import report_blocks
from mcp_ward.snapshot import SnapshotError, load_document, normalize_surface


def tool(name="x", **extra):
    value = {"name": name, "inputSchema": {"type": "object"}}
    value.update(extra)
    return value


class HardeningTests(unittest.TestCase):
    def test_tool_requires_an_object_input_schema(self):
        with self.assertRaisesRegex(SnapshotError, "inputSchema"):
            normalize_surface({"tools": [{"name": "x"}]})
        with self.assertRaisesRegex(SnapshotError, "type.*object"):
            normalize_surface({"tools": [tool(inputSchema={"type": "string"})]})

    def test_invalid_input_schema_root_is_rejected_by_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline = root / "before.json"
            candidate = root / "after.json"
            payload = json.dumps({"tools": [{"name": "x"}]})
            baseline.write_text(payload, encoding="utf-8")
            candidate.write_text(payload, encoding="utf-8")
            env = os.environ.copy()
            env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
            result = subprocess.run(
                [sys.executable, "-m", "mcp_ward", "check", str(baseline), str(candidate)],
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("inputSchema", result.stderr)
            self.assertNotIn("findings", result.stdout)

    def test_type_set_does_not_turn_unknown_names_into_supported(self):
        with self.assertRaises(SnapshotError):
            normalize_surface(
                {
                    "tools": [
                        tool(
                            inputSchema={
                                "type": "object",
                                "properties": {"n": {"type": "wat"}},
                            }
                        )
                    ]
                }
            )
        with self.assertRaises(SnapshotError):
            normalize_surface(
                {
                    "tools": [
                        tool(
                            inputSchema={
                                "type": "object",
                                "properties": {"n": {"type": ["string", "string"]}},
                            }
                        )
                    ]
                }
            )

    def test_input_schema_type_name_is_validated_at_root_and_nested_paths(self):
        before = normalize_surface({"tools": [tool(inputSchema={"type": "object"})]})
        after = normalize_surface(
            {
                "tools": [
                    tool(
                        inputSchema={
                            "type": "object",
                            "properties": {"n": {"type": "string"}},
                        }
                    )
                ]
            }
        )
        findings = diff_surfaces(before, after)
        self.assertTrue(any(item.code == "schema.property.added" for item in findings))

    def test_schema_type_names_and_duplicate_type_values_are_rejected(self):
        for bad in ("wat", ["string", "string"]):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(SnapshotError, "type"):
                    normalize_surface({"tools": [tool(inputSchema={"type": bad})]})

    def test_duplicate_json_object_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "duplicate.json"
            path.write_text(
                '{"tools":[{"name":"first","name":"second","inputSchema":{"type":"object"}}]}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(SnapshotError, "duplicate JSON object key"):
                load_document(path)

    def test_non_standard_json_numbers_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "number.json"
            for literal in ("NaN", "Infinity", "-Infinity"):
                with self.subTest(literal=literal):
                    path.write_text(
                        '{"tools":[{"name":"x","inputSchema":{"type":"object","properties":{"n":{"type":"number","minimum":'
                        + literal
                        + "}}}}]}",
                        encoding="utf-8",
                    )
                    with self.assertRaisesRegex(SnapshotError, "non-standard"):
                        load_document(path)

    def test_unsupported_keyword_presence_is_not_equivalent_to_null(self):
        before = normalize_surface({"tools": [tool()]})
        after = normalize_surface({"tools": [tool(inputSchema={"type": "object", "pattern": "x"})]})
        self.assertTrue(
            any(item.code == "schema.unsupported.changed" for item in diff_surfaces(before, after))
        )

    def test_deep_json_is_an_input_error_not_a_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "deep.json"
            child = '{"type":"object"}'
            for _ in range(1200):
                child = '{"type":"object","properties":{"x":' + child + "}}"
            path.write_text(
                '{"tools":[{"name":"deep","inputSchema":' + child + "}]}",
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
            result = subprocess.run(
                [sys.executable, "-m", "mcp_ward", "snapshot", str(path)],
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertIn("nesting", result.stderr.lower())

    def test_terminal_output_neutralizes_c1_and_bidi_controls(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline = root / "baseline.json"
            candidate = root / "candidate.json"
            baseline.write_text(json.dumps({"tools": [tool()]}), encoding="utf-8")
            candidate.write_text(
                json.dumps(
                    {"tools": [tool(description="\x1b]0;spoof\x07\x9d0;c1\x9c\u202e\u2066")]},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
            result = subprocess.run(
                [sys.executable, "-m", "mcp_ward", "check", str(baseline), str(candidate), "--format", "text"],
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1, result.stderr)
            for char in ("\x1b", "\x07", "\x9b", "\x9d", "\x9c", "\u202e", "\u2066"):
                self.assertNotIn(char, result.stdout)

    def test_strict_blocks_unknown_future_impact(self):
        finding = Finding("future.change", "tools.x", "wire", "future", "future")
        self.assertTrue(report_blocks("strict", DiffReport([finding])))

    def test_git_baseline_show_uses_verified_commit_sha(self):
        valid = json.dumps({"tools": [tool()]})
        calls = []

        def fake_run(args, **kwargs):
            calls.append(list(args))
            if args[1] == "rev-parse":
                return subprocess.CompletedProcess(args, 0, stdout="a" * 40 + "\n", stderr="")
            return subprocess.CompletedProcess(args, 0, stdout=valid, stderr="")

        with patch("mcp_ward.cli.subprocess.run", side_effect=fake_run):
            _git_show("main:baseline.json")
        self.assertEqual(calls[1][2], "a" * 40 + ":baseline.json")
        self.assertNotEqual(calls[1][2], "main:baseline.json")

    def test_git_ref_control_characters_are_rejected(self):
        for ref in ("HEAD\n:x", "HEAD\r:x", "HEAD\x00:x"):
            with self.subTest(ref=repr(ref)):
                with self.assertRaises(SnapshotError):
                    _git_show(ref)

    def test_report_files_use_lf_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline = root / "baseline.json"
            candidate = root / "candidate.json"
            report_dir = root / "reports"
            baseline.write_text(json.dumps({"tools": [tool()]}), encoding="utf-8")
            candidate.write_text(json.dumps({"tools": [tool(description="new")]}), encoding="utf-8")
            env = os.environ.copy()
            env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mcp_ward",
                    "check",
                    str(baseline),
                    str(candidate),
                    "--format",
                    "text,json,html",
                    "--report-dir",
                    str(report_dir),
                ],
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1, result.stderr)
            for name in ("report.txt", "report.json", "report.html"):
                self.assertNotIn(b"\r\n", (report_dir / name).read_bytes())


if __name__ == "__main__":
    unittest.main()
