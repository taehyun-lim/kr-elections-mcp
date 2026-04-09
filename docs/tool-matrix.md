# Tool Matrix
[Korean](tool-matrix_kr.md)

## Must-Have Tools

| Tool | Purpose | Notes |
| --- | --- | --- |
| `list_elections` | List election metadata | Also available as a resource |
| `list_districts` | List districts for an election | Uses normalized district handling |
| `list_parties` | List parties for an election | Also available as a resource |
| `search_candidates` | Search candidate rows | Ambiguity is preserved instead of auto-selecting |
| `get_candidate_profile` | Fetch normalized candidate profile data | Kept separate from policy lookup |
| `get_candidate_policies` | Fetch candidate policy or manifesto data | Availability reflects incomplete coverage |
| `get_district_results` | Return district-level candidate results | Includes source and match metadata |
| `get_district_summary` | Return district-level summary metrics | Includes turnout-style summary fields |
| `get_party_vote_share_history` | Show party vote-share history | Requires district harmonization across elections |
| `get_election_overview` | Return election-wide overview metrics | Supports high-level research workflows |
| `assemble_candidate_packet` | Build a composite candidate packet | Includes matched `krpoltext` text when available |
| `diagnose_core_api_access` | Check core NEC API access | Helps users validate key and application setup |

## Additional Tools Included

| Tool | Purpose | Notes |
| --- | --- | --- |
| `diagnose_full_api_access` | Check extended API access status | Useful when optional NEC products differ by approval |
| `get_krpoltext_text` | Return matching `krpoltext` records | Can match by booklet `code` as well as candidate filters |

## Internal Helpers

These helpers are implementation details and are not intended as the public MCP surface.

- `resolve_candidate`
- `normalize_district`
- `map_party_name`
- `fetch_result_rows`
- `score_candidate_match`

