# Data Sources

[English](data-sources.md)

## South Korean NEC Open Data

주요 구조화 데이터 소스는 [South Korean National Election Commission (NEC)](http://data.nec.go.kr/open-data/api-info.do) 공개 데이터 생태계이며, 키 발급과 상품 신청은 [공공데이터포털](https://www.data.go.kr/)을 통해 진행됩니다.

이 저장소의 핵심 사용 범위:

- 선거 목록과 코드 정보
- 선거구 목록
- 정당 목록
- 후보자 검색
- 후보자 프로필 상세
- 지원되는 경우 후보자 정책 데이터
- 당선인과 결과 데이터
- 투표율과 선거 요약 입력 데이터

처리 원칙:

- `resultType=json` 우선
- 필요하면 XML fallback 사용
- 표준 `data.go.kr` 오류 응답 해석
- 상위 계층에 넘기기 전에 중요한 필드 정규화
- 로컬 워크플로에 도움이 되는 경우 안정적인 응답 캐시

## `krpoltext`

`krpoltext`는 공보물 텍스트를 위한 보조 소스입니다.

현재 구현:

- `https://taehyun-lim.github.io/krpoltext/data`를 현재 data root로 사용합니다.
- `/data/index.json` 매니페스트를 읽습니다.
- 매니페스트 안의 `campaign_booklet` resource를 찾습니다.
- 해당 resource의 download URL에서 코퍼스 row를 읽습니다.
- 이름과 연도, 직위, 선거구 힌트로 매칭할 수 있습니다.
- booklet `code`로도 직접 매칭할 수 있습니다.
- dataset에 있으면 `party_name`, `page_count` 같은 코퍼스 메타데이터를 함께 보존합니다.

따라서 이 MCP는 유지되는 campaign booklet 코퍼스를 통해 공보물 텍스트를 반환할 수 있지만, live NEC PDF를 즉석 OCR하지 않으며 public surface에서 live NEC 공보물 다운로드 메커니즘을 노출하지도 않습니다.

## 결과 정합화 메모

선거 결과는 서로 다른 NEC 관점이나 부분 정규화 파일에서 올 수 있습니다. 이 저장소는 다음 공통 필드로 표준화합니다.

- 득표수
- 득표율
- 당선 여부
- source metadata
- coverage scope
- match method
- match confidence

## 참고 자료

- Tae Hyun Lim의 데이터셋 페이지는 두 코퍼스가 `krpoltext` R 패키지와 static data API를 통해 접근 가능하다고 설명하며, South Korean Election Campaign Booklet Corpus를 소개합니다: [Data Sets - Tae Hyun Lim](https://taehyun-lim.github.io/data_sets/)
- 현재 `krpoltext` 패키지 페이지는 campaign booklet corpus, OSF 기반 다운로드, 유지 중인 데이터 접근 방식을 설명합니다: [krpoltext package page](https://taehyun-lim.github.io/krpoltext/)
- Scientific Data 데이터 디스크립터는 2000년부터 2022년까지의 campaign booklet corpus를 설명합니다: [Scientific Data article](https://www.nature.com/articles/s41597-025-05220-4)

