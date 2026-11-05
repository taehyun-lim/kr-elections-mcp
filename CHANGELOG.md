# Changelog

## Unreleased

### Fixed — election results

- `get_district_results` returned rows from other districts. API rows were kept when their joined label was
  at least 65% similar to the request, which lets most districts of the same province through
  (e.g. 서울 종로구 showed 구로구갑's winner first). Rows are now matched by exact province and district.
- Tally rows were not expanded. Each NEC tally row holds up to 50 candidates (`hbjNN`/`jdNN`/`dugsuNN`); they
  were read as one candidate, so losing candidates had no name or votes. All candidates are now returned.
- Winner rows, district total (`합계`) rows and sub-area rows were mixed into one ranking and double counted.
  District figures now come from the single `합계` row.
- `giho` was filled from the row counter `num`. It is now the official ballot number from winner rows only;
  the tally slot number is exposed separately as `ballot_position`.
- `match_confidence` was 1.0 for every row because each label was compared with itself. It now reflects how
  the district name was resolved.
- `get_district_summary` took metrics from the first loosely matching row (usually another district) and summed
  contaminated votes. All metrics now come from the same `합계` row as the results.
- `get_party_vote_share_history` only saw the winning party. It now returns one point per election for the
  requested party, won or lost.
- `get_election_overview` fell back to `rows[0]` (one district) as the national total and contained a
  mis-encoded `'??'` literal. It now uses the national row or sums district total rows, with a warning.
- `get_candidate_policies` returned one empty pledge. NEC's wide pledge rows (`prmsTitleN`/`prmmContN`) are now
  expanded, including the pledge field (`realm`).
- `search_candidates` returned the same candidacy twice.
- Vote shares follow NEC's truncation rule (59.8659 → 59.86).
- Presidential results for one province showed the winner's nationwide share (e.g. 49.42 instead of 47.13 for
  서울, 2025), so shares added up to more than 100. The published share is now used only when the winner row
  counts the same votes as the tally row.
- `match_krpoltext_candidate` and `assemble_candidate_packet` filtered booklets by the election name
  (`sg_name`). Local elections share one name that names no office (`제8회 전국동시지방선거`), so candidates of
  types 3-6 and 11 never matched a booklet. The office is now taken from `sg_typecode`.
- Presidential tally rows all have `sggName` '대한민국', so the 17 province rows were taken for nationwide rows
  along with the real one (`sdName` '합계'). `get_election_overview` showed no electorate or turnout and no
  districts; `get_district_results(sd_name='전국')` returned nothing; districts derived from tally rows were empty.
  The province now decides, so the nationwide row is used and the provinces are listed as districts.

### Fixed — reliability

- An unauthorized CommonCodeService (HTTP 401) made `get_district_summary`, `get_election_overview`,
  `get_party_vote_share_history`, `list_elections`, `list_districts` and `list_parties` fail even though the
  result APIs worked. Metadata is now optional: a built-in election calendar and lists derived from result
  rows are used instead, with a warning.
- HTTP 401/403 was treated as a network error: the encoded key was never tried and the client slept before
  retrying. Rejected keys now move to the next key variant immediately; identical key variants are sent once.
- HTTP 429/5xx and NEC codes 01/02/04/05/99 are retried with exponential backoff, jitter and `Retry-After`.
  Other 4xx responses and quota errors (code 22, new `ApiQuotaError`) are not retried.
- data.go.kr gateway error envelopes (`OpenAPI_ServiceResponse`) are recognized as errors instead of being
  cached as empty results. Cache keys were versioned so earlier empty entries are ignored.
- `assemble_candidate_packet` sections (profile, policies, result, krpoltext) fail independently.
- Error messages no longer include request URLs; urllib3 debug logging (which prints the `serviceKey`) is capped
  at INFO.
- Diagnostics probe the result APIs with a fixed sample when the election code list fails, and report
  `quota` / `skipped` states. `setup-key` validation reports each API separately.
- Optional `sg_id` / `sg_typecode` / `giho` / `huboid` parameters rejected numbers (`Input should be a valid
  string`) from MCP clients that drop `anyOf` from the schema and send `"2"` as `2`. Numbers are now converted
  to strings.
- `diagnose_core_api_access` / `diagnose_full_api_access` returned every sample row (about 244k characters,
  over client output limits). Each check now returns at most 2 sample rows plus `item_count`.
- krpoltext lookups that infer the election id from a year (`match_krpoltext_candidate`, and the retry in
  `get_krpoltext_meta` / `get_krpoltext_text`) failed with HTTP 401 when the election code API was
  unauthorized. They now use the built-in calendar fallback.
- Booklet text (`get_krpoltext_text`, the `krpoltext` section of `assemble_candidate_packet`) was always empty:
  OSF now redirects downloads to Oracle Cloud object storage (`<namespace>.compat.objectstorage.<region>.oraclecloud.com`),
  which was not a trusted host, so the text file was never downloaded. With an empty cache, metadata lookups
  failed the same way. That host pattern is now trusted; downloads are still checked against the manifest's
  SHA-256 and size.

### Changed

- `get_district_results` / `get_district_summary`: for election types with several districts per province
  (2, 4, 5, 6, 10), omitting `sgg_name` now returns no rows and a warning listing the districts, instead of a
  mixture of districts.
- Default cache directory moved from `.cache/http` (relative to the client's working directory) to
  `~/.cache/kr-elections-mcp/http`. `CACHE_TTL_SECONDS=0` now disables caching (it previously cached forever).
- Cache lifetime depends on the election date: settled results are kept 30 days, recent or empty answers
  briefly. An in-memory layer sits in front of the file cache; cache files are written atomically.
- Tool descriptions and parameter descriptions were added for MCP clients.

### Added

- `CandidateResult.ballot_position`, `giho_detail`, `valid_vote_count`, `warnings`; coverage scope `sub_area`.
- `get_party_vote_share_history(follow_lineage=True)` to follow renamed parties (opt-in).
- Real-shape NEC fixtures and golden tests (`tests/fixtures/nec`, `tests/test_golden_results.py`);
  opt-in live checks (`python -m pytest -m live`).
