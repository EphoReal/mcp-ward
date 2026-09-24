"""Deterministic compatibility findings for normalized MCP tool surfaces."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from .snapshot import SnapshotError

# We intentionally model the small, common JSON Schema projection first. Any
# changed keyword outside this set is an "unknown" finding, never silently
# lost: $ref, combinators (allOf/anyOf/oneOf/not/if-then-else), pattern,
# format, and vendor extensions are preserved verbatim and compared by value
# equality only. We never resolve or interpret them, so a change there is
# reported as unclassified rather than guessed at.
SUPPORTED_SCHEMA_KEYS = {
    "type",
    "properties",
    "required",
    "items",
    "enum",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "uniqueItems",
    "additionalProperties",
    "description",
    "title",
}
IGNORED_TOOL_META = {"title", "description"}


@dataclass(frozen=True)
class Finding:
    code: str
    path: str
    axis: str
    impact: str
    message: str
    before: Any = None
    after: Any = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DiffReport:
    findings: list[Finding]

    def counts(self) -> dict[str, int]:
        counts = {"breaking": 0, "review": 0, "additive": 0, "cosmetic": 0, "unknown": 0}
        for finding in self.findings:
            counts[finding.impact] = counts.get(finding.impact, 0) + 1
        return counts

    def max_severity(self) -> str | None:
        # Unknown is ranked highest because gating profiles fail closed on it.
        order = {"unknown": 5, "breaking": 4, "review": 3, "additive": 2, "cosmetic": 1}
        if not self.findings:
            return None
        return max(self.findings, key=lambda item: order.get(item.impact, 0)).impact


def _finding(code: str, path: str, axis: str, impact: str, message: str, before: Any = None, after: Any = None) -> Finding:
    return Finding(code, path, axis, impact, message, before, after)


def _type_set(schema: dict[str, Any]) -> set[str]:
    value = schema.get("type")
    if value is None:
        return set()
    if isinstance(value, list):
        return {str(item) for item in value}
    return {str(value)}


def _scalar_equal(left: Any, right: Any) -> bool:
    return left == right


def _enum_key(value: Any) -> str:
    """Create a stable, hashable key for any JSON enum member."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _schema_findings(before: Any, after: Any, path: str, direction: str, prefix: str) -> list[Finding]:
    """Compare a schema in either input or output direction.

    Input schemas describe what callers may send; output schemas describe
    what they may receive. The same structural edit therefore has different
    impact depending on direction.
    """
    findings: list[Finding] = []
    if not isinstance(before, dict) or not isinstance(after, dict):
        if before != after:
            code = f"schema.{direction}.shape.changed"
            return [_finding(code, path, "wire", "breaking", "schema shape changed", before, after)]
        return findings

    before_types = _type_set(before)
    after_types = _type_set(after)
    if before_types != after_types:
        type_path = f"{path}.type" if path else "type"
        if not before_types and after_types:
            # A constraint appeared where the baseline promised none: the
            # accepted set can only have shrunk, in either direction.
            findings.append(
                _finding(
                    "schema.type.accepted.narrowed",
                    type_path,
                    "wire",
                    "breaking",
                    f"type constraint added where none was declared; only {sorted(after_types)} is now accepted",
                    None,
                    sorted(after_types),
                )
            )
        elif before_types and not after_types:
            # The baseline's accepted/produced set can no longer be stated.
            # Fail closed as unclassified instead of guessing a direction.
            findings.append(
                _finding(
                    "schema.type.removed",
                    type_path,
                    "both",
                    "unknown",
                    "type constraint was removed; compatibility can no longer be determined",
                    sorted(before_types),
                    None,
                )
            )
        else:
            narrowed = before_types - after_types
            widened = after_types - before_types
            if narrowed:
                findings.append(_finding("schema.type.accepted.narrowed", type_path, "wire", "breaking", f"accepted types narrowed: {sorted(narrowed)} removed", sorted(before_types), sorted(after_types)))
            if widened:
                code = "schema.type.accepted.widened" if direction == "input" else "schema.type.produced.changed"
                impact = "additive" if direction == "input" else "breaking"
                findings.append(_finding(code, type_path, "wire", impact, f"accepted/produced types changed: {sorted(widened)} added", sorted(before_types), sorted(after_types)))

    if before.get("description") != after.get("description"):
        description_path = f"{path}.description" if path else "description"
        findings.append(
            _finding(
                "schema.description.changed",
                description_path,
                "agent",
                "review",
                "schema description changed; agent argument guidance may change",
                before.get("description"),
                after.get("description"),
            )
        )
    if before.get("title") != after.get("title"):
        title_path = f"{path}.title" if path else "title"
        findings.append(
            _finding(
                "schema.title.changed",
                title_path,
                "agent",
                "cosmetic",
                "schema title changed",
                before.get("title"),
                after.get("title"),
            )
        )

    if "enum" in before or "enum" in after:
        enum_path = f"{path}.enum" if path else "enum"
        old_values = before.get("enum", []) if isinstance(before.get("enum"), list) else []
        new_values = after.get("enum", []) if isinstance(after.get("enum"), list) else []
        old_enum = {_enum_key(value): value for value in old_values}
        new_enum = {_enum_key(value): value for value in new_values}
        if set(old_enum) != set(new_enum):
            before_values = [old_enum[key] for key in sorted(old_enum)]
            after_values = [new_enum[key] for key in sorted(new_enum)]
            removed = set(old_enum) - set(new_enum)
            added = set(new_enum) - set(old_enum)
            removed_only = removed and not added
            produced_addition = added and not removed and direction == "output"
            if removed_only:
                # Values the baseline accepted (input) or produced (output)
                # are gone. Both are caller-visible breakage.
                code = "schema.enum.narrowed"
                noun = "accepted" if direction == "input" else "produced"
                message = f"{noun} enum values were removed"
            elif produced_addition:
                code = "schema.enum.produced.changed"
                message = "new enum values are produced that the baseline did not declare"
            else:
                # Input additions are breaking too: validators and generated
                # clients built from the baseline reject values they never
                # saw, so the surface change does not stay compatible.
                code = "schema.enum.changed"
                noun = "accepted" if direction == "input" else "produced"
                message = f"{noun} enum values changed"
            findings.append(_finding(code, enum_path, "wire", "breaking", message, before_values, after_values))

    if direction == "input":
        old_required = set(before.get("required", [])) if isinstance(before.get("required"), list) else set()
        new_required = set(after.get("required", [])) if isinstance(after.get("required"), list) else set()
        if new_required - old_required:
            for name in sorted(new_required - old_required):
                field_path = f"{path}.{name}" if path else name
                findings.append(_finding("schema.required.added", field_path, "wire", "breaking", f"field '{name}' became required", None, after.get("properties", {}).get(name)))
        if old_required - new_required:
            for name in sorted(old_required - new_required):
                field_path = f"{path}.{name}" if path else name
                findings.append(_finding("schema.required.removed", field_path, "wire", "additive", f"field '{name}' became optional", True, False))
    else:
        old_required = set(before.get("required", [])) if isinstance(before.get("required"), list) else set()
        new_required = set(after.get("required", [])) if isinstance(after.get("required"), list) else set()
        if old_required - new_required:
            for name in sorted(old_required - new_required):
                field_path = f"{path}.{name}" if path else name
                findings.append(_finding("schema.output.required.removed", field_path, "wire", "breaking", f"guaranteed output field '{name}' is no longer guaranteed", True, False))
        if new_required - old_required:
            for name in sorted(new_required - old_required):
                field_path = f"{path}.{name}" if path else name
                findings.append(_finding("schema.output.required.added", field_path, "wire", "additive", f"output field '{name}' is now guaranteed", False, True))

    old_props = before.get("properties", {}) if isinstance(before.get("properties"), dict) else {}
    new_props = after.get("properties", {}) if isinstance(after.get("properties"), dict) else {}
    old_names = set(old_props)
    new_names = set(new_props)
    for name in sorted(old_names - new_names):
        findings.append(_finding("schema.property.removed", f"{path}.{name}" if path else name, "wire", "breaking", f"property '{name}' was removed", old_props[name], None))
    for name in sorted(new_names - old_names):
        is_required_input = direction == "input" and name in set(after.get("required", []))
        if is_required_input:
            # Optionality is already reported with the exact field path above.
            continue
        findings.append(_finding("schema.property.added", f"{path}.{name}" if path else name, "wire", "additive" if direction == "input" else "breaking", f"property '{name}' was added", None, new_props[name]))
    for name in sorted(old_names & new_names):
        child_path = f"{path}.{name}" if path else name
        findings.extend(_schema_findings(old_props[name], new_props[name], child_path, direction, prefix))

    if "items" in before or "items" in after:
        old_items = before.get("items")
        new_items = after.get("items")
        if isinstance(old_items, list) or isinstance(new_items, list):
            if old_items != new_items:
                findings.append(_finding("schema.items.tuple.changed", f"{path}.items" if path else "items", "wire", "breaking", "tuple-form items require a full JSON Schema comparison", old_items, new_items))
        else:
            findings.extend(_schema_findings(old_items, new_items, f"{path}.items" if path else "items", direction, prefix))

    for key in sorted(set(before) | set(after)):
        if key in SUPPORTED_SCHEMA_KEYS or key in IGNORED_TOOL_META:
            continue
        if (key in before) != (key in after) or not _scalar_equal(before.get(key), after.get(key)):
            findings.append(_finding("schema.unsupported.changed", f"{path}.{key}" if path else key, "both", "unknown", f"unsupported schema keyword '{key}' changed; the v0.1 engine cannot classify it", before.get(key) if key in before else None, after.get(key) if key in after else None))

    for key in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minLength", "maxLength", "minItems", "maxItems", "uniqueItems", "additionalProperties"):
        if key in before or key in after:
            if before.get(key) != after.get(key):
                findings.append(_finding("schema.bound.changed", f"{path}.{key}" if path else key, "wire", "breaking", f"constraint '{key}' changed", before.get(key), after.get(key)))

    return findings


def _tool_findings(before: dict[str, Any], after: dict[str, Any]) -> list[Finding]:
    name = before.get("name", after.get("name", "<unknown>"))
    prefix = f"tools.{name}"
    findings: list[Finding] = []
    for field in ("title",):
        if before.get(field) != after.get(field):
            findings.append(_finding("agent.title.changed", f"{prefix}.{field}", "agent", "cosmetic", f"{field} changed", before.get(field), after.get(field)))
    if before.get("description") != after.get("description"):
        findings.append(_finding("agent.description.changed", f"{prefix}.description", "agent", "review", "tool description changed; agent routing or argument generation may change", before.get("description"), after.get("description")))
    if before.get("annotations") != after.get("annotations"):
        findings.append(_finding("agent.annotations.changed", f"{prefix}.annotations", "agent", "review", "tool annotations changed; trust and side-effect hints may change", before.get("annotations"), after.get("annotations")))
    if before.get("extra") != after.get("extra"):
        findings.append(_finding("wire.unknown.changed", f"{prefix}.extra", "both", "unknown", "unknown tool fields changed; the v0.1 engine cannot classify them", before.get("extra", {}), after.get("extra", {})))
    for field, direction in (("inputSchema", "input"), ("outputSchema", "output")):
        before_present = field in before
        after_present = field in after
        field_path = f"{prefix}.{field}"
        if before_present != after_present:
            findings.append(
                _finding(
                    "schema.presence.changed",
                    field_path,
                    "wire",
                    "breaking",
                    f"{field} {'appeared' if after_present else 'was removed'}",
                    before.get(field) if before_present else None,
                    after.get(field) if after_present else None,
                )
            )
        elif before_present and before.get(field) != after.get(field):
            findings.extend(_schema_findings(before[field], after[field], field_path, direction, prefix))
    return findings


def _unique_tool_map(tools: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for tool in tools:
        if not isinstance(tool, dict):
            raise SnapshotError("each tool must be a JSON object")
        name = tool.get("name")
        if not isinstance(name, str) or not name:
            raise SnapshotError("each tool must have a non-empty string name")
        if name in result:
            raise SnapshotError(f"duplicate tool name: {name}")
        result[name] = tool
    return result


def diff_surfaces(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> list[Finding]:
    """Return a deterministic list of changes from baseline to candidate."""
    before_map = _unique_tool_map(before)
    after_map = _unique_tool_map(after)
    findings: list[Finding] = []
    for name in sorted(set(before_map) - set(after_map)):
        findings.append(_finding("tool.removed", f"tools.{name}", "wire", "breaking", f"tool '{name}' was removed", before_map[name], None))
    for name in sorted(set(after_map) - set(before_map)):
        findings.append(_finding("tool.added", f"tools.{name}", "wire", "additive", f"tool '{name}' was added", None, after_map[name]))
    for name in sorted(set(before_map) & set(after_map)):
        findings.extend(_tool_findings(before_map[name], after_map[name]))
    return sorted(findings, key=lambda item: (item.path, item.code, item.message))
