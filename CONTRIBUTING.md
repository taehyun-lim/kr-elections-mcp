# Contributing to South Korean Election MCP (kr-elections-mcp)

Thanks for contributing.

This project is a local Python FastMCP server for South Korean election research. It combines South Korean NEC election data, result adapters, and `krpoltext` text records into task-oriented MCP tools. We prefer small, reviewable pull requests with clear provenance, stable matching behavior, and explicit safety around credential and file-handling paths.

## Before You Open an Issue

- Use the GitHub issue templates when possible.
- For bugs, include the exact tool call, CLI command, or MCP client action that reproduces the problem.
- For data mismatches, include the election, district, candidate, and the source you compared against.
- Do not include API keys, full credential screenshots, or private local filesystem details that are not required.

## Security and Secrets

- Never paste `NEC_API_KEY` values into issues, PRs, logs, screenshots, or test fixtures.
- Prefer `kr-elections-mcp setup-key` so credentials are stored in the OS keyring.
- MCP tool inputs should not be used to collect API keys.
- `krpoltext` dataset and text fetches must remain pinned to trusted hosts.

See also: [SECURITY.md](SECURITY.md), [docs/security.md](docs/security.md), and [docs/api-access.md](docs/api-access.md).

## Local Setup

```bash
pip install -e .[dev]
kr-elections-mcp setup-key
kr-elections-mcp run
```

For development with a virtual environment:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Running Tests

Run the full test suite before opening a pull request:

```bash
pytest
```

The repository is designed so that tests pass with mocks and stubs even when a real NEC API key is not present.

## Design Rules for Contributions

- Keep MCP tools task-oriented. Do not expose raw NEC APIs one-for-one as public MCP tools.
- Preserve join discipline. Candidate and result matching should use election keys, district context, party, number, and `huboid` when available.
- Keep candidate profile, policies, results, and `krpoltext` logic separated by layer.
- Preserve `match_method`, `match_confidence`, and provenance metadata when combining sources.
- Treat unsupported coverage explicitly instead of silently returning partial guesses.
- `krpoltext` text lookup should remain corpus-backed and should not regress into live NEC booklet scraping.

## Documentation Expectations

Update docs when behavior changes in a user-visible way.

Common files to update:

- [README.md](README.md)
- [README_kr.md](README_kr.md)
- [docs/api-access.md](docs/api-access.md)
- [docs/api-access_kr.md](docs/api-access_kr.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/tool-matrix.md](docs/tool-matrix.md)
- [docs/examples.md](docs/examples.md)

## Pull Request Guidelines

- Keep PRs focused.
- Explain user-facing behavior and data-source impact clearly.
- Mention any matching ambiguity, confidence tradeoffs, or coverage limitations.
- Include tests for new behavior when practical.
- Avoid unrelated formatting churn.

## CODEOWNERS

A starter `CODEOWNERS` file is included, but the repository owner handle still needs to be filled in after publication. Update it before relying on CODEOWNERS-based review rules or branch protection.

