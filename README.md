# South Korean Election MCP (kr-elections-mcp)

[Korean README](README_kr.md)

[![CI](https://github.com/taehyun-lim/kr-elections-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/taehyun-lim/kr-elections-mcp/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Auth: BYOK](https://img.shields.io/badge/auth-BYOK-4C9A2A)](https://www.data.go.kr/)

South Korean Election MCP (kr-elections-mcp) is a local Python FastMCP server for South Korean election research. It combines NEC open data, normalized result adapters, and `krpoltext` text lookups into task-oriented MCP tools.

This repository is composite-first. It does not mirror every raw NEC endpoint as a public MCP tool. Instead, it focuses on higher-value workflows such as candidate packets, district summaries, election overviews, diagnostics, and safe text lookups.

## What It Provides

- Candidate search and profile retrieval
- Candidate policy retrieval when NEC coverage is available
- District-level election results and summaries
- Party vote-share history and election overviews
- `krpoltext` text lookup for campaign booklet corpus rows
- Composite packet assembly across NEC, results, and `krpoltext` text
- NEC API diagnostics for local BYOK usage

## Quick Start

### 1. Install the package

```bash
pip install .
```

### 2. Apply for NEC API access

This project uses a BYOK model. Each user must apply for the relevant NEC OpenAPI products through the [Public Data Portal (data.go.kr)](https://www.data.go.kr/).

The Public Data Portal notes that encoded and decoded service keys can behave differently depending on API environment or invocation conditions. This server accepts both forms.

See:

- [API Access Guide](docs/api-access.md)
- [Source Status](docs/source-status.md)

### 3. Store the key securely

Recommended:

```bash
kr-elections-mcp setup-key
```

`setup-key` accepts both encoded and decoded NEC service keys. You can store one or both.

Important behavior:

- If only `NEC_API_KEY_DECODED` is present, the server derives the encoded variant automatically.
- Request order is always decoded first, then encoded.
- Legacy `NEC_API_KEY` still works as a fallback.

Useful commands:

```bash
kr-elections-mcp show-key-source
kr-elections-mcp clear-key
```

### 4. Run the MCP server

```bash
kr-elections-mcp run
```

## MCP Client Example

```json
{
  "mcpServers": {
    "south-korean-election": {
      "command": "kr-elections-mcp",
      "args": ["run"]
    }
  }
}
```

If you do not want OS keyring storage, you can provide the key in the MCP client environment instead:

```json
{
  "mcpServers": {
    "south-korean-election": {
      "command": "kr-elections-mcp",
      "args": ["run"],
      "env": {
        "NEC_API_KEY_DECODED": "YOUR_DECODED_KEY"
      }
    }
  }
}
```

`NEC_API_KEY_ENCODED` is optional when the decoded key is already available.

## API Key Storage Rules

Key lookup priority is:

1. Process environment or MCP client `env`
2. OS keyring
3. `.env` development fallback

Within each source, the server prefers `NEC_API_KEY_DECODED` and `NEC_API_KEY_ENCODED`, then falls back to legacy `NEC_API_KEY`.

Recommended for public users:

- Use `kr-elections-mcp setup-key` when possible.
- Keep keys out of chat, screenshots, and Git commits.
- Treat `.env` as a development-only fallback.
- If you intentionally use `.env`, pass it explicitly with `--env-file .env`.
- In many environments, `NEC_API_KEY_DECODED` alone is enough.

## Source Checkout Fallback

If you are running directly from a repository checkout instead of an installed package, the legacy commands still work:

```bash
python server.py setup-key
python server.py show-key-source
python server.py run
```

If you intentionally want to load a local dotenv file, pass it explicitly:

```bash
kr-elections-mcp run --env-file .env
python server.py run --env-file .env
```

## Tools

Core tools:

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

Additional tools:

- `diagnose_full_api_access`
- `get_krpoltext_text`

## `krpoltext` Text Support

This repository does not OCR live NEC booklet PDFs on demand.

Current behavior:

- `get_krpoltext_text` can match on candidate name plus optional year, office, and district hints.
- It can also match directly on booklet `code`.
- The adapter now uses the current `krpoltext` data manifest under `/data/index.json` and resolves the `campaign_booklet` resource.
- It understands both legacy `download_url` entries and newer `download_urls` maps from `krpoltext` `0.2.0`, including OSF-managed artifact links.
- CSV artifacts remain the default path; Parquet artifacts can be used when `pyarrow` is available.
- Legacy text fetches stay on configured krpoltext hosts, and dataset artifact fetches accept the trusted OSF-managed download hosts used by the current manifest.
- When text is available in the campaign booklet corpus, the tool returns the dataset-backed text record and corpus metadata such as `code`, `party_name`, and `page_count` when present.
- This public repository does not expose live NEC booklet discovery, URL derivation, or PDF download.

## Resources

- `resource://nec/elections`
- `resource://nec/districts/{sg_id}/{sg_typecode}`
- `resource://nec/parties/{sg_id}/{sg_typecode}`

## Documentation

- [API Access Guide](docs/api-access.md) ([Korean](docs/api-access_kr.md))
- [Source Status](docs/source-status.md) ([Korean](docs/source-status_kr.md))
- [Architecture](docs/architecture.md) ([Korean](docs/architecture_kr.md))
- [Data Sources](docs/data-sources.md) ([Korean](docs/data-sources_kr.md))
- [Examples](docs/examples.md) ([Korean](docs/examples_kr.md))
- [Tool Matrix](docs/tool-matrix.md) ([Korean](docs/tool-matrix_kr.md))
- [Operational Security Notes](docs/security.md) ([Korean](docs/security_kr.md))

## Testing

Tests are designed to run with mocks and stubs even without a live NEC API key.

```bash
pytest
```

The source-adapter tests cover `krpoltext` manifest resolution, trusted-host handling, and campaign booklet corpus lookups.

## Limitations

- NEC policy coverage is incomplete and depends on service support by election and office.
- Live NEC API access still depends on each user's approved `data.go.kr` access.
- Result coverage can differ by source and historical election availability.
- `krpoltext` support depends on the current external dataset manifest and does not perform live OCR over NEC booklet files.

## License

This project is released under the [MIT License](LICENSE).

