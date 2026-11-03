# Tool Matrix
[Korean](tool-matrix_kr.md)

## Must-Have Tools

| Tool | Purpose | Notes |
| --- | --- | --- |
| `list_elections` | List election metadata | Also available as a resource; built-in calendar fallback when the code API fails |
| `list_districts` | List districts for an election | Derived from tally rows when the code API fails |
| `list_parties` | List parties for an election | Also available as a resource |
| `search_candidates` | Search candidate rows | Ambiguity is preserved instead of auto-selecting |
| `get_candidate_profile` | Fetch normalized candidate profile data | Kept separate from policy lookup |
| `get_candidate_policies` | Fetch candidate policy or manifesto data | Availability reflects incomplete coverage |
| `get_district_results` | Return district-level candidate results | All candidates from the NEC 합계 row; `warnings` explain empty results |
| `get_district_summary` | Return district-level summary metrics | Same row as the results, so numbers always agree |
| `get_party_vote_share_history` | Show party vote-share history | One point per election, losing years included; `follow_lineage` is opt-in |
| `get_election_overview` | Return election-wide overview metrics | Supports high-level research workflows |
| `assemble_candidate_packet` | Build a composite candidate packet | Sections fail independently and are listed in `errors` |
| `diagnose_core_api_access` | Check core NEC API access | Helps users validate key and application setup |

## Additional Tools Included

| Tool | Purpose | Notes |
| --- | --- | --- |
| `diagnose_full_api_access` | Check extended API access status | Useful when optional NEC products differ by approval |
| `get_krpoltext_text` | Return matching `krpoltext` records | Can match by booklet `code` as well as candidate filters |
| `get_krpoltext_meta` | Return structured `krpoltext` metadata rows | Omits long text bodies but keeps merged bio metadata and raw row fields |
| `match_krpoltext_candidate` | Resolve a NEC candidate against `krpoltext` metadata | Keeps same-name collisions ambiguous unless stronger identifiers agree |

## Internal Helpers

These helpers are implementation details and are not intended as the public MCP surface.

- `resolve_candidate`
- `normalize_district`
- `map_party_name`
- `fetch_result_rows`
- `score_candidate_match`


