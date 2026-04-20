# Source Status

[Korean](source-status_kr.md)

This document records the currently expected external-source behavior for `kr-elections-mcp` as of 2026-04-07.

## NEC API Access

Expected key behavior:

- the server accepts both decoded and encoded NEC service keys
- if only the decoded key is configured, the encoded form is derived automatically
- request order is decoded first, then encoded
- legacy `NEC_API_KEY` remains a fallback only

Operational note:

- `show-key-source` should report both the active source and the configured key formats

## NEC Core API Mapping

The repository currently expects NEC API calls to align with the official `data.go.kr` product pages for code info, candidate info, winner info, and tally information.

Observed during the source update:

- core NEC election listing and district lookup needed official endpoint alignment
- candidate profile and policy lookups required fallback handling across NEC variations
- downstream diagnostics depend on the election-code lookup succeeding first

## `krpoltext` Source Status

Current `krpoltext` assumptions:

- the maintained data root is `https://taehyun-lim.github.io/krpoltext/data`
- the maintained manifest is `/data/index.json`, with `/data/metadata.json` as the fallback shape
- campaign booklet text resolution should use the manifest's `campaign_booklet` resource
- booklet text lookup can now key on booklet `code` as well as candidate-name filters
- enriched linkage fields such as `huboid` should be preserved and used when available
- the public repository preserves corpus metadata such as `party_name` and `page_count` when present
- the public repository does not expose live NEC booklet discovery or downloads

This replaces the older assumption that the root `krpoltext` site itself always exposed a directly usable top-level `index.json` for booklet records.

## Tool-Level Notes

Expected public tool behavior:

- `get_krpoltext_text` can match on booklet `code`
- `assemble_candidate_packet` can include `krpoltext` text records
- no public tool derives live NEC booklet download URLs or saves booklet files

## Repository Test Coverage

The repository includes targeted tests for the source-adapter changes:

- `tests/test_campaign_booklet_sources.py`
- `tests/test_krpoltext_api.py`

These tests cover manifest resolution, trusted-host handling, campaign booklet corpus lookup, and user-facing `krpoltext` behavior.

