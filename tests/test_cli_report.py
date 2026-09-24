import json
import os
import subprocess
import sys
import tempfile
import unittest
from dataclasses import asdict
from html.parser import HTMLParser
from pathlib import Path

from mcp_ward.diff import Finding, DiffReport, diff_surfaces
from mcp_ward.policy import PROFILES, report_blocks
from mcp_ward.report import render_html, render_json, render_text
from mcp_ward.snapshot import normalize_surface, snapshot_bytes

RAW_SURFACE = {
    "tools": [
        {
            "name": "search",
            "title": "Search notes",
            "description": "Search notes by exact phrase.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            "outputSchema": {
                "type": "object",
                "properties": {"hits": {"type": "array", "items": {"type": "string"}}},
                "required": ["hits"],
            },
            "annotations": {"readOnlyHint": True},
            "_meta": {
                "io.modelcontextprotocol/specification/2025-11-25": {
                    "baseUri": "https://example.test"
                }
            },
        }
    ]
}


class Balance(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.void = {
            "area", "base", "br", "col", "embed", "hr", "img", "input",
            "link", "meta", "source", "track", "wbr",
        }

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in self.void:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        return

    def handle_endtag(self, tag: str) -> None:
        if tag in self.void:
            return
        if not self.stack or self.stack[-1] != tag:
            raise AssertionError(f"unbalanced closing tag: {tag}; stack={self.stack[-3:]}")
        self.stack.pop()


def sample_finding(impact: str = "breaking") -> Finding:
    return Finding(
        code="agent.description.changed",
        path="tools.search.description",
        axis="agent",
        impact=impact,
        message="Tool description changed.",
        before="old",
        after="new",
    )


def run_cli(*args: str, cwd: Path | None = None, module: str = "mcp_ward.cli") -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    return subprocess.run(
        [sys.executable, "-m", module, *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
    )


class TestPolicies(unittest.TestCase):
    def test_expected_profiles_and_blocks(self) -> None:
        self.assertEqual(set(PROFILES), {"observe", "wire", "agent", "strict"})
        self.assertEqual(report_blocks("observe", DiffReport([])), False)
        self.assertEqual(report_blocks("observe", DiffReport([sample_finding()])), False)
        self.assertEqual(report_blocks("wire", DiffReport([sample_finding("review")])), False)
        self.assertEqual(report_blocks("agent", DiffReport([sample_finding("review")])), True)
        self.assertEqual(report_blocks("agent", DiffReport([sample_finding("additive")])), False)
        self.assertEqual(report_blocks("strict", DiffReport([sample_finding("review")])), True)
        self.assertEqual(report_blocks("strict", DiffReport([sample_finding("cosmetic")])), True)
        self.assertEqual(report_blocks("wire", DiffReport([sample_finding("unknown")])), True)

    def test_unknown_profile_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            report_blocks("nope", DiffReport([]))


class TestRenderers(unittest.TestCase):
    def test_json_report_is_canonical(self) -> None:
        finding = sample_finding()
        report = DiffReport([finding])
        parsed = json.loads(render_json(report, "agent"))
        self.assertEqual(parsed["format_version"], 1)
        self.assertEqual(parsed["findings"], [asdict(finding)])
        self.assertEqual(parsed["counts"], {"breaking": 1, "review": 0, "additive": 0, "cosmetic": 0, "unknown": 0})
        self.assertEqual(parsed["profile"], "agent")
        self.assertEqual(parsed["max_severity"], "breaking")
        self.assertEqual(parsed["exit_code"], 1)

    def test_text_report_has_stable_summary_and_codes(self) -> None:
        report = DiffReport([sample_finding("review")])
        text = render_text(report, "agent")
        self.assertIn("mcp-ward", text)
        self.assertIn("agent.description.changed", text)
        self.assertIn("profile: agent", text)
        self.assertIn("0 breaking  1 review  0 additive  0 cosmetic", text)

    def test_rendered_gate_matches_the_selected_profile(self) -> None:
        breaking = render_text(DiffReport([sample_finding("breaking")]), "observe")
        self.assertIn("· PASS", breaking)
        strict = render_text(DiffReport([sample_finding("cosmetic")]), "strict")
        self.assertIn("· BLOCK", strict)
        page = render_html(DiffReport([sample_finding("cosmetic")]), "strict")
        self.assertIn('data-gate="BLOCK"', page)

    def test_html_is_self_contained_balanced_and_escapes_hostile_data(self) -> None:
        hostile = Finding(
            code="metadata.changed",
            path='tools."><img src=x onerror="alert(1)">',
            axis="both",
            impact="breaking",
            message="<script>alert('x')</script>",
            before=None,
            after={"label": "<b>unsafe</b>"},
        )
        report = DiffReport([hostile])
        page = render_html(report, "observe")
        parser = Balance()
        parser.feed(page)
        parser.close()
        self.assertEqual(parser.stack, [])
        self.assertNotIn("<script>alert", page)
        self.assertNotIn("<img src=x", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn("&lt;b&gt;unsafe&lt;/b&gt;", page)
        self.assertNotIn("http://", page)
        self.assertNotIn("https://", page)
        self.assertNotIn("<link", page)
        self.assertNotIn("@import", page)
        self.assertIn("<!doctype html>", page.lower())
        self.assertIn("prefers-reduced-motion", page)

    def test_text_json_html_share_counts_and_severity(self) -> None:
        report = DiffReport([
            sample_finding("breaking"),
            sample_finding("review"),
            sample_finding("additive"),
            sample_finding("cosmetic"),
        ])
        text = render_text(report, "strict")
        page = render_html(report, "strict")
        parsed = json.loads(render_json(report, "strict"))
        for impact, count in parsed["counts"].items():
            self.assertIn(f"{count} {impact}", text)
            self.assertIn(f'data-impact="{impact}" data-count="{count}"', page)
        self.assertIn('data-filter="unknown"', page)
        for finding in report.findings:
            self.assertIn(finding.code, text)
            self.assertIn(finding.code, page)


    def test_json_exit_code_reflects_the_selected_profile(self) -> None:
        passing = json.loads(render_json(DiffReport([sample_finding("breaking")]), "observe"))
        self.assertEqual(passing["exit_code"], 0)
        blocking = json.loads(render_json(DiffReport([sample_finding("unknown")]), "wire"))
        self.assertEqual(blocking["exit_code"], 1)

    def test_unknown_impact_blocks_every_profile_except_observe(self) -> None:
        unknown = DiffReport([sample_finding("unknown")])
        self.assertFalse(report_blocks("observe", unknown))
        self.assertTrue(report_blocks("wire", unknown))
        self.assertTrue(report_blocks("agent", unknown))
        self.assertTrue(report_blocks("strict", unknown))

    def test_text_report_labels_unknown_findings(self) -> None:
        text = render_text(DiffReport([sample_finding("unknown")]), "wire")
        self.assertIn("UNKNOWN", text)
        self.assertIn("· BLOCK", text)

    def test_unknown_is_visible_in_counts_and_max_severity(self) -> None:
        report = DiffReport([sample_finding("unknown")])
        payload = json.loads(render_json(report, "wire"))
        self.assertEqual(payload["counts"]["unknown"], 1)
        self.assertEqual(payload["max_severity"], "unknown")
        self.assertIn("1 unknown", render_text(report, "wire"))
        self.assertIn('data-count="1"', render_html(report, "wire"))

    def test_text_report_neutralizes_terminal_control_sequences(self) -> None:
        finding = Finding(
            code="wire.name.changed",
            path="tools.\\x1b]0;title\\x07.evil",
            axis="wire",
            impact="breaking",
            message="unsafe\\r\\nnext line",
            before="a",
            after="b",
        )
        text = render_text(DiffReport([finding]), "wire")
        self.assertNotIn("\x1b", text)
        self.assertNotIn("\x07", text)
        self.assertNotIn("\r", text)
        self.assertIn("\\x1b", text)

    def test_html_escapes_hostile_tool_names_from_a_real_diff(self) -> None:
        name = 'x"><script>alert(1)</script>'
        before = normalize_surface(
            {
                "tools": [
                    {
                        "name": name,
                        "inputSchema": {"type": "object"},
                        "description": "<b>old</b>",
                    }
                ]
            }
        )
        after = normalize_surface(
            {
                "tools": [
                    {
                        "name": name,
                        "inputSchema": {"type": "object"},
                        "description": "<i>new</i>",
                    }
                ]
            }
        )
        page = render_html(DiffReport(diff_surfaces(before, after)), "agent")
        parser = Balance()
        parser.feed(page)
        parser.close()
        self.assertEqual(parser.stack, [])
        self.assertNotIn("<script>alert", page)
        self.assertNotIn("<b>old</b>", page)
        self.assertIn("&lt;b&gt;old&lt;/b&gt;", page)


class TestCLI(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.baseline = self.root / "baseline.json"
        self.candidate = self.root / "candidate.json"
        self.baseline.write_text(json.dumps(RAW_SURFACE), encoding="utf-8")
        changed = json.loads(json.dumps(RAW_SURFACE))
        changed["tools"][0]["inputSchema"]["properties"]["limit"]["type"] = "string"
        self.candidate.write_text(json.dumps(changed), encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_snapshot_is_repeatable_and_file_is_stable(self) -> None:
        out = self.root / "snapshot.json"
        first = run_cli("snapshot", str(self.baseline), "--output", str(out))
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("snapshot written:", first.stdout)
        self.assertTrue(out.exists())
        original = out.read_bytes()
        second = run_cli("snapshot", str(self.baseline), "--output", str(out))
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(out.read_bytes(), original)
        self.assertEqual(snapshot_bytes(normalize_surface(RAW_SURFACE)), original)

    def test_check_returns_one_for_agent_profile(self) -> None:
        result = run_cli(
            "check", str(self.baseline), str(self.candidate),
            "--profile", "agent",
            "--format", "json",
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["counts"]["breaking"], 1)
        self.assertEqual(payload["findings"][0]["code"], "schema.type.accepted.narrowed")
        self.assertEqual(payload["findings"][0]["path"], "tools.search.inputSchema.limit.type")

    def test_html_format_is_emitted_to_stdout_without_report_dir(self) -> None:
        result = run_cli("check", str(self.baseline), str(self.candidate), "--format", "html")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("<!doctype html>", result.stdout.lower())
        self.assertIn("data-ready=\"true\"", result.stdout)

    def test_check_observe_never_blocks(self) -> None:
        result = run_cli(
            "check", str(self.baseline), str(self.candidate),
            "--profile", "observe",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("1 breaking", result.stdout)

    def test_check_writes_all_report_formats(self) -> None:
        report_dir = self.root / "reports"
        result = run_cli(
            "check", str(self.baseline), str(self.candidate),
            "--profile", "agent",
            "--format", "text,json,html",
            "--report-dir", str(report_dir),
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(
            sorted(path.name for path in report_dir.iterdir()),
            ["report.html", "report.json", "report.txt"],
        )
        parsed = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(parsed["counts"]["breaking"], 1)

    def test_check_renders_zh_and_both_without_changing_json(self) -> None:
        zh = run_cli(
            "check", str(self.baseline), str(self.candidate),
            "--format", "text", "--lang", "zh",
        )
        self.assertEqual(zh.returncode, 1, zh.stderr)
        self.assertIn("破坏性变更", zh.stdout)
        # This fixture's only finding is a type narrowing, so assert the
        # translated wording for a code the fixture really produces.
        self.assertIn("接受的类型收窄", zh.stdout)
        self.assertNotIn("accepted types narrowed", zh.stdout)

        # Locale aliases resolve through normalize_lang even though argparse no
        # longer hard-rejects them.
        alias = run_cli(
            "check", str(self.baseline), str(self.candidate),
            "--format", "text", "--lang", "zh-CN",
        )
        self.assertEqual(alias.returncode, 1, alias.stderr)
        self.assertIn("破坏性变更", alias.stdout)

        both = run_cli(
            "check", str(self.baseline), str(self.candidate),
            "--format", "text", "--lang", "both",
        )
        self.assertEqual(both.returncode, 1, both.stderr)
        self.assertIn("BREAKING / 破坏性变更", both.stdout)

        json_en = run_cli(
            "check", str(self.baseline), str(self.candidate),
            "--format", "json", "--lang", "en",
        )
        json_both = run_cli(
            "check", str(self.baseline), str(self.candidate),
            "--format", "json", "--lang", "both",
        )
        self.assertEqual(json_en.returncode, 1, json_en.stderr)
        self.assertEqual(json_both.returncode, 1, json_both.stderr)
        self.assertEqual(
            json.loads(json_en.stdout),
            json.loads(json_both.stdout),
        )

    def test_check_writes_localized_html_and_rejects_unknown_language(self) -> None:
        report_dir = self.root / "localized"
        result = run_cli(
            "check", str(self.baseline), str(self.candidate),
            "--format", "text,json,html", "--lang", "both",
            "--report-dir", str(report_dir),
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        page = (report_dir / "report.html").read_text(encoding="utf-8")
        self.assertIn("Surface review / <span lang=\"zh-CN\">工具表面审查</span>", page)
        self.assertIn("before / <span lang=\"zh-CN\">变更前</span>", page)

        invalid = run_cli(
            "check", str(self.baseline), str(self.candidate),
            "--lang", "fr",
        )
        self.assertEqual(invalid.returncode, 2, invalid.stderr)
        self.assertIn("lang", invalid.stderr.lower())

    def test_package_module_entrypoint_uses_the_same_cli(self) -> None:
        result = run_cli("--version", module="mcp_ward")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("mcp-ward 0.1.0", result.stdout)

    def test_check_requires_a_candidate_even_with_a_baseline(self) -> None:
        result = run_cli("check", str(self.baseline), module="mcp_ward")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("candidate", result.stderr)

    def test_package_module_entrypoint_propagates_cli_errors(self) -> None:
        result = run_cli("check", "missing-baseline.json", "missing-candidate.json", module="mcp_ward")
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("error", result.stderr)

    def test_check_supports_git_baseline_ref(self) -> None:
        self.baseline.unlink()
        run_cli("snapshot", str(self.candidate), "--output", str(self.baseline))
        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "MCP Ward Test"], cwd=self.root, check=True)
        subprocess.run(["git", "add", "baseline.json"], cwd=self.root, check=True)
        subprocess.run(
            ["git", "commit", "-m", "baseline"],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        )
        changed = json.loads(json.dumps(RAW_SURFACE))
        changed["tools"][0]["description"] = "Changed."
        self.candidate.write_text(json.dumps(changed), encoding="utf-8")
        result = run_cli(
            "check", "--baseline-ref", "HEAD:baseline.json",
            "--candidate", str(self.candidate),
            "--profile", "agent",
            "--format", "json",
            cwd=self.root,
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        parsed = json.loads(result.stdout)
        self.assertEqual(parsed["findings"][0]["code"], "agent.description.changed")

    def test_cli_rejects_ambiguous_and_invalid_inputs(self) -> None:
        ambiguous = run_cli(
            "check", str(self.baseline),
            "--baseline-ref", "HEAD:baseline.json",
        )
        self.assertEqual(ambiguous.returncode, 2)
        self.assertIn("either", ambiguous.stderr)

        missing = run_cli("snapshot", str(self.root / "missing.json"))
        self.assertEqual(missing.returncode, 2)
        self.assertIn("no such file", missing.stderr.lower())

        unknown_format = run_cli(
            "check", str(self.baseline), str(self.candidate),
            "--format", "yaml",
        )
        self.assertEqual(unknown_format.returncode, 2)
        self.assertIn("format", unknown_format.stderr.lower())

        bad_profile = run_cli(
            "check", str(self.baseline), str(self.candidate),
            "--profile", "nope",
        )
        self.assertEqual(bad_profile.returncode, 2)
        self.assertIn("profile", bad_profile.stderr.lower())

    def test_removed_paranoid_profile_is_rejected(self) -> None:
        legacy = run_cli(
            "check", str(self.baseline), str(self.candidate),
            "--profile", "paranoid",
        )
        self.assertEqual(legacy.returncode, 2)
        self.assertIn("profile", legacy.stderr.lower())

    def test_check_requires_a_baseline_without_baseline_ref(self) -> None:
        result = run_cli("check", "--candidate", str(self.candidate))
        self.assertEqual(result.returncode, 2)
        self.assertIn("baseline", result.stderr)

    def test_candidate_positional_and_option_conflict(self) -> None:
        result = run_cli(
            "check", str(self.baseline), str(self.candidate),
            "--candidate", str(self.candidate),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("both", result.stderr)

    def test_git_baseline_ref_errors_are_exit_code_two(self) -> None:
        no_colon = run_cli(
            "check", "--baseline-ref", "HEAD",
            "--candidate", str(self.candidate),
        )
        self.assertEqual(no_colon.returncode, 2)
        self.assertIn("REF:PATH", no_colon.stderr)

        missing = run_cli(
            "check", "--baseline-ref", "HEAD:nope.json",
            "--candidate", str(self.candidate),
            cwd=self.root,
        )
        self.assertEqual(missing.returncode, 2)
        self.assertIn("invalid git baseline ref", missing.stderr)

        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "MCP Ward Test"], cwd=self.root, check=True)
        (self.root / "notes.txt").write_text("not a tools document", encoding="utf-8")
        subprocess.run(["git", "add", "notes.txt"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "notes"], cwd=self.root, check=True, capture_output=True, text=True)
        not_json = run_cli(
            "check", "--baseline-ref", "HEAD:notes.txt",
            "--candidate", str(self.candidate),
            cwd=self.root,
        )
        self.assertEqual(not_json.returncode, 2)
        self.assertIn("not valid JSON", not_json.stderr)

        for ref, expected in (
            (":notes.txt", "baseline-ref"),
            ("0:notes.txt", "baseline ref"),
            ("-x:notes.txt", "baseline-ref"),
        ):
            with self.subTest(ref=ref):
                rejected = run_cli(
                    "check", "--baseline-ref", ref,
                    "--candidate", str(self.candidate),
                    cwd=self.root,
                )
                self.assertEqual(rejected.returncode, 2)
                self.assertIn(expected, rejected.stderr)

    def test_report_dir_suppresses_stdout_for_written_formats(self) -> None:
        report_dir = self.root / "out"
        result = run_cli(
            "check", str(self.baseline), str(self.candidate),
            "--format", "json",
            "--report-dir", str(report_dir),
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(result.stdout, "")
        parsed = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(parsed["counts"]["breaking"], 1)
        self.assertEqual(parsed["exit_code"], 1)

    def test_html_alias_writes_the_exact_path_and_text_reaches_stdout(self) -> None:
        target = self.root / "custom" / "review.html"
        result = run_cli(
            "check", str(self.baseline), str(self.candidate),
            "--format", "text",
            "--html", str(target),
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("mcp-ward", result.stdout)
        self.assertTrue(target.exists())
        self.assertIn("<!doctype html>", target.read_text(encoding="utf-8").lower())


if __name__ == "__main__":
    unittest.main()
