# Architecture
[Korean](architecture_kr.md)

## Overview

South Korean Election MCP is a local Python FastMCP server for South Korean election research workflows. The v1 architecture is composite-first: it wraps multiple sources behind task-oriented MCP tools instead of mirroring every raw API endpoint one-to-one.

The main user-facing goals are:

- candidate discovery and profile lookup
- policy lookup when NEC coverage exists
- district-level result lookup and summaries
- `krpoltext` text lookup
- composite packet assembly across sources

## Layered Design

1. `server.py`
   Creates the FastMCP server, wires dependencies, and provides the local CLI for key management and stdio execution.
2. `app/tool_handlers.py`
   Defines the public MCP tool surface and orchestrates multi-source assembly logic.
3. `app/nec_api.py`
   Wraps NEC OpenAPI access with JSON-first requests, XML fallback, normalization, retries, and shared error handling.
4. `app/results_api.py`
   Normalizes district and election result views into a consistent model with match metadata.
5. `app/krpoltext_api.py`
   Resolves and returns `krpoltext` records through the maintained dataset manifest and campaign booklet resource.
6. `app/campaign_booklet_corpus.py`
   Handles campaign booklet corpus manifest resolution, row loading, and code-aware matching.
7. `app/normalize.py`
   Implements district, party, and candidate-name normalization plus candidate/result matching helpers.
8. `app/models.py`
   Defines structured input/output models, provenance metadata, availability metadata, and packet models.
9. `app/config.py` and `app/secret_store.py`
   Load settings, resolve NEC API keys, and prefer OS keyring storage for public distribution.

## Public Surface Design

The public MCP surface is task-oriented.

Examples:

- `list_elections`
- `search_candidates`
- `get_candidate_profile`
- `get_district_summary`
- `assemble_candidate_packet`
- `diagnose_core_api_access`

The repository intentionally avoids exposing every NEC endpoint directly as a public MCP tool.

## Join and Matching Rules

The project avoids optimistic single-field joins.

Canonical keys:

- `election_key = (sgId, sgTypecode)`
- `candidate_key = (sgId, sgTypecode, huboid)`
- `district_key_raw = (sgId, sgTypecode, sdName, sggName?, wiwName?)`

Matching behavior:

- API rows are never filtered by string similarity. Provinces are compared with an era-independent key
  (`app/geo.py`: 전라북도 = 전북특별자치도, 서울 = 서울특별시), districts by exact normalized name.
- User-typed district names are resolved onto the names NEC actually returned (`app/district_resolver.py`):
  exact, then suffix (`종로` → `종로구`, `사하갑` → `사하구갑`), then 갑/을 splits (returned as ambiguous),
  then component areas (`영도구` → `중구영도구`), then a unique prefix. Anything else is reported as not found
  with suggestions. This is the only fuzzy step in the results path.
- Tally rows are *wide*: one row per area with up to 50 candidate slots (`hbjNN`/`jdNN`/`dugsuNN`).
  `app/tally.py` expands the slots and groups rows by (province, district). Every district figure comes from
  the single `wiwName == 합계` row; sub-area rows are used only when `wiw_name` is requested.
- Winner rows are joined onto slots by name (party breaks ties) inside the same district. Only winner rows carry
  `huboid` and the official ballot number (`giho`); the slot number is exposed as `ballot_position`.
- Vote shares follow NEC: truncated, not rounded, to two decimals.
- Metadata lookups (election code list, district and party code lists) never fail a result query. When
  CommonCodeService is unavailable the tools fall back to a built-in election calendar or to lists derived from
  result rows, and say so in `warnings`.
- Prefer `huboid` when available; otherwise match by exact name and use party only to separate namesakes.
- Return ambiguity or `None` with a warning instead of silently choosing a row when resolution is uncertain.

## Public `krpoltext` Rules

The public repository keeps `krpoltext` text lookup and campaign booklet corpus metadata, but it does not expose live NEC booklet discovery or downloads.

- `get_krpoltext_text` returns corpus-backed text records and code-aware matches.
- `assemble_candidate_packet` may include `krpoltext` text, but it does not include live booklet assets.
- `campaign_booklet_corpus` remains responsible for manifest resolution, trusted-host checks, and row loading.
- page-oriented corpus metadata such as `page_count` should be preserved when the dataset provides it.
- live NEC booklet URL derivation and file download are intentionally outside the public surface.

## Resources and Discoverability

v1 exposes both tools and resources.

Resources:

- `resource://nec/elections`
- `resource://nec/districts/{sg_id}/{sg_typecode}`
- `resource://nec/parties/{sg_id}/{sg_typecode}`

Equivalent tool access remains available for LLM and client discoverability.

## Operational Notes

- NEC key loading priority: environment > OS keyring > `.env` fallback
- decoded-only NEC key configuration is supported, with automatic encoded derivation
- tests are mock/stub-friendly and do not require a live NEC key
- the public distribution model is local single-user BYOK
- multi-user hosted key storage is intentionally out of scope for v1


