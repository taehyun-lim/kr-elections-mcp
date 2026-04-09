# Security Policy

## Reporting a Vulnerability

If you discover a security issue, please avoid filing a public issue with exploit details, leaked credentials, or live sensitive endpoints.

Preferred process after the repository is published:

1. Use GitHub Security Advisories or private security reporting if enabled.
2. If private reporting is not available yet, contact the maintainer through a private channel and include only the minimum reproduction details needed.
3. Rotate any exposed API keys immediately.

## Scope

The most likely security-sensitive areas in South Korean Election MCP (kr-elections-mcp) are:

- NEC API key handling
- MCP client configuration examples
- Logging and exception redaction
- Local file writes for booklet downloads
- Cached raw payloads that may accidentally retain secrets

## Project Security Rules

- Never ask users to paste API keys into MCP chat or tool arguments.
- Prefer OS keyring storage via `kr-elections-mcp setup-key`.
- Treat `.env` only as a development fallback.
- Do not print `serviceKey` values in logs, tracebacks, or diagnostics output.
- Keep booklet downloads explicit and opt-in.
- Do not add automatic remote file downloads to packet assembly paths.
- Keep CI dependency and static security checks green before release (`pip-audit` and `bandit`).

See the longer operational guidance in [docs/security.md](docs/security.md) and the public-user setup notes in [docs/api-access.md](docs/api-access.md).

