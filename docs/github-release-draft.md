# GitHub Release Draft

[Korean](github-release-draft_kr.md)

This document is a copy-paste-ready draft for the initial public release page.

## Recommended Release Title

`v0.1.0 - South Korean Election MCP initial public release`

## Alternative Release Title

`v0.1.0 - Local FastMCP server for South Korean election data`

## Release Body

```md
## South Korean Election MCP v0.1.0

Initial public release of a local Python FastMCP server for South Korean election research workflows.

### Highlights

- Task-oriented MCP tools instead of raw NEC endpoint mirroring
- Candidate packet assembly across profile, policy, `krpoltext`, and results
- District result and summary tools
- Public `krpoltext` booklet text and metadata lookup
- OS keyring-based NEC API key setup for safer public distribution
- Mock/stub-based pytest coverage for core flows

### Included MCP tools

- `list_elections`
- `list_districts`
- `list_parties`
- `search_candidates`
- `get_candidate_profile`
- `get_candidate_policies`
- `get_district_results`
- `get_district_summary`
- `get_party_vote_share_history`
- `get_election_overview`
- `assemble_candidate_packet`
- `diagnose_core_api_access`
- `diagnose_full_api_access`
- `get_krpoltext_text`

### Security and key handling

Recommended API key setup:

```bash
kr-elections-mcp setup-key
```

This stores the NEC API key in the local OS keyring instead of asking users to paste it into chat, tool inputs, or tracked repo files.

### Quick start

```bash
pip install .
kr-elections-mcp setup-key
kr-elections-mcp run
```

### Notes and limitations

- NEC API coverage varies by election type and time period
- policy availability is not uniform across all elections
- district names vary historically, so matching preserves normalization and confidence metadata
- `assemble_candidate_packet` includes `krpoltext` text and metadata when available
- public releases do not expose live NEC booklet discovery, URL derivation, or PDF download
- `krpoltext` support depends on the configured static data API and does not OCR NEC booklets on demand

### Validation status

- local pytest passing at release time
- FastMCP stdio server startup verified
```

## Short Announcement Copy

South Korean Election MCP (kr-elections-mcp) is now public: a local FastMCP server that turns South Korean election data into usable MCP tools for candidate packets, district summaries, `krpoltext` booklet text, and result lookups.
