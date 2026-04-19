# South Korean Election MCP (kr-elections-mcp)

[English README](README.md)

[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.19490046-blue)](https://doi.org/10.5281/zenodo.19490046)
[![CI](https://github.com/taehyun-lim/kr-elections-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/taehyun-lim/kr-elections-mcp/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Auth: BYOK](https://img.shields.io/badge/auth-BYOK-4C9A2A)](https://www.data.go.kr/)

South Korean Election MCP (kr-elections-mcp)는 한국 선거 연구를 위한 로컬 Python FastMCP 서버입니다. NEC 공개 데이터, 정규화된 선거 결과 어댑터, `krpoltext` 텍스트 조회를 작업 중심 MCP 도구로 묶습니다.

이 저장소는 composite-first 방식입니다. raw NEC endpoint를 전부 그대로 MCP tool로 노출하기보다, 후보자 packet, 선거구 요약, 선거 개요, 진단, 텍스트 조회처럼 연구 가치가 높은 작업을 우선합니다.

## 제공 기능

- 후보자 검색과 기본 프로필 조회
- NEC 범위 내 후보자 정책 조회
- 선거구 단위 결과와 요약 조회
- 정당 득표율 이력과 선거 개요 조회
- `krpoltext` 캠페인 공보물 코퍼스 텍스트 조회
- NEC, 결과, `krpoltext` 텍스트를 묶는 후보자 packet 조립
- 로컬 BYOK 환경을 위한 NEC API 진단

## 빠른 시작

### 1. 패키지 설치

```bash
pip install .
```

### 2. NEC API 이용 신청

이 프로젝트는 BYOK 방식입니다. 사용자가 직접 [공공데이터포털](https://www.data.go.kr/)에서 필요한 NEC OpenAPI 상품을 신청해야 합니다.

공공데이터포털 안내:

> API 환경 또는 API 호출 조건에 따라 인증키가 적용되는 방식이 다를 수 있습니다.
> 포털에서 제공되는 Encoding/Decoding 된 인증키를 적용하면서 구동되는 키를 사용하시기 바랍니다.
> 향후 포털에서 더 명확한 정보를 제공하기 위해 노력하겠습니다.

이 서버는 encoding 키와 decoding 키를 모두 받을 수 있습니다.

자세한 내용:

- [API Access Guide](docs/api-access_kr.md)
- [Source Status](docs/source-status_kr.md)

### 3. 키를 안전하게 저장

권장:

```bash
kr-elections-mcp setup-key
```

`setup-key`는 encoded 키와 decoded 키를 모두 받을 수 있습니다. 하나만 저장해도 됩니다.

이 저장소의 동작:

- `NEC_API_KEY_DECODED`만 있어도 encoded 형식을 자동으로 만들어 함께 시도합니다.
- 요청 순서는 항상 decoded 먼저, encoded 다음입니다.
- legacy `NEC_API_KEY`도 fallback으로는 계속 지원합니다.

유용한 명령:

```bash
kr-elections-mcp show-key-source
kr-elections-mcp clear-key
```

### 4. MCP 서버 실행

```bash
kr-elections-mcp run
```

## MCP 클라이언트 예시

```json
{
  "mcpServers": {
    "south-korean-election": {
      "command": "kr-elections-mcp",
      "args": ["run"]
    }
  }
}
```

OS keyring을 쓰지 않으려면 MCP 클라이언트 환경변수로 넣을 수 있습니다.

```json
{
  "mcpServers": {
    "south-korean-election": {
      "command": "kr-elections-mcp",
      "args": ["run"],
      "env": {
        "NEC_API_KEY_DECODED": "YOUR_DECODED_KEY"
      }
    }
  }
}
```

decoded 키가 있으면 `NEC_API_KEY_ENCODED`는 선택 사항입니다.

## API 키 저장 규칙

키 조회 우선순위:

1. 현재 프로세스 또는 MCP client `env`
2. OS keyring
3. `.env` 개발용 fallback

같은 source 안에서는 `NEC_API_KEY_DECODED`와 `NEC_API_KEY_ENCODED`를 우선 사용하고, 마지막에 legacy `NEC_API_KEY`를 fallback으로 사용합니다.

공개 저장소 사용자에게 권장하는 방식:

- 가능하면 `kr-elections-mcp setup-key` 사용
- 키를 채팅, 스크린샷, Git commit에 남기지 않기
- `.env`는 개발용 fallback으로만 사용
- 많은 환경에서는 `NEC_API_KEY_DECODED`만으로 충분함

## 소스 체크아웃 fallback

설치된 패키지 대신 저장소 checkout에서 바로 실행하는 경우에는 기존 명령도 계속 사용할 수 있습니다.

```bash
python server.py setup-key
python server.py show-key-source
python server.py run
```

로컬 `.env` fallback을 의도적으로 사용할 때만 `--env-file .env`를 붙이세요.

```bash
kr-elections-mcp run --env-file .env
python server.py run --env-file .env
```

## Tools

핵심 tools:

- `list_elections`
- `list_districts`
- `list_parties`
- `search_candidates`
- `get_candidate_profile`
- `get_candidate_policies`
- `get_district_results`
- `get_district_summary`
- `get_party_vote_share_history`
- `get_election_overview`
- `assemble_candidate_packet`
- `diagnose_core_api_access`

추가 tools:

- `diagnose_full_api_access`
- `get_krpoltext_text`
- `get_krpoltext_meta`
- `match_krpoltext_candidate`

## `krpoltext` 텍스트 지원

이 저장소는 live NEC PDF를 그때그때 OCR하지 않습니다.

현재 동작:

- `get_krpoltext_text`는 이름과 연도, 직위, 선거구, 정당 힌트로 찾을 수 있습니다.
- booklet `code`로도 직접 찾을 수 있습니다.
- `get_krpoltext_meta`는 긴 공보물 본문 없이 구조화된 campaign booklet metadata를 반환합니다.
- metadata tool은 upstream dataset이 제공하면 `giho`, `birthday`, `age`, `job*`, `edu*`, `career*` 같은 병합된 후보자 bio field도 보존합니다.
- `match_krpoltext_candidate`는 먼저 NEC 후보자를 해결한 다음, 선거 범위와 더 강한 개인 식별자를 써서 `krpoltext` row를 순위화합니다.
- 같은 선거, 같은 선거구, 같은 이름 충돌은 더 강한 개인 식별자가 유일하게 맞지 않으면 계속 ambiguous로 남깁니다.
- 현재 [`krpoltext`](https://taehyun-lim.github.io/krpoltext/)의 /data/index.json 매니페스트를 읽고, 필요하면 /data/metadata.json으로 fallback한 뒤 campaign_booklet resource를 따라갑니다.
- 원격 데이터셋과 legacy 텍스트 fetch는 설정된 [`krpoltext`](https://taehyun-lim.github.io/krpoltext/) host로만 제한됩니다.
- upstream 코퍼스가 제공하면 `huboid` 같은 enriched NEC linkage field를 보존하고, `match_krpoltext_candidate`가 강한 식별자로 활용할 수 있습니다.
- 런타임 설치에 `pyarrow`가 포함되어 enriched Parquet 아티팩트를 기본 우선 경로로 사용할 수 있고, CSV 메타데이터와 fallback URL도 계속 지원합니다.
- 코퍼스에 텍스트가 있으면 dataset-backed 텍스트 레코드를 반환하고, 가능할 때 `code`, `party_name`, `page_count` 같은 코퍼스 메타데이터도 함께 돌려줍니다.
- 이 공개 저장소는 live NEC 공보물 탐색, URL 해석, PDF 다운로드를 노출하지 않습니다.

예시 metadata 조회:

```text
get_krpoltext_meta(
  candidate_name="Alice Kim",
  election_year=2024,
  office_name="national_assembly",
  district_name="Seoul Jongno",
  party_name="Independent",
  limit=3
)
```

예시 응답 형태:

```json
{
  "items": [
    {
      "record_id": "K1",
      "code": "ECM0120240001_0007S",
      "candidate_name": "Alice Kim",
      "office_name": "national_assembly",
      "election_year": 2024,
      "district_name": "Seoul Jongno",
      "giho": "7",
      "party_name": "Independent",
      "birthday": "1970-01-02",
      "age": 54,
      "edu": "Seoul National University",
      "career1": "Former lawmaker",
      "career2": "Attorney",
      "has_text": true
    }
  ],
  "warnings": []
}
```

예시 보수적 NEC-`krpoltext` 매칭:

```text
match_krpoltext_candidate(
  candidate_name="Alice Kim",
  sg_id="20240410",
  sg_typecode="2",
  district_name="Seoul Jongno",
  limit=5
)
```

예시 응답 형태:

```json
{
  "status": "resolved",
  "message": "Resolved krpoltext metadata row using stronger personal identifiers.",
  "item": {
    "code": "ECM0120240001_0007S",
    "candidate_name": "Alice Kim",
    "district_name": "Seoul Jongno",
    "giho": "7",
    "birthday": "1970.01.02",
    "age": 54,
    "match_method": "name+year+office+district+party+giho+birthday+age+education",
    "match_confidence": 1.0
  },
  "warnings": [],
  "errors": []
}
```

위 예시는 설명용 응답 형태이며, live 데이터 row를 보장하는 예시는 아닙니다.

## Resources

- `resource://nec/elections`
- `resource://nec/districts/{sg_id}/{sg_typecode}`
- `resource://nec/parties/{sg_id}/{sg_typecode}`

## 문서

- [API Access Guide](docs/api-access_kr.md) ([English](docs/api-access.md))
- [Source Status](docs/source-status_kr.md) ([English](docs/source-status.md))
- [Architecture](docs/architecture_kr.md) ([English](docs/architecture.md))
- [Data Sources](docs/data-sources_kr.md) ([English](docs/data-sources.md))
- [Examples](docs/examples_kr.md) ([English](docs/examples.md))
- [Tool Matrix](docs/tool-matrix_kr.md) ([English](docs/tool-matrix.md))
- [krpoltext Matching Guide](docs/krpoltext-matching_kr.md) ([English](docs/krpoltext-matching.md))
- [Operational Security Notes](docs/security_kr.md) ([English](docs/security.md))

## 테스트

테스트는 live NEC 키 없이도 mock과 stub로 돌릴 수 있게 설계되어 있습니다.

```bash
pytest
```

source adapter 관련 테스트는 `krpoltext` 매니페스트 해석, trusted host 처리, campaign booklet corpus lookup을 다룹니다.

## 한계

- NEC 정책 데이터는 선거와 직위별 지원 범위가 다릅니다.
- live NEC API 사용은 여전히 각 사용자의 `data.go.kr` 승인 상태에 좌우됩니다.
- 결과 데이터 범위는 source와 과거 선거 가용성에 따라 달라질 수 있습니다.
- `krpoltext` 지원은 현재 외부 dataset manifest에 의존하며, live NEC 공보물 PDF OCR은 수행하지 않습니다.

## License

이 프로젝트는 [MIT License](LICENSE)로 배포됩니다.


