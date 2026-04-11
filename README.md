# South Korean Election MCP (kr-elections-mcp)

[Korean README](README_kr.md)

[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.19490046-blue)](https://doi.org/10.5281/zenodo.19490046)
[![CI](https://github.com/taehyun-lim/kr-elections-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/taehyun-lim/kr-elections-mcp/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Auth: BYOK](https://img.shields.io/badge/auth-BYOK-4C9A2A)](https://www.data.go.kr/)

South Korean Election MCP (kr-elections-mcp) is a local Python FastMCP server for South Korean election research. It combines NEC open data, normalized result adapters, and [`krpoltext`](https://taehyun-lim.github.io/krpoltext/) text lookups into task-oriented MCP tools.

This repository is composite-first. It does not mirror every raw NEC endpoint as a public MCP tool. Instead, it focuses on higher-value workflows such as candidate packets, district summaries, election overviews, diagnostics, and safe text lookups.

## What It Provides

- Candidate search and profile retrieval
- Candidate policy retrieval when NEC coverage is available
- District-level election results and summaries
- Party vote-share history and election overviews
- [`krpoltext`](https://taehyun-lim.github.io/krpoltext/) text lookup for campaign booklet corpus rows
- Composite packet assembly across NEC, results, and [`krpoltext`](https://taehyun-lim.github.io/krpoltext/) text
- NEC API diagnostics for local BYOK usage

## Quick Start

### 1. Install the CLI

Requires Python 3.11+.

Recommended for most users:

```bash
pipx install .
```

`pipx` keeps the CLI isolated and makes it easier to point MCP clients at a stable `kr-elections-mcp` command.

If you prefer plain `pip`:

```bash
python -m pip install .
```

For development from a repository checkout:

```bash
python -m venv .venv
# activate the virtual environment for your shell
python -m pip install -r requirements.txt
python -m pip install -e .
```

This project is currently distributed as a Python package, not an npm package. If your MCP client is JavaScript- or Node-based, install the Python CLI first and then reference `kr-elections-mcp` from the client config below.

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

After installation, your MCP client should launch the Python-installed CLI, not an npm wrapper.

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

`NEC_API_KEY_ENCODED` is not required if the decoded key is already available.

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
- `get_krpoltext_meta`
- `match_krpoltext_candidate`

## [`krpoltext`](https://taehyun-lim.github.io/krpoltext/) Text Support

This repository does not OCR live NEC booklet PDFs on demand.

Current behavior:

- `get_krpoltext_text` can match on candidate name plus optional year, office, district, and party hints.
- It can also match directly on booklet `code`.
- `get_krpoltext_meta` returns structured campaign booklet metadata without the long booklet text body.
- The metadata tool preserves merged candidate bio fields such as `giho`, `birthday`, `age`, `job*`, `edu*`, and `career*` when the upstream dataset provides them.
- `match_krpoltext_candidate` resolves an NEC candidate first, then ranks [`krpoltext`](https://taehyun-lim.github.io/krpoltext/) rows using election scope plus stronger personal identifiers.
- Same-election same-district same-name collisions remain ambiguous unless a stronger personal identifier uniquely matches.
- The adapter now uses the current [`krpoltext`](https://taehyun-lim.github.io/krpoltext/) data manifest under `/data/index.json` and resolves the `campaign_booklet` resource.
- It understands both legacy `download_url` entries and newer `download_urls` maps from [`krpoltext`](https://taehyun-lim.github.io/krpoltext/) `0.2.0`, including OSF-managed artifact links.
- CSV artifacts remain the default path; Parquet artifacts can be used when `pyarrow` is available.
- Legacy text fetches stay on configured [`krpoltext`](https://taehyun-lim.github.io/krpoltext/) hosts, and dataset artifact fetches accept the trusted OSF-managed download hosts used by the current manifest.
- When text is available in the campaign booklet corpus, the tool returns the dataset-backed text record and corpus metadata such as `code`, `party_name`, and `page_count` when present.
- This public repository does not expose live NEC booklet discovery, URL derivation, or PDF download.

Example metadata lookup for Moon Jae-in in the 2017 presidential election:

```text
get_krpoltext_meta(
  candidate_name="문재인",
  election_year=2017,
  office_name="president",
  district_name="전국 대한민국",
  party_name="더불어민주당",
  limit=3
)
```

Example response shape:

```json
{
  "items": [
    {
      "record_id": "ECM0120170001_0001S",
      "code": "ECM0120170001_0001S",
      "candidate_name": "문재인",
      "office_name": "president",
      "election_year": 2017,
      "district_name": "전국 대한민국",
      "giho": "1",
      "party_name": "더불어민주당",
      "birthday": "1953-01-24",
      "age": 64,
      "edu": "경희대학교 법률학과 졸업",
      "career1": "(전)더불어민주당 당대표",
      "career2": "(전)제19대 국회의원",
      "page_count": 15,
      "has_text": true
    }
  ],
  "warnings": []
}
```

Example conservative NEC-to-`krpoltext` match:

```text
match_krpoltext_candidate(
  candidate_name="문재인",
  sg_id="20170509",
  sg_typecode="1",
  district_name="전국 대한민국",
  limit=5
)
```

Example response shape:

```json
{
  "status": "resolved",
  "message": "Resolved krpoltext metadata row from NEC election, office, district, and name context.",
  "item": {
    "code": "ECM0120170001_0001S",
    "candidate_name": "문재인",
    "district_name": "전국 대한민국",
    "giho": "1",
    "birthday": "1953-01-24",
    "age": 64,
    "match_method": "name+year+office+district+party+giho+birthday+age+sex+education+job+career",
    "match_confidence": 1.0
  },
  "warnings": [],
  "errors": []
}
```

The examples above use a real 2017 presidential-election row from the managed campaign booklet corpus.

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
- [krpoltext Matching Guide](docs/krpoltext-matching.md) ([Korean](docs/krpoltext-matching_kr.md))
- [Operational Security Notes](docs/security.md) ([Korean](docs/security_kr.md))

## How to Cite

If you use this software in research, cite the software record or export citation metadata from [CITATION.cff](CITATION.cff).

- DOI: [10.5281/zenodo.19490046](https://doi.org/10.5281/zenodo.19490046)
- Citation metadata: [CITATION.cff](CITATION.cff)

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


