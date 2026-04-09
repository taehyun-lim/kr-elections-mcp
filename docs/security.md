# Operational Security Notes
[Korean](security_kr.md)

This document describes practical security rules for running and extending South Korean Election MCP.

## Credential Handling

Preferred priority:

1. MCP client or process environment
2. OS keyring
3. `.env` development fallback

Rules:

- never ask users to paste API keys into MCP chat
- never add a public MCP tool that stores API keys
- never log raw `serviceKey` values
- never commit live API keys or screenshots containing them
- prefer `kr-elections-mcp setup-key` for public repo users

## Public Booklet Boundary

The public repository must not expose live NEC booklet discovery, URL derivation, or PDF download.

Required behavior:

- do not add public tools that derive NEC booklet download URLs
- do not add public tools that save booklet files locally
- keep `assemble_candidate_packet` free of indirect booklet downloads
- keep `krpoltext` text lookup limited to corpus and trusted-host fetch paths

## External Dataset Safety

- keep `krpoltext` dataset and legacy text fetches pinned to configured hosts
- reject manifest or legacy index URLs that point to unrelated hosts
- prefer explicit configuration over following third-party dataset redirects

## Logging and Diagnostics

- keep secret values out of tracebacks when possible
- preserve enough provenance to debug matching decisions
- distinguish `unauthorized`, `not_applied`, `empty`, and `error` in diagnostics output
- avoid leaking raw credentials through debug dumps or cached payloads

## Local File Writes

- keep structured warnings and partial-success results so failures are visible without unsafe retries

## Public Repository Hygiene

Before each release:

- verify no `.env` with live keys is tracked
- verify tests do not contain copied secrets
- verify examples do not instruct users to paste keys into chat
- verify README and docs still point users to keyring or environment-based setup

