# Architecture
[English](architecture.md)

## 개요

South Korean Election MCP는 한국 선거 연구 워크플로를 위한 로컬 Python FastMCP 서버입니다. v1 아키텍처는 composite-first 방식으로, raw API를 일대일로 그대로 노출하기보다 여러 소스를 작업 중심 MCP 도구 뒤에 감춥니다.

주요 목표:

- 후보자 탐색과 프로필 조회
- NEC 범위 내 정책 조회
- 선거구 단위 결과와 요약 조회
- `krpoltext` 텍스트 조회
- 여러 소스를 묶는 후보자 packet 조립

## 계층 구조

1. `server.py`
   FastMCP 서버를 만들고 의존성을 연결하며, 키 관리와 stdio 실행용 로컬 CLI를 제공합니다.
2. `app/tool_handlers.py`
   public MCP tool surface를 정의하고 여러 소스를 조합하는 로직을 담당합니다.
3. `app/nec_api.py`
   JSON 우선 요청, XML fallback, 정규화, 재시도, 공통 오류 처리와 함께 NEC OpenAPI를 감쌉니다.
4. `app/results_api.py`
   선거구 및 선거 결과 뷰를 일관된 모델과 match metadata로 정규화합니다.
5. `app/krpoltext_api.py`
   유지 중인 dataset manifest와 campaign booklet resource를 통해 `krpoltext` 레코드를 반환합니다.
6. `app/campaign_booklet_corpus.py`
   campaign booklet 코퍼스 manifest 해석, row 로딩, code-aware matching을 담당합니다.
7. `app/normalize.py`
   선거구, 정당, 후보자 이름 정규화와 후보자/결과 매칭 helper를 제공합니다.
8. `app/models.py`
   구조화된 입력/출력 모델, provenance, availability, packet 모델을 정의합니다.
9. `app/config.py`, `app/secret_store.py`
   설정을 읽고 NEC 키를 해석하며, 공개 배포 기준 OS keyring을 우선합니다.

## Public Surface 설계

public MCP surface는 task-oriented입니다.

예시:

- `list_elections`
- `search_candidates`
- `get_candidate_profile`
- `get_district_summary`
- `assemble_candidate_packet`
- `diagnose_core_api_access`

이 저장소는 모든 NEC endpoint를 public MCP tool로 직접 노출하지 않습니다.

## 조인과 매칭 규칙

단일 필드만으로 낙관적으로 조인하지 않습니다.

canonical key:

- `election_key = (sgId, sgTypecode)`
- `candidate_key = (sgId, sgTypecode, huboid)`
- `district_key_raw = (sgId, sgTypecode, sdName, sggName?, wiwName?)`

매칭 동작:

- API 행을 문자열 유사도로 거르지 않습니다. 시도는 시대와 무관한 키로 비교하고(`app/geo.py`: 전라북도 = 전북특별자치도,
  서울 = 서울특별시), 선거구는 정규화한 이름이 정확히 같을 때만 같은 선거구로 봅니다.
- 사용자가 입력한 선거구명은 NEC가 실제로 돌려준 이름 중 하나로 해석합니다(`app/district_resolver.py`).
  순서는 exact, 접미사(`종로` → `종로구`, `사하갑` → `사하구갑`), 갑/을 분할(모호함으로 반환), 구성 구시군
  (`영도구` → `중구영도구`), 유일한 prefix입니다. 그 밖에는 제안 목록과 함께 찾지 못했다고 알립니다. 결과 경로에서
  fuzzy 매칭은 이 단계뿐입니다.
- 개표 행은 가로형입니다. 한 행에 후보 칸이 최대 50개(`hbjNN`/`jdNN`/`dugsuNN`) 있습니다. `app/tally.py`가 칸을
  펼치고 (시도, 선거구)로 묶습니다. 선거구 수치는 모두 `wiwName == 합계` 행 하나에서 가져오고, 구시군 하위 행은
  `wiw_name`을 지정했을 때만 씁니다.
- 당선 행은 같은 선거구 안에서 이름으로 후보 칸에 조인합니다(동명이인은 정당으로 구분). `huboid`와 공식 기호(`giho`)는
  당선 행에만 있으므로, 칸 번호는 `ballot_position`으로 따로 둡니다.
- 득표율은 NEC 방식대로 소수 둘째 자리에서 절사합니다.
- 메타데이터 조회(선거 코드, 선거구·정당 코드)가 실패해도 결과 조회는 실패하지 않습니다. CommonCodeService를 쓸 수
  없으면 내장 선거 달력이나 결과 행에서 도출한 목록으로 대체하고 `warnings`에 알립니다.
- 가능하면 `huboid`를 우선하고, 없으면 정확한 이름으로 맞추며 정당은 동명이인 구분에만 씁니다.
- 해석이 불확실하면 임의로 고르지 않고 ambiguity 또는 경고와 함께 `None`을 반환합니다.

## Public `krpoltext` 규칙

공개 저장소는 `krpoltext` 텍스트 조회와 campaign booklet 코퍼스 메타데이터를 유지하지만, live NEC 공보물 탐색과 다운로드는 노출하지 않습니다.

- `get_krpoltext_text`는 코퍼스 기반 텍스트와 code-aware 매칭을 반환합니다.
- `assemble_candidate_packet`은 `krpoltext` 텍스트를 포함할 수 있지만 live booklet asset은 포함하지 않습니다.
- `campaign_booklet_corpus`는 manifest 해석, trusted host 검사, row 로딩을 담당합니다.
- dataset이 제공하면 `page_count` 같은 페이지 메타데이터를 보존해야 합니다.
- live NEC 공보물 URL 해석과 파일 다운로드는 public surface 밖에 둡니다.
## Resources와 발견 가능성

v1은 tool과 resource를 함께 제공합니다.

Resources:

- `resource://nec/elections`
- `resource://nec/districts/{sg_id}/{sg_typecode}`
- `resource://nec/parties/{sg_id}/{sg_typecode}`

LLM과 MCP client의 발견 가능성을 위해 같은 접근을 tool로도 제공합니다.

## 운영 메모

- NEC 키 우선순위: environment > OS keyring > `.env` fallback
- decoded만 설정해도 encoded 형식을 자동으로 파생합니다.
- 테스트는 mock과 stub에 친화적이며 live NEC 키를 요구하지 않습니다.
- 공개 배포 모델은 로컬 단일 사용자 BYOK입니다.
- hosted multi-user key storage는 v1 범위 밖입니다.

