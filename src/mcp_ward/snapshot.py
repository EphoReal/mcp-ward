"""Load and normalize MCP tool surface documents without losing unknown fields."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

SNAPSHOT_VERSION = 1
MAX_JSON_DEPTH = 200
KNOWN_TOOL_FIELDS = {"name", "title", "description", "inputSchema", "outputSchema", "annotations"}


class SnapshotError(ValueError):
    """Raised when a document is not a usable MCP tool surface."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SnapshotError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise SnapshotError(f"non-standard JSON number is not allowed: {value}")


def _json_loads_strict(text: str, source: str) -> Any:
    try:
        document = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except RecursionError as exc:
        raise SnapshotError(f"invalid JSON in {source}: nesting is too deep") from exc
    except json.JSONDecodeError as exc:
        raise SnapshotError(f"invalid JSON in {source}: {exc}") from exc
    _check_json_depth(document)
    return document


def _check_json_depth(value: Any, depth: int = 0) -> None:
    if depth > MAX_JSON_DEPTH:
        raise SnapshotError(f"JSON nesting exceeds the supported depth of {MAX_JSON_DEPTH}")
    if isinstance(value, dict):
        for child in value.values():
            _check_json_depth(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _check_json_depth(child, depth + 1)


def _validate_json_value(value: Any, path: str = "document") -> None:
    """Validate values before they enter the deterministic JSON projection."""
    pending = [(path, value)]
    while pending:
        current_path, current = pending.pop()
        if current is None or isinstance(current, (str, bool, int)):
            continue
        if isinstance(current, float):
            if not math.isfinite(current):
                raise SnapshotError(f"{current_path} contains a non-finite number")
            continue
        if isinstance(current, dict):
            for key, child in current.items():
                if not isinstance(key, str):
                    raise SnapshotError(f"{current_path} object keys must be strings")
                pending.append((f"{current_path}.{key}", child))
            continue
        if isinstance(current, list):
            pending.extend((f"{current_path}[{index}]", child) for index, child in enumerate(current))
            continue
        raise SnapshotError(f"{current_path} contains a non-JSON value")


VALID_SCHEMA_TYPES = {
    "null",
    "boolean",
    "object",
    "array",
    "number",
    "integer",
    "string",
}


def _validate_schema_shape(value: dict[str, Any], path: str, *, root: bool = False) -> None:
    if "type" in value:
        type_value = value["type"]
        valid_type = (
            isinstance(type_value, str) and type_value in VALID_SCHEMA_TYPES
        ) or (
            isinstance(type_value, list)
            and bool(type_value)
            and all(isinstance(item, str) and item in VALID_SCHEMA_TYPES for item in type_value)
        )
        if valid_type and isinstance(type_value, list) and len(type_value) != len(set(type_value)):
            raise SnapshotError(f"{path} type array must not contain duplicates")
        if not valid_type:
            raise SnapshotError(f"{path} type must be a standard JSON Schema type name or unique array of them")
    if "enum" in value:
        enum = value["enum"]
        if not isinstance(enum, list) or not enum:
            raise SnapshotError(f"{path} enum must be a non-empty array")
    if "required" in value:
        required = value["required"]
        if not isinstance(required, list) or any(not isinstance(name, str) for name in required):
            raise SnapshotError(f"{path} required must be an array of strings")
        if len(required) != len(set(required)):
            raise SnapshotError(f"{path} has duplicate required field names")
    if "properties" in value and not isinstance(value["properties"], dict):
        raise SnapshotError(f"{path} properties must be a JSON object")
    properties = value.get("properties", {})
    if isinstance(properties, dict):
        for name, child in properties.items():
            if not isinstance(child, dict):
                raise SnapshotError(f"{path}.{name} property schema must be a JSON object")
            _validate_schema_shape(child, f"{path}.{name}")
    if "items" in value:
        items = value["items"]
        if isinstance(items, list) and not items:
            raise SnapshotError(f"{path} items must not be an empty array")
        if isinstance(items, dict):
            _validate_schema_shape(items, f"{path}.items")
        elif isinstance(items, list):
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    raise SnapshotError(f"{path}.items[{index}] must be a JSON object")
                _validate_schema_shape(item, f"{path}.items[{index}]")
        else:
            raise SnapshotError(f"{path} items must be a schema object or array")
    for keyword in ("allOf", "anyOf", "oneOf"):
        if keyword in value:
            alternatives = value[keyword]
            if not isinstance(alternatives, list) or not alternatives or any(not isinstance(item, dict) for item in alternatives):
                raise SnapshotError(f"{path} {keyword} must be a non-empty array of schema objects")
            for index, item in enumerate(alternatives):
                _validate_schema_shape(item, f"{path}.{keyword}[{index}]")
    if "not" in value and not isinstance(value["not"], dict):
        raise SnapshotError(f"{path} not must be a schema object")
    if isinstance(value.get("not"), dict):
        _validate_schema_shape(value["not"], f"{path}.not")
    if "if" in value or "then" in value or "else" in value:
        for keyword in ("if", "then", "else"):
            if keyword in value and not isinstance(value[keyword], dict):
                raise SnapshotError(f"{path} {keyword} must be a schema object")
            if isinstance(value.get(keyword), dict):
                _validate_schema_shape(value[keyword], f"{path}.{keyword}")
    if "additionalProperties" in value and not isinstance(value["additionalProperties"], (bool, dict)):
        raise SnapshotError(f"{path} additionalProperties must be a boolean or schema object")
    if isinstance(value.get("additionalProperties"), dict):
        _validate_schema_shape(value["additionalProperties"], f"{path}.additionalProperties")
    for keyword in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minLength", "maxLength", "minItems", "maxItems"):
        if keyword in value and (not isinstance(value[keyword], (int, float)) or isinstance(value[keyword], bool)):
            raise SnapshotError(f"{path} {keyword} must be numeric")
    for keyword in ("uniqueItems",):
        if keyword in value and not isinstance(value[keyword], bool):
            raise SnapshotError(f"{path} {keyword} must be boolean")
    for keyword in ("description", "title", "pattern", "format"):
        if keyword in value and not isinstance(value[keyword], str):
            raise SnapshotError(f"{path} {keyword} must be a string")


def normalize_surface(document: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a deterministic, minimal projection of a tool list.

    ``document`` may be a raw ``{"tools": [...]}`` result, a snapshot produced
    by this package, or the already-normalized list returned by this function.
    Unknown tool fields are retained under ``extra`` rather than discarded, so
    later changes can still be detected.
    """
    _validate_json_value(document)
    if isinstance(document, list):
        tools = document
    elif isinstance(document, dict):
        if "kind" in document and document["kind"] != "mcp-tools":
            raise SnapshotError("snapshot kind must be 'mcp-tools'")
        if "snapshot_version" in document and document["snapshot_version"] != SNAPSHOT_VERSION:
            raise SnapshotError(f"unsupported snapshot_version: {document['snapshot_version']!r}")
        tools = document.get("tools")
    else:
        raise SnapshotError("tool surface must be a JSON object or array")
    if not isinstance(tools, list):
        raise SnapshotError("tool surface must contain a tools array")

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in tools:
        if not isinstance(raw, dict):
            raise SnapshotError("each tool must be a JSON object")
        name = raw.get("name")
        if not isinstance(name, str) or not name:
            raise SnapshotError("each tool must have a non-empty string name")
        if name in seen:
            raise SnapshotError(f"duplicate tool name: {name}")
        seen.add(name)

        item: dict[str, Any] = {"name": name}
        for field in ("title", "description", "inputSchema", "outputSchema", "annotations"):
            if field in raw:
                value = raw[field]
                if field in {"title", "description"} and not isinstance(value, str):
                    raise SnapshotError(f"tool {name!r} field {field!r} must be a string")
                if field in {"inputSchema", "outputSchema", "annotations"} and not isinstance(value, dict):
                    raise SnapshotError(f"tool {name!r} field {field!r} must be a JSON object")
                if field in {"inputSchema", "outputSchema"}:
                    _validate_schema_shape(value, f"tool {name!r} {field}", root=field == "inputSchema")
                item[field] = value
        if "inputSchema" not in item:
            raise SnapshotError(f"tool {name!r} must include inputSchema")
        if item["inputSchema"].get("type") != "object":
            raise SnapshotError(f"tool {name!r} inputSchema type must be 'object'")
        # `extra` is the normalized carrier for vendor/future fields. Preserve
        # it when round-tripping a normalized item instead of nesting it again.
        carried = raw.get("extra", {})
        if not isinstance(carried, dict):
            raise SnapshotError("tool extra field must be a JSON object")
        unknown = dict(carried or {})
        raw_unknown = {key: raw[key] for key in sorted(raw) if key not in KNOWN_TOOL_FIELDS and key != "extra"}
        collisions = sorted(set(unknown) & set(raw_unknown))
        if collisions:
            raise SnapshotError(f"tool {name!r} extra fields collide with raw fields: {', '.join(collisions)}")
        unknown.update(raw_unknown)
        item["extra"] = {key: unknown[key] for key in sorted(unknown)}
        normalized.append(item)
    return sorted(normalized, key=lambda item: item["name"])


def snapshot_bytes(document: dict[str, Any]) -> bytes:
    """Serialize a normalized surface as deterministic, reviewable JSON."""
    snapshot = {
        "snapshot_version": SNAPSHOT_VERSION,
        "kind": "mcp-tools",
        "tools": normalize_surface(document),
    }
    return (json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def load_document(path: str | Path) -> list[dict[str, Any]]:
    """Read a raw tools/list JSON file or a saved snapshot."""
    source = Path(path)
    try:
        document = _json_loads_strict(source.read_text(encoding="utf-8"), str(source))
    except OSError as exc:
        raise SnapshotError(f"cannot read {source}: {exc}") from exc
    return normalize_surface(document)
