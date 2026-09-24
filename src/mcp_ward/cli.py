"""Command-line entry point for mcp-ward."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .diff import DiffReport, diff_surfaces
from .i18n import normalize_lang
from .policy import PROFILES, report_blocks
from .report import render_html, render_json, render_text, safe_error
from .snapshot import SnapshotError, load_document, normalize_surface, snapshot_bytes


def _formats(value: str) -> list[str]:
    formats = [item.strip().lower() for item in value.split(",") if item.strip()]
    allowed = {"text", "json", "html"}
    unknown = sorted(set(formats) - allowed)
    if unknown:
        raise argparse.ArgumentTypeError(
            "format must contain text, json, html (comma-separated); unknown: "
            + ", ".join(unknown)
        )
    if not formats:
        raise argparse.ArgumentTypeError("format must contain at least one renderer")
    return list(dict.fromkeys(formats))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcp-ward",
        description="Review MCP tool-surface changes without an LLM.",
    )
    parser.add_argument("--version", action="version", version="mcp-ward 0.1.0")
    sub = parser.add_subparsers(dest="command", required=True)

    snap = sub.add_parser("snapshot", help="normalize a raw tools/list JSON document")
    snap.add_argument("input", type=Path)
    snap.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("mcp-ward.snapshot.json"),
        help="snapshot destination (default: mcp-ward.snapshot.json)",
    )

    check = sub.add_parser("check", help="compare a baseline and candidate surface")
    check.add_argument("baseline", nargs="?", type=Path)
    check.add_argument("candidate", nargs="?", type=Path)
    check.add_argument(
        "--baseline-ref",
        help="read a committed baseline as REF:PATH using git show",
    )
    check.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        default="agent",
        help="gate policy (default: agent)",
    )
    check.add_argument(
        "--format",
        type=_formats,
        default=_formats("text"),
        metavar="{text,json,html}",
        help="stdout and report formats (comma-separated)",
    )
    check.add_argument(
        "--candidate",
        dest="candidate_option",
        type=Path,
        help="candidate JSON path; use this with --baseline-ref",
    )
    check.add_argument(
        "--report-dir",
        type=Path,
        help=(
            "write requested formats to this directory as report.* files; "
            "only formats without a file destination are echoed to stdout"
        ),
    )
    check.add_argument(
        "--html",
        type=Path,
        help="also write HTML to this exact path (legacy alias)",
    )
    check.add_argument(
        "--lang",
        default="en",
        metavar="{en,zh,both}",
        help=(
            "language for human-readable report text (default: en); "
            "accepts en, zh, both and common locale spellings such as zh-CN"
        ),
    )
    return parser


def _git_show(ref: str) -> list[dict]:
    if ":" not in ref:
        raise SnapshotError("--baseline-ref must look like REF:PATH")
    commitish, separator, path = ref.partition(":")
    if not commitish or not separator or not path or commitish.startswith("-"):
        raise SnapshotError("--baseline-ref must use a non-empty commit-ish before ':'")
    if any(char in commitish for char in "\x00\n\r"):
        raise SnapshotError("--baseline-ref contains an invalid control character")
    verify = subprocess.run(
        ["git", "rev-parse", "--verify", f"{commitish}^{{commit}}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if verify.returncode:
        detail = verify.stderr.strip() or f"git exited with {verify.returncode}"
        raise SnapshotError(f"invalid git baseline ref {commitish!r}: {detail}")
    verified_sha = verify.stdout.strip()
    if not verified_sha or len(verified_sha) != 40 or any(char not in "0123456789abcdefABCDEF" for char in verified_sha):
        raise SnapshotError("git rev-parse returned an invalid commit id")
    completed = subprocess.run(
        ["git", "show", f"{verified_sha}:{path}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if completed.returncode:
        detail = completed.stderr.strip() or f"git exited with {completed.returncode}"
        raise SnapshotError(f"git show {ref} failed: {detail}")
    try:
        document = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SnapshotError(f"git baseline {ref} is not valid JSON: {exc}") from exc
    return normalize_surface(document)


def _load_baseline(args: argparse.Namespace) -> list[dict]:
    if args.baseline_ref:
        if args.baseline:
            raise SnapshotError("use either a baseline path or --baseline-ref, not both")
        return _git_show(args.baseline_ref)
    if args.baseline:
        return load_document(args.baseline)
    raise SnapshotError("check requires a baseline path or --baseline-ref")


RENDERERS = {
    "text": ("report.txt", render_text),
    "json": ("report.json", render_json),
    "html": ("report.html", render_html),
}


def _report_destinations(
    formats: list[str],
    report_dir: Path | None,
    html_path: Path | None,
) -> dict[str, Path]:
    """Map each requested format to a file destination, if it has one."""
    destinations: dict[str, Path] = {}
    if report_dir:
        for fmt in formats:
            destinations[fmt] = report_dir / RENDERERS[fmt][0]
    if html_path:
        # The legacy alias always writes HTML, even when html is not one of
        # the stdout/report-dir formats.
        destinations["html"] = html_path
    return destinations


def _emit_reports(
    report: DiffReport,
    profile: str,
    formats: list[str],
    destinations: dict[str, Path],
    lang: str = "en",
) -> None:
    lang = normalize_lang(lang)
    for fmt in formats:
        if fmt not in destinations:
            sys.stdout.write(RENDERERS[fmt][1](report, profile, lang=lang))
    for fmt, destination in destinations.items():
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(RENDERERS[fmt][1](report, profile, lang=lang).encode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "snapshot":
            surface = load_document(args.input)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(snapshot_bytes({"tools": surface}))
            print(f"snapshot written: {safe_error(args.output)} ({len(surface)} tool(s))")
            return 0

        if args.profile not in PROFILES:
            raise SnapshotError(f"unknown profile: {args.profile}")
        baseline = _load_baseline(args)
        if args.candidate and args.candidate_option:
            raise SnapshotError("candidate was supplied both positionally and with --candidate")
        candidate_path = args.candidate_option or args.candidate
        if not candidate_path:
            raise SnapshotError("check requires a candidate JSON path")
        candidate = load_document(candidate_path)
        report = DiffReport(diff_surfaces(baseline, candidate))

        destinations = _report_destinations(args.format, args.report_dir, args.html)
        _emit_reports(report, args.profile, args.format, destinations, lang=args.lang)
        return 1 if report_blocks(args.profile, report) else 0
    except (SnapshotError, ValueError, OSError) as exc:
        print(f"mcp-ward: error: {safe_error(exc)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
