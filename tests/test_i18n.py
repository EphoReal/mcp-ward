import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

from mcp_ward.diff import DiffReport, Finding
from mcp_ward.i18n import (
    AXES,
    GATES,
    HTML,
    IMPACTS,
    LABELS,
    MESSAGES,
    TEXT,
    display_message,
    display_width,
    normalize_lang,
    pad_display,
)
from mcp_ward.report import render_html, render_json, render_text


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

    def handle_endtag(self, tag: str) -> None:
        if tag in self.void:
            return
        if not self.stack or self.stack[-1] != tag:
            raise AssertionError(f"unbalanced closing tag: {tag}")
        self.stack.pop()


def finding(impact: str = "breaking", code: str = "schema.required.added") -> Finding:
    return Finding(
        code,
        "tools.search.inputSchema.limit",
        "wire",
        impact,
        "field 'limit' became required",
        after={"type": "string"},
    )


class LanguageCatalogTests(unittest.TestCase):
    def test_locale_aliases_normalize(self) -> None:
        self.assertEqual(normalize_lang("zh-CN"), "zh")
        self.assertEqual(normalize_lang("cn"), "zh")
        self.assertEqual(normalize_lang("EN_us"), "en")
        self.assertEqual(normalize_lang("zh-en"), "both")

    def test_catalog_key_sets_match(self) -> None:
        for table in (IMPACTS, GATES, AXES, MESSAGES, HTML, LABELS, TEXT):
            with self.subTest(table=table):
                self.assertEqual(set(table["en"]), set(table["zh"]))

    def test_unknown_language_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "en, zh, or both"):
            normalize_lang("fr")

    def test_every_diff_code_is_translated(self) -> None:
        """No engine code may silently fall back to English-only wording."""
        engine = Path(__file__).resolve().parents[1] / "src" / "mcp_ward" / "diff.py"
        source = engine.read_text(encoding="utf-8")
        self.assertIn('code = f"schema.{direction}.shape.changed"', source)
        codes = {f"schema.{direction}.shape.changed" for direction in ("input", "output")}
        # Everything else is a plain quoted literal, either passed to _finding
        # or assigned to `code` in a ternary.
        codes |= set(re.findall(r'"((?:schema|agent|wire|tool)\.[a-z.]+)"', source))
        self.assertGreaterEqual(len(codes), 25)
        self.assertEqual(
            set(MESSAGES["en"]) - codes, set(), "catalogue has codes the engine never emits"
        )
        self.assertEqual(
            codes - set(MESSAGES["en"]), set(), "engine emits codes missing from the catalogue"
        )
        self.assertEqual(set(MESSAGES["zh"]), codes)

    def test_translated_templates_use_matching_placeholders(self) -> None:
        for code, english in MESSAGES["en"].items():
            with self.subTest(code=code):
                self.assertEqual(
                    set(re.findall(r"\{(\w+)\}", english)),
                    set(re.findall(r"\{(\w+)\}", MESSAGES["zh"][code])),
                )
                MESSAGES["zh"][code].format(**{name: "x" for name in re.findall(r"\{(\w+)\}", english)})

    def test_every_format_works_for_every_language(self) -> None:
        for code in MESSAGES["en"]:
            for lang in ("en", "zh", "both"):
                with self.subTest(code=code, lang=lang):
                    normalized = normalize_lang(lang)
                    message = display_message(
                        normalized, code, "original english message",
                        path="tools.x.inputSchema.limit", before=["a"], after=["b"],
                    )
                    self.assertTrue(message.strip())
                    if normalized == "zh" and code != "schema.presence.changed":
                        self.assertNotIn("original english message", message)


class I18nReportTests(unittest.TestCase):
    def test_zh_text_report_uses_translated_labels_and_message(self) -> None:
        report = DiffReport([finding()])
        text = render_text(report, "agent", lang="zh")
        self.assertIn("破坏性变更", text)
        self.assertIn("需要阻止", text)
        self.assertIn("字段 'limit' 变成了必填字段", text)

    def test_default_english_html_keeps_pre_i18n_wording(self) -> None:
        page = render_html(DiffReport([finding()]), "agent")
        self.assertIn("<title>mcp-ward · breaking report</title>", page)
        self.assertIn('<span class="impact impact-breaking">breaking</span>', page)
        self.assertIn('<span class="axis">wire axis</span>', page)
        self.assertIn("<p>field &#x27;limit&#x27; became required</p>", page)
        self.assertNotIn("lang=\"zh-CN\"", page)

    def test_both_html_marks_the_chinese_half_with_a_lang_attribute(self) -> None:
        page = render_html(DiffReport([finding()]), "agent", lang="both")
        self.assertIn('<span class="axis">wire axis / <span lang="zh-CN">', page)
        self.assertIn("<span lang=\"zh-CN\">字段 ", page)
        parser = Balance()
        parser.feed(page)
        parser.close()
        self.assertEqual(parser.stack, [])
        self.assertNotIn("工具表面审查 / Surface review", page)

    def test_both_html_marks_all_chinese_halves_not_just_findings(self) -> None:
        """Every bilingual label must switch voice for screen readers.

        The page chrome used to emit Chinese under an English document
        language, so a screen reader pronounced the Chinese with an English
        voice. Every `en / zh` pair gets the Chinese half wrapped.
        """
        page = render_html(DiffReport([finding()]), "agent", lang="both")
        for english, chinese in (
            ("Surface review", "工具表面审查"),
            ("contract lens", "契约检查"),
            ("before", "变更前"),
            ("after", "变更后"),
            ("breaking", "破坏性变更"),
            ("BLOCK", "需要阻止"),
            ("theme", "主题"),
        ):
            with self.subTest(label=english):
                self.assertIn(f'{english} / <span lang="zh-CN">{chinese}</span>', page)
        parser = Balance()
        parser.feed(page)
        parser.close()
        self.assertEqual(parser.stack, [])

    def test_single_language_html_has_no_nested_lang_span(self) -> None:
        en = render_html(DiffReport([finding()]), "agent")
        zh = render_html(DiffReport([finding()]), "agent", lang="zh")
        self.assertNotIn('lang="zh-CN"', en)
        self.assertNotIn('<span lang="zh-CN">', zh)

    def test_display_width_ignores_emoji_joiners_and_overshoots(self) -> None:
        """Emoji ZWJ sequences and keycaps occupy about two cells, not eleven."""
        for family in ("\U0001f468‍\U0001f469‍\U0001f467‍\U0001f466", "\U0001f3f3️‍\U0001f308"):
            self.assertLessEqual(display_width(family), 2, repr(family))
        # A single wide emoji still counts as two cells.
        self.assertEqual(display_width("\U0001f600"), 2)

    def test_zh_html_document_declares_chinese(self) -> None:
        page = render_html(DiffReport([finding()]), "agent", lang="zh")
        self.assertIn('<html lang="zh-CN"', page)
        self.assertIn("<title>mcp-ward · 破坏性变更 报告</title>", page)

    def test_both_text_report_contains_english_and_chinese(self) -> None:
        report = DiffReport([finding()])
        text = render_text(report, "agent", lang="both")
        self.assertIn("BREAKING / 破坏性变更", text)
        self.assertIn("field 'limit' became required / 字段 'limit' 变成了必填字段", text)

    def test_json_language_modes_are_byte_identical(self) -> None:
        report = DiffReport([finding()])
        outputs = [render_json(report, "agent", lang=lang) for lang in ("en", "zh", "both")]
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[0], outputs[2])

    def test_zh_html_is_escaped_balanced_and_localized(self) -> None:
        report = DiffReport([Finding(
            "schema.required.added",
            'tools.x"><script>alert(1)</script>',
            "wire",
            "breaking",
            "field 'x' became required",
            after={"type": "<unsafe>"},
        )])
        page = render_html(report, "agent", lang="zh")
        parser = Balance()
        parser.feed(page)
        parser.close()
        self.assertEqual(parser.stack, [])
        self.assertIn("工具表面审查", page)
        self.assertIn("字段 &#x27;x&#x27; 变成了必填字段", page)
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;", page)
        self.assertIn("无外部资源", page)

    def test_both_html_contains_both_language_labels(self) -> None:
        page = render_html(DiffReport([finding()]), "agent", lang="both")
        self.assertIn("Surface review / <span lang=\"zh-CN\">工具表面审查</span>", page)
        self.assertIn("breaking / <span lang=\"zh-CN\">破坏性变更</span>", page)
        self.assertIn("before / <span lang=\"zh-CN\">变更前</span>", page)

    def test_custom_api_call_with_message_keeps_fallback(self) -> None:
        custom = Finding("future.code", "tools.x", "wire", "breaking", "Future warning.")
        text = render_text(DiffReport([custom]), "agent", lang="zh")
        self.assertIn("Future warning.", text)

    def test_default_english_preserves_dynamic_generated_message(self) -> None:
        generated = Finding(
            "schema.type.accepted.narrowed",
            "tools.x.inputSchema.type",
            "wire",
            "breaking",
            "type constraint added where none was declared; only ['string'] is now accepted",
            before=None,
            after=["string"],
        )
        report = DiffReport([generated])
        self.assertIn("only ['string'] is now accepted", render_text(report, "agent"))
        self.assertIn(
            "type constraint added where none was declared; only ['string'] is now accepted /",
            render_text(report, "agent", lang="both"),
        )
        self.assertIn(
            "type constraint added where none was declared; only ['string'] is now accepted / 此前没有 type 约束；现在只接受 [\"string\"]",
            render_text(report, "agent", lang="both"),
        )

    def test_zh_presence_message_is_fully_localized(self) -> None:
        presence = Finding(
            "schema.presence.changed",
            "tools.x.outputSchema",
            "wire",
            "breaking",
            "outputSchema appeared",
            before=None,
            after={"type": "object"},
        )
        text = render_text(DiffReport([presence]), "agent", lang="zh")
        self.assertIn("outputSchema 出现", text)
        self.assertNotIn("appeared", text)

    def test_presence_removed_is_localized_correctly(self) -> None:
        presence = Finding(
            "schema.presence.changed",
            "tools.x.inputSchema",
            "wire",
            "breaking",
            "inputSchema was removed",
            before={"type": "object"},
            after=None,
        )
        text = render_text(DiffReport([presence]), "agent", lang="zh")
        self.assertIn("inputSchema 被移除", text)
        self.assertNotIn("was removed", text)

    def test_both_mode_preserves_english_and_adds_chinese_for_dynamic_codes(self) -> None:
        for code, path, message, before, after in (
            (
                "schema.type.accepted.narrowed",
                "tools.x.inputSchema.type",
                "accepted types narrowed: ['integer'] removed",
                ["integer", "string"],
                ["string"],
            ),
            (
                "schema.enum.changed",
                "tools.x.outputSchema.results.enum",
                "produced enum values changed",
                ["a"],
                ["a", "b"],
            ),
        ):
            with self.subTest(code=code):
                finding = Finding(code, path, "wire", "breaking", message, before, after)
                text = render_text(DiffReport([finding]), "agent", lang="both")
                self.assertIn(f"{message} /", text)

    def test_clean_report_preserves_english_clean_heading(self) -> None:
        text = render_text(DiffReport([]), "agent")
        self.assertIn("mcp-ward · CLEAN", text)
        self.assertIn("mcp-ward · 无变化", render_text(DiffReport([]), "agent", lang="zh"))

    def test_type_narrowing_does_not_claim_a_missing_baseline_constraint(self) -> None:
        narrowing = Finding(
            "schema.type.accepted.narrowed",
            "tools.x.inputSchema.type",
            "wire",
            "breaking",
            "type constraint added where none was declared; only ['string'] is now accepted",
            before=None,
            after=["string"],
        )
        text = render_text(DiffReport([narrowing]), "agent", lang="zh")
        self.assertIn("此前没有 type 约束；现在只接受 [\"string\"]", text)
        self.assertIn("type constraint added where none was declared", render_text(DiffReport([narrowing]), "agent", lang="both"))

    def test_type_narrowing_with_existing_baseline_uses_removed_types(self) -> None:
        narrowing = Finding(
            "schema.type.accepted.narrowed",
            "tools.x.inputSchema.type",
            "wire",
            "breaking",
            "accepted types narrowed: ['integer'] removed",
            before=["integer", "string"],
            after=["string"],
        )
        text = render_text(DiffReport([narrowing]), "agent", lang="zh")
        self.assertIn("接受的类型收窄：移除了 [\"integer\"]", text)
        self.assertNotIn("此前没有 type 约束", text)

    def test_cjk_text_labels_keep_paths_in_the_same_display_column(self) -> None:
        """Column alignment must be measured in terminal cells, not characters.

        A CJK glyph occupies two cells, so comparing string indexes would
        report a false green while the rendered report is visibly ragged.
        """
        report = DiffReport([
            finding(),
            Finding("tool.added", "tools.other", "wire", "additive", "tool 'other' was added"),
            Finding("agent.title.changed", "tools.x.title", "agent", "cosmetic", "title changed"),
        ])

        def cells(value: str) -> int:
            return display_width(value)

        for lang in ("en", "zh", "both"):
            columns = set()
            for line in render_text(report, "agent", lang=lang).splitlines():
                if "tools." in line and not line.startswith(" "):
                    columns.add(cells(line[: line.index("tools.")]))
            with self.subTest(lang=lang):
                self.assertEqual(len(columns), 1, f"ragged columns in {lang}: {columns}")

    def test_display_width_helper_matches_known_cjk_cells(self) -> None:
        # Guards the padding helper itself against a future regression.
        self.assertEqual(display_width("abc"), 3)
        self.assertEqual(display_width("破坏性"), 6)        # 3 glyphs x 2 cells
        self.assertEqual(display_width("破坏性变更"), 10)   # 5 glyphs x 2 cells
        self.assertEqual(display_width("abc破坏性"), 9)     # 3 + 6
        self.assertEqual(pad_display("破坏性", 10), "破坏性    ")
        self.assertEqual(pad_display("BREAKING", 9), "BREAKING ")  # 8 chars -> 9 cells
        self.assertEqual(pad_display("BREAKING", 8), "BREAKING")
        # Never truncates a label that is already wider than the target.
        self.assertEqual(pad_display("兼容性扩展", 4), "兼容性扩展")

if __name__ == "__main__":
    unittest.main()
