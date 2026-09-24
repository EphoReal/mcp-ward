# v0.1 product contract

**English** | [简体中文](product-contract.md)

## Name

`mcp-ward`

## Job

Given two MCP tool surfaces, classify changes for both protocol callers and agent behaviour. The first release is an offline, deterministic lens; it never calls an LLM and never requires a cloud account.

## Audience

- MCP server maintainers
- maintainers of typed agent clients
- teams reviewing tool-surface pull requests

## Success criterion

A user can save two realistic `tools/list` documents, run one local command, understand in under a minute why a change is risky, and receive a deterministic non-zero exit code in CI.

## Design promises

1. **No silent loss:** unknown tool fields and unsupported schema keywords are preserved or surfaced.
2. **Two axes:** wire compatibility and agent behaviour are reported separately.
3. **One engine:** profiles are gates over one finding stream, not separate classifiers.
4. **Portable artifact:** stable JSON snapshots and a self-contained HTML report.
5. **Small surface:** one Python package, standard-library core, no web server.

## Non-goals for v0.1

- live MCP process or HTTP capture
- full JSON Schema implementation
- output conformance testing
- LLM behaviour evaluation
- automatic baseline promotion
- hosted history or collaboration
