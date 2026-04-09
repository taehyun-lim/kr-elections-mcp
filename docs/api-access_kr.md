# API Access Guide

[English](api-access.md)

South Korean Election MCP (kr-elections-mcp)는 BYOK 방식으로 동작합니다. 사용자가 직접 NEC API 접근 권한을 신청하고 키를 관리해야 합니다.

## 공식 진입점

- [South Korean National Election Commission (NEC) Open Data API Info](http://data.nec.go.kr/open-data/api-info.do)
- [공공데이터포털](https://www.data.go.kr/)

## 사용자가 해야 할 일

1. 필요한 NEC OpenAPI 상품을 확인합니다.
2. `data.go.kr`에서 필요한 NEC API 상품을 신청합니다.
3. 자동승인이 아닌 상품은 승인 완료를 기다립니다.
4. 승인 후 encoded 키와 decoded 키를 확인합니다.
5. 로컬에 저장합니다.

```bash
kr-elections-mcp setup-key
```

## 키 형식

공공데이터포털 안내:

> API 환경 또는 API 호출 조건에 따라 인증키가 적용되는 방식이 다를 수 있습니다.
> 포털에서 제공되는 Encoding/Decoding 된 인증키를 적용하면서 구동되는 키를 사용하시기 바랍니다.
> 향후 포털에서 더 명확한 정보를 제공하기 위해 노력하겠습니다.

이 저장소의 동작:

- `setup-key`는 encoded 키와 decoded 키를 모두 받을 수 있습니다.
- 둘 다 저장할 수도 있고 하나만 저장할 수도 있습니다.
- decoded 키만 있으면 encoded 형식을 자동으로 만들어 함께 시도합니다.
- 요청 순서는 항상 decoded 먼저, encoded 다음입니다.
- legacy `NEC_API_KEY`도 fallback 입력으로는 계속 지원합니다.

## 권장 로컬 설정

```bash
pip install .
kr-elections-mcp setup-key
kr-elections-mcp show-key-source
kr-elections-mcp run
```

로컬 `.env` fallback을 의도적으로 사용할 때만 `--env-file .env`를 붙이세요.

```bash
kr-elections-mcp run --env-file .env
```

환경변수로도 설정할 수 있습니다.

```env
NEC_API_KEY_DECODED=your_decoded_service_key
NEC_API_KEY_ENCODED=your_encoded_service_key
```

많은 환경에서는 `NEC_API_KEY_DECODED`만으로 충분합니다.

## 중요 메모

- `data.go.kr` 계정이 있다고 해서 모든 NEC API를 바로 쓸 수 있는 것은 아닙니다. 상품별 승인 범위가 다를 수 있습니다.
- 한 NEC 서비스에서 되는 키가 다른 서비스에서는 승인이 없어 실패할 수 있습니다.
- 이 저장소는 공용 API 키를 제공하지 않습니다.
- 공개 저장소 사용자라면 `.env` 커밋 대신 OS keyring이나 MCP client 환경변수를 권장합니다.
- encoded 키를 셸에 넣기 불편한 환경에서는 decoded 키만 저장하는 것이 가장 단순한 경우가 많습니다.
- 소스 checkout에서는 `python server.py ...` fallback도 계속 사용할 수 있습니다.
