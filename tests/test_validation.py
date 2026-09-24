import unittest

from mcp_ward.snapshot import SnapshotError, normalize_surface


def tool(name="bad", **extra):
    value = {"name": name, "inputSchema": {"type": "object"}}
    value.update(extra)
    return value


class DocumentValidationTests(unittest.TestCase):
    def test_empty_tools_is_a_valid_surface(self):
        self.assertEqual([], normalize_surface({"tools": []}))

    def test_unknown_schema_keywords_are_preserved_and_not_flattened(self):
        raw = {
            "tools": [
                {
                    "name": "ref_tool",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"item": {"$ref": "#/$defs/Item"}},
                        "$defs": {"Item": {"type": "object"}},
                    },
                }
            ]
        }
        surface = normalize_surface(raw)
        self.assertEqual(raw["tools"][0]["inputSchema"], surface[0]["inputSchema"])

    def test_invalid_non_object_schema_is_rejected(self):
        with self.assertRaisesRegex(SnapshotError, "inputSchema"):
            normalize_surface({"tools": [{"name": "bad", "inputSchema": []}]})

    def test_required_must_be_an_array_of_strings(self):
        with self.assertRaisesRegex(SnapshotError, "required"):
            normalize_surface(
                {
                    "tools": [
                        {
                            "name": "bad",
                            "inputSchema": {
                                "type": "object",
                                "properties": {},
                                "required": "missing",
                            },
                        }
                    ]
                }
            )

    def test_output_schema_can_be_present_without_input_schema(self):
        with self.assertRaisesRegex(SnapshotError, "inputSchema"):
            normalize_surface(
                {"tools": [{"name": "out", "outputSchema": {"type": "object"}}]}
            )

    def test_nested_required_must_be_an_array_of_strings(self):
        with self.assertRaisesRegex(SnapshotError, "required"):
            normalize_surface(
                {
                    "tools": [
                        {
                            "name": "bad",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"nested": {"type": "object", "required": "x"}},
                            },
                        }
                    ]
                }
            )

    def test_required_names_must_be_unique(self):
        with self.assertRaisesRegex(SnapshotError, "duplicate required"):
            normalize_surface(
                {
                    "tools": [
                        {
                            "name": "bad",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"id": {"type": "string"}},
                                "required": ["id", "id"],
                            },
                        }
                    ]
                }
            )

    def test_nested_property_schema_must_be_an_object(self):
        with self.assertRaisesRegex(SnapshotError, "property schema"):
            normalize_surface(
                {
                    "tools": [
                        {
                            "name": "bad",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"nested": True},
                            },
                        }
                    ]
                }
            )

    def test_array_tuple_items_are_preserved_and_validated(self):
        raw = {
            "tools": [
                {
                    "name": "tuple",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "value": {"type": "array", "items": [{"type": "string"}]}
                        },
                    },
                }
            ]
        }
        self.assertEqual(raw["tools"][0]["inputSchema"], normalize_surface(raw)[0]["inputSchema"])

    def test_unknown_snapshot_version_is_rejected(self):
        with self.assertRaisesRegex(SnapshotError, "snapshot_version"):
            normalize_surface({"snapshot_version": 99, "kind": "mcp-tools", "tools": []})

    def test_snapshot_kind_must_be_mcp_tools(self):
        with self.assertRaisesRegex(SnapshotError, "kind"):
            normalize_surface({"snapshot_version": 1, "kind": "other", "tools": []})

    def test_empty_extra_must_still_be_an_object(self):
        with self.assertRaisesRegex(SnapshotError, "extra"):
            normalize_surface({"tools": [tool(extra=[])]})

    def test_extra_and_raw_unknown_key_collision_is_rejected(self):
        with self.assertRaisesRegex(SnapshotError, "extra"):
            normalize_surface(
                {"tools": [tool(extra={"vendor": 1}, vendor=2)]}
            )

    def test_tool_text_fields_must_be_strings(self):
        with self.assertRaisesRegex(SnapshotError, "title"):
            normalize_surface({"tools": [{"name": "bad", "title": 3}]})
        with self.assertRaisesRegex(SnapshotError, "description"):
            normalize_surface({"tools": [{"name": "bad", "description": False}]})

    def test_malformed_type_is_rejected(self):
        malformed = [3, ["string", 3], [], {"name": "string"}, None, True]
        for bad in malformed:
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(SnapshotError, "type"):
                    normalize_surface(
                        {"tools": [{"name": "bad", "inputSchema": {"type": bad}}]}
                    )

    def test_malformed_nested_type_is_rejected(self):
        with self.assertRaisesRegex(SnapshotError, "type"):
            normalize_surface(
                {
                    "tools": [
                        {
                            "name": "bad",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"nested": {"type": ["string", 3]}},
                            },
                        }
                    ]
                }
            )

    def test_malformed_items_is_rejected(self):
        for bad in ("item", 7, True, None):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(SnapshotError, "items"):
                    normalize_surface(
                        {"tools": [tool(inputSchema={"type": "object", "properties": {"rows": {"type": "array", "items": bad}}})]}
                    )
        with self.assertRaisesRegex(SnapshotError, "items"):
            normalize_surface(
                {
                    "tools": [
                        {
                            "name": "bad",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"rows": {"type": "array", "items": "row"}},
                            },
                        }
                    ]
                }
            )

    def test_malformed_tuple_items_are_rejected(self):
        with self.assertRaisesRegex(SnapshotError, r"items\[1\]"):
            normalize_surface(
                {"tools": [tool(inputSchema={"type": "object", "properties": {"rows": {"type": "array", "items": [{"type": "string"}, "nope"]}}})]}
            )
        with self.assertRaisesRegex(SnapshotError, "empty array"):
            normalize_surface(
                {"tools": [tool(inputSchema={"type": "object", "properties": {"rows": {"type": "array", "items": []}}})]}
            )

    def test_malformed_combinator_schema_is_rejected(self):
        for keyword, bad in (("allOf", []), ("anyOf", {}), ("oneOf", ["nope"]), ("not", [])):
            with self.subTest(keyword=keyword, bad=bad):
                with self.assertRaisesRegex(SnapshotError, keyword):
                    normalize_surface({"tools": [tool(inputSchema={"type": "object", keyword: bad})]})

    def test_enum_must_be_a_non_empty_array(self):
        for bad in ("fast", 3, {}, None, []):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(SnapshotError, "enum"):
                    normalize_surface(
                        {"tools": [tool(inputSchema={"type": "object", "enum": bad})]}
                    )

    def test_ref_and_combinator_keywords_are_preserved_verbatim(self):
        schema = {
            "type": "object",
            "properties": {"item": {"$ref": "#/$defs/Item"}},
            "$defs": {"Item": {"type": "object"}},
            "allOf": [{"required": ["item"]}],
            "oneOf": [{"type": "string"}, {"type": "number"}],
            "anyOf": [{"type": "null"}],
            "not": {"type": "boolean"},
            "pattern": "^a",
            "format": "uri",
        }
        raw = {"tools": [{"name": "complex", "inputSchema": schema}]}
        self.assertEqual(schema, normalize_surface(raw)[0]["inputSchema"])


if __name__ == "__main__":
    unittest.main()
