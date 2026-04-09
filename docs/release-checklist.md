# Release Checklist

[Korean](release-checklist_kr.md)

## Pre-Release Verification

- run `pytest`
- run `kr-elections-mcp --help`
- run `kr-elections-mcp show-key-source`
- confirm the stdio server still starts
- confirm README Quick Start matches the current CLI

## Security Review

- verify no live NEC API keys are committed
- verify no local-only secret paths are documented
- verify examples do not ask users to paste keys into chat
- verify public releases do not reintroduce live NEC booklet discovery, URL derivation, or PDF download
- verify `krpoltext` dataset and text fetches remain pinned to configured hosts

## Documentation Review

- confirm `README.md` and `README_kr.md` still match each other
- confirm English and Korean docs still point to each other correctly
- confirm tool names in docs match the actual MCP surface
- confirm release notes still describe the shipped behavior

## GitHub Repo Review

- set the repository About description and topics
- upload a social preview image if available
- enable branch protection or review rules if needed
- update `.github/CODEOWNERS` with the real owner handle

## Packaging / Release Page

- create the Git tag and release title
- paste the prepared release notes draft
- link the most important docs in the release body
- mention BYOK and OS keyring-based key setup explicitly
