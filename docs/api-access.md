# API Access Guide

[Korean](api-access_kr.md)

South Korean Election MCP (kr-elections-mcp) uses a BYOK model. Each user must obtain and manage their own NEC API access.

## Official Entry Points

- [South Korean National Election Commission (NEC) Open Data API Info](http://data.nec.go.kr/open-data/api-info.do)
- [Public Data Portal (data.go.kr)](https://www.data.go.kr/)

## What Users Need To Do

1. Review the NEC open-data products you need.
2. Apply for the relevant NEC API products through `data.go.kr`.
3. Wait for approval when the requested product is not automatic.
4. Copy your encoded and decoded service keys after approval.
5. Store them locally with:

```bash
kr-elections-mcp setup-key
```

## Key Variants

The Public Data Portal notes that encoded and decoded keys may behave differently depending on API environment or invocation conditions.

This server supports both formats.

Behavior in this repository:

- `setup-key` accepts both encoded and decoded keys.
- You may store one or both.
- If only the decoded key is available, the server derives the encoded form automatically.
- Request order is always decoded first, then encoded.
- Legacy `NEC_API_KEY` still works as a fallback input.

## Recommended Local Setup

```bash
pip install .
kr-elections-mcp setup-key
kr-elections-mcp show-key-source
kr-elections-mcp run
```

If you intentionally use a local dotenv file for development, pass it explicitly:

```bash
kr-elections-mcp run --env-file .env
```

You can also use environment variables:

```env
NEC_API_KEY_DECODED=your_decoded_service_key
NEC_API_KEY_ENCODED=your_encoded_service_key
```

In many environments, `NEC_API_KEY_DECODED` alone is sufficient.

## Important Notes

- Having an account on `data.go.kr` is not enough by itself. Some NEC products still require separate approval.
- A key that works for one NEC service may still fail on another service if approval has not been granted.
- This repository does not host shared API keys.
- Public users should prefer OS keyring storage or MCP client environment variables instead of committing `.env` files.
- If your shell makes encoded keys awkward to paste, storing only the decoded key is usually the simplest option.
- Source checkout fallback remains available through `python server.py ...`.
- Local `.env` files are opt-in; use `--env-file .env` when you want them loaded.
