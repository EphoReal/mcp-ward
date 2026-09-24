import unittest

from mcp_ward.diff import DiffReport, Finding, diff_surfaces
from mcp_ward.report import render_text
from mcp_ward.snapshot import normalize_surface


class ReviewRegressionTests(unittest.TestCase):
    def test_text_report_neutralizes_axis_control_sequences(self) -> None:
        finding = Finding(
            code="agent.description.changed",
            path="tools.x",
            axis="\x1b]0;pwn\x07",
            impact="review",
            message="description changed",
        )
        text = render_text(DiffReport([finding]), "agent")
        self.assertNotIn("\x1b", text)
        self.assertNotIn("\x07", text)
        self.assertIn("\\x1b", text)

    def test_added_type_constraint_is_described_as_a_new_constraint(self) -> None:
        before = normalize_surface({
            "tools": [{
                "name": "x",
                "inputSchema": {
                    "type": "object",
                    "properties": {"value": {}},
                },
            }]
        })
        after = normalize_surface({
            "tools": [{
                "name": "x",
                "inputSchema": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                },
            }]
        })
        finding = diff_surfaces(before, after)[0]
        self.assertEqual(finding.code, "schema.type.accepted.narrowed")
        self.assertIsNone(finding.before)
        self.assertEqual(finding.after, ["string"])
        self.assertIn("此前没有 type 约束", render_text(DiffReport([finding]), "wire", lang="zh"))
        self.assertIn('["string"]', render_text(DiffReport([finding]), "wire", lang="zh"))

    def test_single_quotes_in_names_are_not_truncated(self) -> None:
        finding = Finding(
            code="tool.removed",
            path="tools.quote'name",
            axis="wire",
            impact="breaking",
            message="tool 'quote'name' was removed",
        )
        text = render_text(DiffReport([finding]), "wire", lang="zh")
        self.assertIn("工具 'quote'name' 被删除", text)

    def test_presence_removal_is_fully_translated(self) -> None:
        finding = Finding(
            code="schema.presence.changed",
            path="tools.x.outputSchema",
            axis="wire",
            impact="breaking",
            message="outputSchema was removed",
            before={"type": "object"},
            after=None,
        )
        text = render_text(DiffReport([finding]), "wire", lang="zh")
        self.assertIn("outputSchema 被移除", text)
        self.assertNotIn("was removed", text)
        both = render_text(DiffReport([finding]), "wire", lang="both")
        self.assertIn("outputSchema was removed / outputSchema 被移除", both)

    def test_output_property_named_input_schema_keeps_output_direction(self) -> None:
        """Direction comes from the schema root, not any `inputSchema` substring.

        A tool may legitimately expose an output property called
        `inputSchema`; the English engine still says "produced", so the
        translation must not switch to "accepted".
        """
        finding = Finding(
            "schema.type.accepted.narrowed",
            "tools.x.outputSchema.inputSchema.type",
            "wire",
            "breaking",
            "accepted types narrowed: ['number'] removed",
            before=["number", "string"],
            after=["string"],
        )
        text = render_text(DiffReport([finding]), "wire", lang="zh")
        self.assertIn("生成的类型收窄", text)
        self.assertNotIn("接受的类型收窄", text)

        enum = Finding(
            "schema.enum.narrowed",
            "tools.x.outputSchema.inputSchema.mode.enum",
            "wire",
            "breaking",
            "produced enum values were removed",
            before=["a", "b"],
            after=["a"],
        )
        enum_text = render_text(DiffReport([enum]), "wire", lang="zh")
        self.assertIn("生成的 enum 值被移除", enum_text)
        self.assertNotIn("接受的 enum 值被移除", enum_text)

    def test_input_property_named_output_schema_keeps_input_direction(self) -> None:
        finding = Finding(
            "schema.type.accepted.narrowed",
            "tools.x.inputSchema.outputSchema.type",
            "wire",
            "breaking",
            "accepted types narrowed: ['number'] removed",
            before=["number", "string"],
            after=["string"],
        )
        text = render_text(DiffReport([finding]), "wire", lang="zh")
        self.assertIn("接受的类型收窄", text)
        self.assertNotIn("生成的类型收窄", text)

    def test_names_with_apostrophes_survive_translation(self) -> None:
        """Greedy matching keeps `o'clock` and `a'b'c` intact.

        This bug was real and was fixed twice, so it stays pinned here.
        """
        for name in ("o'clock", "a'b'c", "quote'd", "it's"):
            with self.subTest(name=name):
                finding = Finding(
                    "tool.removed", f"tools.{name}", "wire", "breaking",
                    f"tool '{name}' was removed",
                )
                text = render_text(DiffReport([finding]), "wire", lang="zh")
                self.assertIn(f"工具 '{name}' 被删除", text)
                both = render_text(DiffReport([finding]), "wire", lang="both")
                self.assertIn(f"tool '{name}' was removed / 工具 '{name}' 被删除", both)

    def test_property_names_with_apostrophes_survive_translation(self) -> None:
        finding = Finding(
            "schema.property.removed", "tools.x.inputSchema.o'clock", "wire", "breaking",
            "property 'o'clock' was removed",
        )
        text = render_text(DiffReport([finding]), "wire", lang="zh")
        self.assertIn("属性 'o'clock' 被删除", text)

    def test_default_english_keeps_finding_message_exactly(self) -> None:
        finding = Finding(
            code="schema.type.accepted.narrowed",
            path="tools.x.inputSchema.type",
            axis="wire",
            impact="breaking",
            message="accepted types narrowed: ['integer'] removed",
            before=["integer", "string"],
            after=["string"],
        )
        self.assertIn("accepted types narrowed: ['integer'] removed", render_text(DiffReport([finding]), "wire"))


if __name__ == "__main__":
    unittest.main()
