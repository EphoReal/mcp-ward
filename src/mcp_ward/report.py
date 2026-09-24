"""Human- and machine-readable renderers for compatibility findings."""
from __future__ import annotations

import html
import json
from typing import Any

from .diff import DiffReport
from .i18n import (
    axis_display,
    axis_label,
    display_message,
    display_width,
    gate_label,
    html_impact,
    html_text,
    html_title,
    impact_label,
    label,
    normalize_lang,
    pad_display,
    text,
    zh_span,
)
from .policy import report_blocks


def report_payload(report: DiffReport, profile: str) -> dict[str, Any]:
    return {
        "format_version": 1,
        "profile": profile,
        "counts": report.counts(),
        "max_severity": report.max_severity(),
        "exit_code": 1 if report_blocks(profile, report) else 0,
        "findings": [finding.to_dict() for finding in report.findings],
    }


def render_json(report: DiffReport, profile: str, lang: str = "en") -> str:
    # JSON is intentionally language-neutral. Accepting lang keeps every
    # renderer callable through one API without changing machine semantics.
    normalize_lang(lang)
    return json.dumps(report_payload(report, profile), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _compact(value: Any, limit: int = 100) -> str:
    if value is None:
        return "∅"
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return text if len(text) <= limit else text[: limit - 1] + "…"


_CONTROL_TEXT = {
    "\x00": "\\x00", "\x01": "\\x01", "\x02": "\\x02", "\x03": "\\x03",
    "\x04": "\\x04", "\x05": "\\x05", "\x06": "\\x06", "\x07": "\\x07",
    "\x08": "\\x08", "\x09": "\\x09", "\x0a": "\\n", "\x0b": "\\x0b",
    "\x0c": "\\x0c", "\x0d": "\\r", "\x0e": "\\x0e", "\x0f": "\\x0f",
    "\x10": "\\x10", "\x11": "\\x11", "\x12": "\\x12", "\x13": "\\x13",
    "\x14": "\\x14", "\x15": "\\x15", "\x16": "\\x16", "\x17": "\\x17",
    "\x18": "\\x18", "\x19": "\\x19", "\x1a": "\\x1a", "\x1b": "\\x1b",
    "\x1c": "\\x1c", "\x1d": "\\x1d", "\x1e": "\\x1e", "\x1f": "\\x1f",
    "\x7f": "\\x7f", "\x80": "\\x80", "\x85": "\\x85",
    "\x9b": "\\x9b", "\x9d": "\\x9d", "\x9c": "\\x9c",
    "\u202a": "\\u202a", "\u202b": "\\u202b", "\u202c": "\\u202c",
    "\u202d": "\\u202d", "\u202e": "\\u202e", "\u2066": "\\u2066",
    "\u2067": "\\u2067", "\u2068": "\\u2068", "\u2069": "\\u2069",
}


def _safe_terminal(value: Any) -> str:
    """Render untrusted text without allowing terminal control sequences."""
    if not isinstance(value, str):
        value = _compact(value, 500)
    return "".join(
        _CONTROL_TEXT.get(char, char) for char in value
    )


def safe_error(value: Any) -> str:
    """Public terminal-safe formatter for CLI error and status text."""
    if isinstance(value, BaseException):
        value = str(value)
    elif not isinstance(value, str):
        value = str(value)
    return _safe_terminal(value)


def _active_class(key: str) -> str:
    """Static class attribute for the default filter button."""
    return ' class="active"' if key == "all" else ""


def render_text(report: DiffReport, profile: str, color: bool = False, lang: str = "en") -> str:
    lang = normalize_lang(lang)
    counts = report.counts()
    severity = report.max_severity() or "clean"
    gate_key = "BLOCK" if report_blocks(profile, report) else "PASS"
    lines = [
        f"mcp-ward · {severity.upper() if lang == 'en' else impact_label(lang, severity) if severity != 'clean' else gate_label(lang, 'clean')} · profile: {_safe_terminal(profile)} · {gate_label(lang, gate_key)}",
        f"{counts['breaking']} {label(lang, 'breaking')}  {counts['review']} {label(lang, 'review')}  {counts['additive']} {label(lang, 'additive')}  {counts['cosmetic']} {label(lang, 'cosmetic')}  {counts['unknown']} {label(lang, 'unknown')}",
        "",
    ]
    if not report.findings:
        lines.append(text(lang, "no_changes"))
        return "\n".join(lines) + "\n"
    # One shared column width for every finding row. English keeps its
    # historical 9 cells because `BREAKING` is exactly that wide; a CJK label
    # can be wider, so the column widens to the widest label actually present
    # rather than letting one row push its path to a different column.
    if lang == "both":
        pairs = [impact_label(lang, item.impact).split(" / ") for item in report.findings]
        impact_cells = max(
            (display_width(part) for parts in pairs for part in parts),
            default=0,
        )
    else:
        impact_cells = max(
            (display_width(impact_label(lang, item.impact)) for item in report.findings),
            default=0,
        )
    impact_cells = max(9, impact_cells)

    for finding in report.findings:
        impact = _safe_terminal(impact_label(lang, finding.impact))
        if lang == "both":
            parts = impact.split(" / ")
            impact = " / ".join(pad_display(item, impact_cells) for item in parts)
        else:
            impact = pad_display(impact, impact_cells)
        lines.append(f"{impact} {_safe_terminal(finding.path)}")
        message = display_message(
            lang,
            finding.code,
            finding.message,
            path=finding.path,
            before=finding.before,
            after=finding.after,
        )
        lines.append(f"          {_safe_terminal(message)} [{_safe_terminal(axis_label(lang, finding.axis))} · {_safe_terminal(finding.code)}]")
        if finding.before != finding.after:
            lines.append(f"          − {_safe_terminal(finding.before)}")
            lines.append(f"          + {_safe_terminal(finding.after)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_html(report: DiffReport, profile: str, lang: str = "en") -> str:
    """Render a single-file, dependency-free review surface.

    The report is intentionally an inspect/compare surface, not a marketing
    page: findings are the primary content and every value remains text.
    """
    lang = normalize_lang(lang)
    payload = report_payload(report, profile)
    counts = payload["counts"]
    severity = payload["max_severity"] or "clean"
    gate_key = "BLOCK" if report_blocks(profile, report) else "PASS"
    finding_markup = []
    for finding in payload["findings"]:
        impact = finding["impact"]
        before = _compact(finding.get("before"), 500)
        after = _compact(finding.get("after"), 500)
        message = display_message(
            lang,
            finding["code"],
            finding["message"],
            path=finding["path"],
            before=finding.get("before"),
            after=finding.get("after"),
        )
        html_impact_text = _safe_terminal(html_impact(lang, impact))
        html_axis_text = _safe_terminal(axis_display(lang, finding["axis"]))
        finding_markup.append(
            f'''<article class="finding" data-finding data-impact="{html.escape(impact)}" data-axis="{html.escape(finding['axis'])}" tabindex="0">
  <div class="finding-head"><span class="impact impact-{html.escape(impact)}">{zh_span(html.escape(html_impact_text))}</span><span class="axis">{zh_span(html.escape(html_axis_text))}</span><code>{html.escape(finding['code'])}</code></div>
  <h2>{html.escape(finding['path'])}</h2><p>{zh_span(html.escape(message))}</p>
  <div class="values"><div><span>{zh_span(html.escape(html_text(lang, 'before')))}</span><code>{html.escape(before)}</code></div><div><span>{zh_span(html.escape(html_text(lang, 'after')))}</span><code>{html.escape(after)}</code></div></div>
</article>'''
        )
    if not finding_markup:
        finding_markup.append(
            f'<div class="empty"><strong>{zh_span(html.escape(html_text(lang, "no_changes")))}</strong><span>{zh_span(html.escape(html_text(lang, "no_changes_detail")))}</span></div>'
        )
    document_lang = "zh-CN" if lang == "zh" else "en"
    summary_labels = "".join(
        f'<div class="metric {html.escape(impact)}" data-impact="{html.escape(impact)}" data-count="{counts[impact]}"><strong>{counts[impact]}</strong><span>{zh_span(html.escape(label(lang, impact)))}</span></div>'
        for impact in ("breaking", "review", "additive", "cosmetic", "unknown")
    )
    filters = "".join(
        f'<button{_active_class(key)} data-filter="{html.escape(key)}">{zh_span(html.escape(label(lang, key)))}</button>'
        for key in ("all", "breaking", "review", "additive", "cosmetic", "unknown")
    )
    # Do not inline user/tool-controlled strings in executable script text. The
    # HTML itself is fully escaped above; scripts only contain static code.
    return f'''<!doctype html>
<html lang="{document_lang}" data-theme="dark">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{zh_span(html.escape(html_title(lang, severity)))}</title>
<style>
:root {{ color-scheme: dark; --bg:#0d0f12; --surface:#15181d; --line:#29313a; --ink:#edf1f4; --muted:#9aa5ae; --accent:#f3b562; --good:#72c99b; --warn:#f3c969; --bad:#f28b82; --add:#91b6ed; --shadow:0 18px 50px rgba(0,0,0,.24); --radius:12px; font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }}
:root[data-theme="light"] {{ color-scheme: light; --bg:#f5f6f7; --surface:#fff; --line:#d9dee3; --ink:#1b2025; --muted:#63707a; --accent:#9a5a00; --good:#18794e; --warn:#8a5b00; --bad:#b42318; --add:#245ea8; --shadow:0 12px 30px rgba(26,35,44,.08); }}
* {{ box-sizing:border-box; }} body {{ margin:0; background:var(--bg); color:var(--ink); line-height:1.5; }} button,input {{ font:inherit; }} .shell {{ max-width:1060px; margin:0 auto; padding:32px 22px 64px; }}
header {{ display:flex; justify-content:space-between; gap:20px; align-items:flex-start; margin-bottom:28px; }} .eyebrow {{ color:var(--accent); font-size:.75rem; font-weight:700; letter-spacing:.14em; text-transform:uppercase; }} h1 {{ font-size:clamp(1.8rem,4vw,3rem); line-height:1.05; margin:10px 0 8px; letter-spacing:-.04em; }} .lede {{ color:var(--muted); margin:0; max-width:60ch; }}
.actions {{ display:flex; gap:8px; align-items:center; }} button {{ border:1px solid var(--line); background:var(--surface); color:var(--ink); border-radius:999px; padding:8px 12px; cursor:pointer; transition:border-color .18s, transform .18s; }} button:hover,button:focus-visible {{ border-color:var(--accent); }} button:active {{ transform:scale(.97); }} button:focus-visible,input:focus-visible,.finding:focus-visible {{ outline:2px solid var(--accent); outline-offset:3px; }}
.summary {{ display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); border:1px solid var(--line); background:var(--surface); border-radius:var(--radius); box-shadow:var(--shadow); overflow:hidden; margin-bottom:20px; }} .metric {{ padding:16px; border-right:1px solid var(--line); }} .metric:last-child {{ border-right:0; }} .metric strong {{ display:block; font-size:1.55rem; letter-spacing:-.03em; }} .metric span {{ color:var(--muted); font-size:.78rem; }} .breaking strong {{ color:var(--bad); }} .review strong {{ color:var(--warn); }} .additive strong {{ color:var(--add); }} .cosmetic strong {{ color:var(--muted); }} .unknown strong {{ color:var(--accent); }}
.toolbar {{ display:flex; justify-content:space-between; align-items:center; gap:12px; margin:22px 0 12px; }} .toolbar p {{ color:var(--muted); margin:0; }} .filters {{ display:flex; flex-wrap:wrap; gap:6px; }} .filters button.active {{ background:var(--accent); border-color:var(--accent); color:#18130b; }}
.findings {{ display:grid; gap:10px; }} .finding {{ background:var(--surface); border:1px solid var(--line); border-radius:var(--radius); padding:18px; transition:border-color .18s, opacity .18s, transform .18s; animation:rise .28s ease both; }} .finding:hover {{ border-color:color-mix(in srgb,var(--accent) 55%,var(--line)); transform:translateY(-1px); }} .finding-head {{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; color:var(--muted); font-size:.78rem; }} .impact {{ border-radius:999px; padding:3px 8px; font-size:.7rem; font-weight:800; text-transform:uppercase; letter-spacing:.08em; }} .impact-breaking {{ color:var(--bad); background:color-mix(in srgb,var(--bad) 14%,transparent); }} .impact-review {{ color:var(--warn); background:color-mix(in srgb,var(--warn) 14%,transparent); }} .impact-additive {{ color:var(--add); background:color-mix(in srgb,var(--add) 14%,transparent); }} .impact-cosmetic {{ color:var(--muted); background:color-mix(in srgb,var(--muted) 14%,transparent); }} .impact-unknown {{ color:var(--accent); background:color-mix(in srgb,var(--accent) 16%,transparent); }} .finding h2 {{ font:600 .98rem/1.3 ui-monospace,SFMono-Regular,Consolas,monospace; margin:14px 0 5px; overflow-wrap:anywhere; }} .finding p {{ margin:0; color:var(--muted); }} .values {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:16px; }} .values div {{ min-width:0; background:var(--bg); border:1px solid var(--line); border-radius:8px; padding:9px 11px; }} .values span {{ display:block; color:var(--muted); font-size:.7rem; text-transform:uppercase; letter-spacing:.1em; margin-bottom:4px; }} .values code {{ display:block; color:var(--ink); font: .75rem/1.45 ui-monospace,SFMono-Regular,Consolas,monospace; white-space:pre-wrap; overflow-wrap:anywhere; }}
.empty {{ padding:38px 20px; border:1px dashed var(--line); border-radius:var(--radius); text-align:center; display:grid; gap:6px; }} .empty span {{ color:var(--muted); }} footer {{ color:var(--muted); font-size:.78rem; margin-top:28px; }}
@keyframes rise {{ from {{ opacity:0; transform:translateY(6px); }} to {{ opacity:1; transform:none; }} }} @media (prefers-reduced-motion:reduce) {{ *,*::before,*::after {{ animation:none!important; transition:none!important; scroll-behavior:auto!important; }} }} @media (max-width:650px) {{ .shell {{ padding:22px 14px 48px; }} header {{ display:block; }} .actions {{ margin-top:16px; }} .summary {{ grid-template-columns:repeat(2,1fr); }} .metric {{ border-bottom:1px solid var(--line); }} .metric:nth-child(even) {{ border-right:0; }} .metric:last-child {{ border-bottom:0; }} .values {{ grid-template-columns:1fr; }} .toolbar {{ align-items:flex-start; flex-direction:column; }} }}
</style></head>
<body><main class="shell" data-ready="true" data-gate="{html.escape(gate_key)}" data-profile="{html.escape(profile)}">
<header><div><div class="eyebrow">mcp-ward / {zh_span(html.escape(html_text(lang, 'contract_lens')))}</div><h1>{zh_span(html.escape(html_text(lang, 'title')))}</h1><p class="lede">{zh_span(html.escape(html_text(lang, 'lede')))}</p></div><div class="actions"><button id="theme" aria-label="{html.escape(html_text(lang, 'theme'))}">◐ {zh_span(html.escape(html_text(lang, 'theme_action')))}</button></div></header>
<section class="summary" aria-label="{html.escape(html_text(lang, 'change_summary'))}" data-counts="{html.escape(json.dumps(counts, sort_keys=True))}">{summary_labels}</section>
<div class="toolbar"><p>{zh_span(html.escape(html_text(lang, 'gate')))}: <strong>{zh_span(html.escape(gate_label(lang, gate_key)))}</strong> · profile: <code>{html.escape(profile)}</code></p><div class="filters" role="group" aria-label="{html.escape(html_text(lang, 'filter_findings'))}">{filters}</div></div>
<section class="findings" aria-live="polite">{''.join(finding_markup)}</section>
<footer>{zh_span(html.escape(html_text(lang, 'footer')))}</footer>
</main><script>
const root=document.documentElement; const theme=document.getElementById('theme'); const get=()=>localStorage.getItem('mcp-ward-theme')||'dark'; const set=t=>{{root.dataset.theme=t;localStorage.setItem('mcp-ward-theme',t);}}; set(get()); theme.addEventListener('click',()=>set(root.dataset.theme==='dark'?'light':'dark'));
const buttons=[...document.querySelectorAll('[data-filter]')]; const rows=[...document.querySelectorAll('[data-finding]')]; buttons.forEach(button=>button.addEventListener('click',()=>{{buttons.forEach(x=>x.classList.toggle('active',x===button)); const filter=button.dataset.filter; rows.forEach(row=>row.hidden=filter!=='all'&&row.dataset.impact!==filter);}}));
</script></body></html>'''
