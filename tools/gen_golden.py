"""Generate the default-English golden fixtures from the current tree.

The renderer is required to stay byte-compatible with the pre-i18n English
output. This script (re)creates tests/golden/ from the tracked example inputs so
the fixture can be regenerated deliberately rather than hand-edited.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mcp_ward.diff import DiffReport, diff_surfaces  # noqa: E402
from mcp_ward.report import render_html, render_json, render_text  # noqa: E402
from mcp_ward.snapshot import normalize_surface  # noqa: E402

GOLDEN = ROOT / "tests" / "golden" / "default_en"


def main() -> int:
    baseline = json.loads((ROOT / "examples" / "tools-list.json").read_text(encoding="utf-8"))
    candidate = json.loads((ROOT / "examples" / "tools-list-breaking.json").read_text(encoding="utf-8"))
    report = DiffReport(diff_surfaces(normalize_surface(baseline), normalize_surface(candidate)))
    empty = DiffReport([])

    outputs = {
        "report.txt": render_text(report, "agent"),
        "report.html": render_html(report, "agent"),
        "report.json": render_json(report, "agent"),
        "empty.txt": render_text(empty, "observe"),
        "empty.html": render_html(empty, "observe"),
    }
    GOLDEN.mkdir(parents=True, exist_ok=True)
    for name, content in outputs.items():
        (GOLDEN / name).write_text(content, encoding="utf-8", newline="\n")
        print(f"wrote {name} ({len(content)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
