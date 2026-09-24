# Architecture

**English** | [简体中文](architecture.md)

## Product boundary

`mcp-ward` is a deterministic compatibility lens for MCP tool contracts. Version 0.1 operates on a saved `tools/list` document or a normalized snapshot. It does not start an MCP server and does not call an LLM.

## Command surface

```text
mcp-ward snapshot INPUT [-o OUTPUT]
mcp-ward check BASELINE CANDIDATE [--profile observe|wire|agent|strict]
mcp-ward check --baseline-ref REF:PATH --candidate INPUT
mcp-ward check BASELINE CANDIDATE --format text,json,html
mcp-ward check BASELINE CANDIDATE --lang en|zh|both
mcp-ward check BASELINE CANDIDATE --report-dir DIR
mcp-ward check BASELINE CANDIDATE --html report.html
```

Exit codes:

- `0`: the selected profile accepts the change set
- `1`: one or more findings meet or exceed the selected gate
- `2`: invalid input, invalid snapshot, invalid CLI arguments, or Git baseline error

A requested format is written to a file when `--report-dir` (or the `--html`
alias) covers it, and echoed to stdout only when it has no file destination.
This keeps `--format json --report-dir reports/` safe to use in pipelines.

## Snapshot contract

A snapshot is deterministic, human-readable JSON. It contains no capture timestamp, machine path, or command string, so unchanged contracts produce byte-identical files.

```json
{
  "snapshot_version": 1,
  "kind": "mcp-tools",
  "tools": [
    {
      "name": "search",
      "title": "Search",
      "description": "Search indexed documents.",
      "inputSchema": {"type": "object"},
      "outputSchema": {"type": "object"},
      "annotations": {},
      "extra": {}
    }
  ]
}
```

Unknown top-level tool fields are retained under `extra` and compared. A change there is not silently ignored. Unsupported schema keywords are also retained and surfaced as `unknown`; the supported projection never treats an unrecognised construct as safe.

## Finding model

Each finding has:

- stable `code`
- JSON-style `path`
- `axis`: `wire`, `agent`, or `both`
- `impact`: `breaking`, `review`, `additive`, `cosmetic`, or `unknown`
- concise explanation and before/after values

`unknown` is the fail-closed bucket: it means the change is outside the v0.1 projection, not that the change is safe.

A tool description rewrite is normally `agent/review`: the JSON-RPC call can still work, but model selection or argument generation can change. A removed tool is `wire/breaking`.

## Profiles

| Profile | Blocks |
|---|---|
| `wire` | wire-breaking changes and `unknown` changes; appropriate for generated clients and protocol conformance |
| `agent` | wire-breaking, agent-review, and `unknown` changes; default for autonomous agent integrations |
| `strict` | every finding, including additive and cosmetic drift |
| `observe` | nothing; useful for migration reports |

Profiles are gates, not separate diff algorithms. One canonical finding list feeds every consumer. `unknown` always fails closed: only `observe` passes it.

Git baselines are read from a commit-ish only: the ref is verified with
`git rev-parse --verify <ref>^{commit}` before the blob is fetched. Index-only
forms such as `:path` and revision-zero forms such as `0:path` are rejected.

## JSON Schema policy

V1 implements a deliberately small schema projection: object properties, required fields, scalar/array type sets, enums, array items, numeric bounds, string bounds, nullability, `additionalProperties`, and schema-level `description`/`title`.

Presence is handled conservatively in both directions: adding a `type` constraint where the baseline declared none is `breaking`, and removing a declared `type` is an `unknown` finding because the accepted set can no longer be stated.

Unsupported schema keywords are not discarded and not interpreted. `$ref` and the combinator keywords (`allOf`, `anyOf`, `oneOf`, `not`, `if`/`then`/`else`) are preserved verbatim in snapshots and compared by value equality only; v0.1 never resolves references. Any addition, removal, or change to an unsupported keyword — including those — produces an `unknown/both` finding that gating profiles fail closed on. This is intentionally more conservative than silently pretending compatibility.

## Rendering

- Text is the default CI surface and contains no mandatory colour.
- The `--lang en|zh|both` option changes human-readable text and HTML only;
  JSON keeps stable machine keys and messages in every language mode. Locale
  spellings such as `zh-CN` are normalized by `i18n.normalize_lang`.
- Default `en` output is byte-compatible with the pre-i18n report. The English
  contract is pinned by `tests/golden/default_en/`, regenerated only on purpose
  with `python tools/gen_golden.py`. Language work must never change English
  bytes, JSON, exit codes, or gate decisions.
- Translations live in `i18n.py`, keyed by the engine's stable finding `code`
  rather than by English prose. Only mcp-ward's own wording is translated:
  tool names, parameter names, descriptions, paths, and user input pass through
  untouched, and a code with no translation falls back to the original message.
- JSON is stable, machine-readable, and includes `exit_code` for the selected profile.
- HTML is a single self-contained file with system fonts, no external assets, light/dark themes, keyboard-operable filter buttons, and `prefers-reduced-motion` support. Every finding value is escaped text; findings can carry the `unknown` impact like the other four labels.
- Localized text passes through the same terminal-control-character scrubber as
  the rest of the report, so a translation can never reintroduce escape
  sequences into stdout. In `both` mode the Chinese half of a label is wrapped in
  `lang="zh-CN"` so screen readers switch voice.
