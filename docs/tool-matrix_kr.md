# Tool Matrix
[English](tool-matrix.md)

## 핵심 Tools

| Tool | 목적 | 메모 |
| --- | --- | --- |
| `list_elections` | 선거 메타데이터 목록 조회 | resource로도 제공 |
| `list_districts` | 특정 선거의 선거구 목록 조회 | 정규화된 district 처리 사용 |
| `list_parties` | 특정 선거의 정당 목록 조회 | resource로도 제공 |
| `search_candidates` | 후보자 검색 | ambiguity를 보존하고 자동 확정하지 않음 |
| `get_candidate_profile` | 정규화된 후보자 프로필 조회 | 정책 조회와 분리 |
| `get_candidate_policies` | 후보자 정책 또는 공약 조회 | coverage 부족을 availability로 표현 |
| `get_district_results` | 선거구 단위 후보 결과 반환 | source와 match metadata 포함 |
| `get_district_summary` | 선거구 단위 요약 지표 반환 | turnout 계열 요약 필드 포함 |
| `get_party_vote_share_history` | 정당 득표율 이력 조회 | 선거 간 district harmonization 필요 |
| `get_election_overview` | 선거 전체 개요 지표 반환 | 상위 연구 워크플로 지원 |
| `assemble_candidate_packet` | 복합 candidate packet 구성 | 매칭되면 `krpoltext` 텍스트를 포함 |
| `diagnose_core_api_access` | 핵심 NEC API 접근 확인 | key와 신청 상태 점검에 유용 |

## 추가 Tools

| Tool | 목적 | 메모 |
| --- | --- | --- |
| `diagnose_full_api_access` | 확장 API 접근 상태 확인 | optional NEC 상품별 승인 차이 확인용 |
| `get_krpoltext_text` | 매칭되는 `krpoltext` 레코드 반환 | 후보자 필터 외에 booklet `code`로도 매칭 가능 |
| `get_krpoltext_meta` | 구조화된 `krpoltext` metadata row 반환 | 긴 본문 없이 병합된 bio metadata와 raw row field를 보존 |
| `match_krpoltext_candidate` | NEC 후보자를 `krpoltext` metadata에 매칭 | 더 강한 식별자가 맞지 않으면 동명이인 충돌을 ambiguous로 유지 |

## 내부 Helper

아래 helper는 구현 상세이며 public MCP surface가 아닙니다.

- `resolve_candidate`
- `normalize_district`
- `map_party_name`
- `fetch_result_rows`
- `score_candidate_match`


