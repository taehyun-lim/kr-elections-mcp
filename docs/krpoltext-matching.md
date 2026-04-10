# krpoltext Matching Guide

This guide describes the public MCP workflow for working across NEC candidate records and `krpoltext` campaign booklet metadata.

## Public Workflow

1. Resolve the NEC candidate with `search_candidates` or a candidate-facing tool.
2. Inspect structured booklet metadata with `get_krpoltext_meta`.
3. Use `match_krpoltext_candidate` for the conservative NEC-to-`krpoltext` join.
4. Fetch long-form booklet text with `get_krpoltext_text` after the row is resolved or when a known `code` is available.

## Match States

- `resolved`: one row remains after applying election, office, district, and stronger personal signals.
- `ambiguous`: multiple rows remain plausible, so the MCP does not auto-select one.
- `not_found`: no metadata row matched the resolved NEC candidate strongly enough.

## Match Signals

The shared matcher uses the resolved NEC candidate context first:

- election year derived from the NEC election date
- office name
- normalized district label
- candidate name
- party name when available

It then relies on stronger personal signals from the `krpoltext` metadata when available:

- `giho`
- `birthday`
- `age`
- `job*`
- `edu*`
- `career1`
- `career2`

The matcher is intentionally conservative. Same-election same-district same-name collisions stay ambiguous unless a stronger personal identifier uniquely matches.

## Upstream Improvements That Would Help

The current `krpoltext` metadata is already much better for matching than text-only rows, but the public integration would become easier and safer if the upstream dataset or API also exposed:

- the NEC candidate identifier used for the merge, such as `huboid` or `cnddtId`
- the exact NEC election identifiers, such as `sgId` and `sgTypecode`
- a canonical district identifier instead of only region and district strings
- a documented metadata-only endpoint or artifact that omits long text fields by default
- an explicit row-level lookup endpoint by booklet `code`
- a stable published schema endpoint for the metadata fields and their types

Those additions would reduce fuzzy joins, make client implementations simpler, and improve reproducibility across MCP clients.
