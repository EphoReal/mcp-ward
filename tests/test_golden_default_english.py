"""Default-English output must stay byte-compatible with the pre-i18n report.

Regenerate the fixtures deliberately with `python tools/gen_golden.py`; never
hand-edit them. A diff here means a user-visible English output change, which
needs a deliberate decision rather than an accidental one.
"""
import json
import unittest
from pathlib import Path

from mcp_ward.diff import DiffReport, diff_surfaces
from mcp_ward.report import render_html, render_json, render_text
from mcp_ward.snapshot import normalize_surface

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = Path(__file__).resolve().parent / "golden" / "default_en"


def load(name: str) -> str:
    return GOLDEN.joinpath(name).read_text(encoding="utf-8")


def example_report() -> DiffReport:
    baseline = json.loads((ROOT / "examples" / "tools-list.json").read_text(encoding="utf-8"))
    candidate = json.loads((ROOT / "examples" / "tools-list-breaking.json").read_text(encoding="utf-8"))
    return DiffReport(diff_surfaces(normalize_surface(baseline), normalize_surface(candidate)))


class DefaultEnglishGoldenTests(unittest.TestCase):
    def test_text_report_matches_golden(self) -> None:
        self.assertEqual(render_text(example_report(), "agent"), load("report.txt"))

    def test_html_report_matches_golden(self) -> None:
        self.assertEqual(render_html(example_report(), "agent"), load("report.html"))

    def test_json_report_matches_golden(self) -> None:
        self.assertEqual(render_json(example_report(), "agent"), load("report.json"))

    def test_empty_text_report_matches_golden(self) -> None:
        self.assertEqual(render_text(DiffReport([]), "observe"), load("empty.txt"))

    def test_empty_html_report_matches_golden(self) -> None:
        self.assertEqual(render_html(DiffReport([]), "observe"), load("empty.html"))

    def test_golden_text_keeps_pre_i18n_heading_case(self) -> None:
        self.assertTrue(load("empty.txt").startswith("mcp-ward · CLEAN · profile: observe · PASS\n"))


if __name__ == "__main__":
    unittest.main()
