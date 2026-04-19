# Source Status

[English](source-status.md)

이 문서는 2026-04-07 기준 `kr-elections-mcp`가 기대하는 외부 소스 상태를 기록합니다.

## NEC API 접근

예상 키 동작:

- 서버는 decoded 키와 encoded 키를 모두 받을 수 있습니다.
- decoded 키만 설정돼 있어도 encoded 형식을 자동으로 만들어 함께 시도합니다.
- 요청 순서는 decoded 먼저, encoded 다음입니다.
- legacy `NEC_API_KEY`는 fallback 전용으로 남아 있습니다.

운영 메모:

- `show-key-source`는 active source와 configured key formats를 함께 보여줘야 합니다.

## NEC 핵심 API 매핑

저장소는 현재 code info, candidate info, winner info, tally info에 대해 공식 `data.go.kr` 상품 페이지와 맞는 NEC API 매핑을 기대합니다.

source update 중 확인된 점:

- 핵심 선거 목록과 선거구 조회는 공식 endpoint 정렬이 필요했습니다.
- 후보자 프로필과 정책 조회는 NEC 변형 응답을 넘기기 위한 fallback 처리가 필요했습니다.
- downstream diagnostics는 선행 election-code 조회가 성공해야 연쇄적으로 동작합니다.

## `krpoltext` 소스 상태

현재 `krpoltext` 가정:

- 유지되는 data root는 `https://taehyun-lim.github.io/krpoltext/data`
- 유지되는 매니페스트는 `/data/index.json`이며, 필요하면 `/data/metadata.json` 형식으로 fallback합니다.
- campaign booklet 텍스트 해석은 매니페스트 안의 `campaign_booklet` resource를 기준으로 해야 합니다.
- booklet 텍스트 조회는 이름 필터뿐 아니라 booklet code로도 직접 찾을 수 있어야 합니다.
- huboid 같은 enriched linkage field는 가능할 때 보존하고 활용해야 합니다.
- public 저장소는 `party_name`, `page_count` 같은 코퍼스 메타데이터를 보존해야 합니다.
- public 저장소는 live NEC 공보물 탐색과 다운로드를 노출하지 않습니다.

이는 예전처럼 루트 `krpoltext` 사이트에서 곧바로 사용 가능한 최상위 `index.json`을 항상 기대하던 가정을 대체합니다.

## Tool 단위 메모

현재 기대되는 public tool 동작:

- `get_krpoltext_text`는 booklet `code`로도 매칭할 수 있습니다.
- `assemble_candidate_packet`은 `krpoltext` 텍스트 레코드를 포함할 수 있습니다.
- 어떤 public tool도 live NEC 공보물 다운로드 URL을 해석하거나 파일을 저장하지 않습니다.

## 저장소 테스트 커버리지

source adapter 변경을 위한 주요 테스트:

- `tests/test_campaign_booklet_sources.py`
- `tests/test_krpoltext_api.py`

이 테스트들은 매니페스트 해석, trusted host 처리, campaign booklet corpus lookup, 사용자 대상 `krpoltext` 동작을 다룹니다.

