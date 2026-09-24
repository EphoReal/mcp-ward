# Roadmap

**English** | [简体中文](roadmap.md)

## 0.1 — deterministic offline lens

- normalize raw `tools/list` JSON and prior snapshots
- stable snapshot output
- input/output tool schema diff
- description, title, annotation, and unknown-field changes
- four consumer profiles
- text, JSON, and self-contained HTML reports
- bilingual human-readable reports (`--lang en|zh|both`) with language-neutral JSON
- Git ref baseline via `git show`
- standard-library test suite and cross-platform CI

## 0.2 — evidence and ergonomics

- optional stdio transport behind an adapter
- policy configuration file for project-specific gates
- SARIF output
- real-world compatibility fixtures from open-source MCP servers
- baseline promotion command with an explicit reviewed workflow

## Later, only if usage justifies it

- trace recording and deterministic replay
- OpenAPI or function-calling adapters over the same finding model
- hosted baseline history

## Explicitly not planned for the first release

- cloud service, login, multi-tenancy
- React application or component framework
- LLM-generated explanations
- automatic baseline updates
- claims of formal JSON Schema validation
