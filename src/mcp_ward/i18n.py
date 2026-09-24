"""Language catalogues for human-readable report output.

Machine-readable finding fields remain stable ASCII keys. Only generated
wording is translated; user-controlled tool data is never translated.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Mapping
from typing import Any

DEFAULT_LANG = "en"
SUPPORTED_LANGS = ("en", "zh", "both")

IMPACTS = {
    "en": {
        "clean": "clean",
        "breaking": "BREAKING",
        "review": "REVIEW",
        "additive": "ADDITIVE",
        "cosmetic": "COSMETIC",
        "unknown": "UNKNOWN",
    },
    "zh": {
        "clean": "无变化",
        "breaking": "破坏性变更",
        "review": "需要审查",
        "additive": "兼容性扩展",
        "cosmetic": "外观变化",
        "unknown": "无法判断",
    },
}

GATES = {
    "en": {"BLOCK": "BLOCK", "PASS": "PASS", "clean": "clean"},
    "zh": {"BLOCK": "需要阻止", "PASS": "通过", "clean": "无变化"},
}

AXES = {
    "en": {"wire": "wire", "agent": "agent", "both": "both"},
    "zh": {"wire": "协议", "agent": "Agent", "both": "协议与 Agent"},
}

MESSAGES = {
    "en": {
        "schema.input.shape.changed": "schema shape changed",
        "schema.output.shape.changed": "schema shape changed",
        "schema.type.accepted.narrowed": "{lead} types narrowed: {removed} removed",
        "schema.type.accepted.widened": "accepted types widened: {added} added",
        "schema.type.produced.changed": "produced types changed: {added} added",
        "schema.type.removed": "type constraint was removed; compatibility can no longer be determined",
        "schema.description.changed": "schema description changed; agent argument guidance may change",
        "schema.title.changed": "schema title changed",
        "schema.enum.narrowed": "{noun} enum values were removed",
        "schema.enum.produced.changed": "new enum values are produced that the baseline did not declare",
        "schema.enum.changed": "{noun} enum values changed",
        "schema.required.added": "field '{name}' became required",
        "schema.required.removed": "field '{name}' became optional",
        "schema.output.required.removed": "guaranteed output field '{name}' is no longer guaranteed",
        "schema.output.required.added": "output field '{name}' is now guaranteed",
        "schema.property.removed": "property '{name}' was removed",
        "schema.property.added": "property '{name}' was added",
        "schema.items.tuple.changed": "tuple-form items require a full JSON Schema comparison",
        "schema.unsupported.changed": "unsupported schema keyword '{name}' changed; the v0.1 engine cannot classify it",
        "schema.bound.changed": "constraint '{name}' changed",
        "schema.presence.changed": "{field} {action}",
        "agent.title.changed": "tool title changed",
        "agent.description.changed": "tool description changed; agent routing or argument generation may change",
        "agent.annotations.changed": "tool annotations changed; trust and side-effect hints may change",
        "wire.unknown.changed": "unknown tool fields changed; the v0.1 engine cannot classify them",
        "tool.removed": "tool '{name}' was removed",
        "tool.added": "tool '{name}' was added",
    },
    "zh": {
        "schema.input.shape.changed": "输入 schema 结构发生变化",
        "schema.output.shape.changed": "输出 schema 结构发生变化",
        "schema.type.accepted.narrowed": "{lead}类型收窄：移除了 {removed}",
        "schema.type.accepted.widened": "接受的类型扩大：添加了 {added}",
        "schema.type.produced.changed": "生成的类型发生变化：添加了 {added}",
        "schema.type.removed": "type 约束被移除，无法再判断兼容性",
        "schema.description.changed": "schema 描述发生变化，Agent 的参数指导可能改变",
        "schema.title.changed": "schema 标题发生变化",
        "schema.enum.narrowed": "{noun} enum 值被移除",
        "schema.enum.produced.changed": "现在会生成基准版本中未声明的新 enum 值",
        "schema.enum.changed": "{noun} enum 值发生变化",
        "schema.required.added": "字段 '{name}' 变成了必填字段",
        "schema.required.removed": "字段 '{name}' 变成了可选字段",
        "schema.output.required.removed": "原本保证返回的输出字段 '{name}' 不再保证存在",
        "schema.output.required.added": "输出字段 '{name}' 现在保证存在",
        "schema.property.removed": "属性 '{name}' 被删除",
        "schema.property.added": "属性 '{name}' 被添加",
        "schema.items.tuple.changed": "tuple 形式的 items 需要完整的 JSON Schema 比较",
        "schema.unsupported.changed": "不支持的 schema 关键字 '{name}' 发生变化，v0.1 无法判断其影响",
        "schema.bound.changed": "约束 '{name}' 发生变化",
        "schema.presence.changed": "{field} {action}",
        "agent.title.changed": "工具标题发生变化",
        "agent.description.changed": "工具描述发生变化，Agent 的工具选择或参数生成可能改变",
        "agent.annotations.changed": "工具 annotations 发生变化，信任和副作用提示可能改变",
        "wire.unknown.changed": "未知工具字段发生变化，v0.1 无法判断其影响",
        "tool.removed": "工具 '{name}' 被删除",
        "tool.added": "工具 '{name}' 被添加",
    },
}

HTML = {
    "en": {
        "report": "report",
        "contract_lens": "contract lens",
        "title": "Surface review",
        "lede": "One deterministic view of protocol compatibility and agent-facing change.",
        "theme": "Theme",
        "change_summary": "Change summary",
        "filter_findings": "Filter findings",
        "gate": "Gate",
        "before": "before",
        "after": "after",
        "no_changes": "No contract changes.",
        "no_changes_detail": "The two surfaces are equivalent under the current projection.",
        "footer": "Generated locally by mcp-ward · values are escaped text · no external assets",
        "axis": "{axis} axis",
        "theme_action": "theme",
    },
    "zh": {
        "report": "报告",
        "contract_lens": "契约检查",
        "title": "工具表面审查",
        "lede": "以确定性方式查看协议兼容性和 Agent 可见变化。",
        "theme": "主题",
        "change_summary": "变化摘要",
        "filter_findings": "筛选变化",
        "gate": "门禁",
        "before": "变更前",
        "after": "变更后",
        "no_changes": "未检测到契约变化。",
        "no_changes_detail": "在当前检查范围内，两份工具表面等价。",
        "footer": "由 mcp-ward 在本地生成 · 所有值均已转义 · 无外部资源",
        "axis": "{axis}维度",
        "theme_action": "主题",
    },
}

TEXT = {
    "en": {
        "no_changes": "No contract changes detected.",
    },
    "zh": {
        "no_changes": "未检测到契约变化。",
    },
}

LABELS = {
    "en": {
        "breaking": "breaking",
        "review": "review",
        "additive": "additive",
        "cosmetic": "cosmetic",
        "unknown": "unknown",
        "all": "all",
    },
    "zh": {
        "breaking": "破坏性变更",
        "review": "需要审查",
        "additive": "兼容性扩展",
        "cosmetic": "外观变化",
        "unknown": "无法判断",
        "all": "全部",
    },
}


def normalize_lang(value: str) -> str:
    """Accept common locale spellings and reject unsupported values."""
    if not isinstance(value, str):
        raise ValueError("lang must be en, zh, or both")
    normalized = value.strip().lower().replace("_", "-")
    if normalized in {"zh", "cn", "zh-cn", "zh-sg", "zh-hans"}:
        return "zh"
    if normalized in {"en", "en-us", "en-gb"}:
        return "en"
    if normalized in {"both", "en-zh", "zh-en"}:
        return "both"
    raise ValueError("lang must be en, zh, or both")


def display_width(value: str) -> int:
    """Terminal cell width of `value`.

    East-Asian wide and fullwidth glyphs occupy two cells and combining marks
    occupy none, so plain `len()` padding makes a CJK column look ragged even
    though the character counts match.

    Emoji zero-width-joiner sequences and variation selectors are collapsed
    first: a family emoji is one grapheme drawn in about two cells, but summing
    its component code points would report a wildly wrong width.
    """
    # A ZWJ sequence joins code points into a single glyph, so the whole run
    # counts once. Variation Selectors (U+FE0E/U+FE0F) add no cell. Ordinary
    # multi-character text (ASCII, CJK) is summed per character as usual.
    segments = [segment for segment in value.split("\u200d") if segment]
    if not segments:
        return 0

    def segment_width(segment: str) -> int:
        cleaned = segment.replace("\ufe0e", "").replace("\ufe0f", "")
        width = 0
        for char in cleaned:
            if unicodedata.combining(char):
                continue
            # Regional indicators pair into one two-cell flag glyph.
            if 0x1F1E6 <= ord(char) <= 0x1F1FF:
                width += 1
                continue
            width += 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
        return width

    if len(segments) == 1:
        return segment_width(segments[0])
    # A joined run renders as a single glyph, so it occupies at most two cells
    # however many code points it contains.
    joined_width = sum(segment_width(item) for item in segments)
    return 2 if joined_width > 2 else joined_width


def pad_display(value: str, cells: int) -> str:
    """Left-justify `value` to `cells` terminal columns, never truncating."""
    return value + " " * max(0, cells - display_width(value))


def _pair(table: Mapping[str, Mapping[str, str]], lang: str, key: str, fallback: str) -> str:
    if lang == "both":
        english = table["en"].get(key, fallback)
        chinese = table["zh"].get(key, english)
        return f"{english} / {chinese}"
    return table[lang].get(key, fallback)


def impact_label(lang: str, impact: str) -> str:
    lang = normalize_lang(lang)
    fallback = impact.upper()
    return _pair(IMPACTS, lang, impact, fallback)


def gate_label(lang: str, gate: str) -> str:
    lang = normalize_lang(lang)
    return _pair(GATES, lang, gate, gate)


def axis_label(lang: str, axis: str) -> str:
    lang = normalize_lang(lang)
    return _pair(AXES, lang, axis, axis)


def axis_display(lang: str, axis: str) -> str:
    """Axis wording for HTML, where default English stays byte-compatible."""
    lang = normalize_lang(lang)
    if lang == "both":
        return f"{HTML['en']['axis'].format(axis=axis)} / {HTML['zh']['axis'].format(axis=AXES['zh'].get(axis, axis))}"
    return HTML[lang]["axis"].format(axis=AXES[lang].get(axis, axis))


def html_impact(lang: str, impact: str) -> str:
    """Impact badge wording; default English keeps the raw impact token."""
    lang = normalize_lang(lang)
    if lang == "en":
        return impact
    return _pair(IMPACTS, lang, impact, impact)


def html_title(lang: str, severity: str) -> str:
    """Document title; default English keeps the pre-i18n wording."""
    lang = normalize_lang(lang)
    if lang == "en":
        return f"mcp-ward · {severity} {HTML['en']['report']}"
    if lang == "zh":
        return f"mcp-ward · {IMPACTS['zh'].get(severity, severity)} {HTML['zh']['report']}"
    english = f"{severity} {HTML['en']['report']}"
    chinese = f"{IMPACTS['zh'].get(severity, severity)} {HTML['zh']['report']}"
    return f"mcp-ward · {english} / {chinese}"


def zh_span(text: str) -> str:
    """Tag the Chinese half of an `en / zh` pair so screen readers switch voice.

    The input must already be HTML-escaped: the tags added here are static, and
    only a literal separator followed by CJK text is ever wrapped.
    """
    head, separator, tail = text.partition(" / ")
    if separator and any("\u3000" <= char <= "\u9fff" or "\uff00" <= char <= "\uffef" for char in tail):
        return f'{head} / <span lang="zh-CN">{tail}</span>'
    return text


def label(lang: str, key: str) -> str:
    lang = normalize_lang(lang)
    return _pair(LABELS, lang, key, key)


def html_text(lang: str, key: str) -> str:
    lang = normalize_lang(lang)
    return _pair(HTML, lang, key, key)


def text(lang: str, key: str) -> str:
    lang = normalize_lang(lang)
    return _pair(TEXT, lang, key, key)


def _compact(value: Any) -> str:
    if value is None:
        return "∅"
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _quoted_name(message: str) -> str:
    match = re.search(r"^[^']*'(.+)'(?:\s+(?:was|became|is|are|changed|removed|added|is no longer|is now)\b.*)?$", message)
    return match.group(1) if match else ""


def _name_from_path(path: str, fallback: str) -> str:
    if path:
        return path.rsplit(".", 1)[-1]
    return fallback


def _type_values(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, list):
        return {str(item) for item in value}
    return {str(value)}


def _compact_types(values: list[str]) -> str:
    """Use the same list spelling as Finding.message when formatting deltas."""
    return repr(values).replace('"', "'")


def _path_direction(path: str) -> str:
    """Return `input` or `output` for a finding path.

    The direction is decided by the tool-surface schema root, not by a
    substring search: an output property may legitimately be named
    `inputSchema`, as in `tools.x.outputSchema.inputSchema.type`. The first
    schema segment wins, because it is the outermost one.
    """
    for segment in path.split("."):
        if segment == "inputSchema":
            return "input"
        if segment == "outputSchema":
            return "output"
    # Fall back to input, matching the engine's "accepted" wording for
    # findings whose path has no schema root.
    return "input"


def _localized_type_message(code: str, path: str, before: Any, after: Any) -> str:
    """Translate the type findings without changing the engine's semantics."""
    direction = _path_direction(path)
    old = _type_values(before)
    new = _type_values(after)
    removed = _compact(sorted(old - new))
    added = _compact(sorted(new - old))
    if code == "schema.type.accepted.narrowed":
        if not old:
            verb = "接受" if direction == "input" else "生成"
            return f"此前没有 type 约束；现在只{verb} {added}"
        return f"接受的类型收窄：移除了 {removed}" if direction == "input" else f"生成的类型收窄：移除了 {removed}"
    if code == "schema.type.accepted.widened":
        return f"接受的类型扩大：添加了 {added}"
    return f"生成的类型发生变化：添加了 {added}"


def _localized_enum_message(code: str, path: str) -> str:
    noun = "接受" if _path_direction(path) == "input" else "生成"
    if code == "schema.enum.narrowed":
        return f"{noun}的 enum 值被移除"
    if code == "schema.enum.produced.changed":
        return "现在会生成基准版本中未声明的新 enum 值"
    return f"{noun}的 enum 值发生变化"


def _message_values(code: str, fallback: str, path: str, lang: str = "en") -> dict[str, Any]:
    name = _quoted_name(fallback) or _name_from_path(path, "")
    if code == "schema.presence.changed":
        action = "出现" if lang == "zh" else "appeared"
        if "was removed" in fallback:
            action = "被移除" if lang == "zh" else "was removed"
        return {"field": name or _name_from_path(path, "schema"), "action": action}
    return {"name": name}


def _format_message(lang: str, code: str, fallback: str, path: str, before: Any, after: Any) -> str:
    lang = normalize_lang(lang)
    if code not in MESSAGES["en"] or code not in MESSAGES["zh"]:
        return fallback
    if lang == "en":
        # The engine's original English message is the compatibility contract;
        # never replace it with a lossy template reconstructed from values.
        return fallback

    if code in {
        "schema.type.accepted.narrowed",
        "schema.type.accepted.widened",
        "schema.type.produced.changed",
    }:
        localized = _localized_type_message(code, path, before, after)
    elif code in {"schema.enum.narrowed", "schema.enum.changed", "schema.enum.produced.changed"}:
        localized = _localized_enum_message(code, path)
    else:
        template = MESSAGES["zh"][code]
        try:
            localized = template.format(**_message_values(code, fallback, path, "zh"))
        except (KeyError, IndexError, TypeError, ValueError):
            return fallback
    return localized if lang == "zh" or localized == fallback else f"{fallback} / {localized}"


def display_message(
    lang: str,
    code: str,
    fallback: str,
    *,
    path: str = "",
    before: Any = None,
    after: Any = None,
) -> str:
    """Translate known finding codes while preserving custom messages."""
    return _format_message(lang, code, fallback, path, before, after)
