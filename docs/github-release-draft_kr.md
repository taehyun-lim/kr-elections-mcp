# GitHub 릴리스 초안

[English](github-release-draft.md)

이 문서는 초기 공개 릴리스 페이지에 바로 붙여 넣을 수 있는 초안입니다.

## 권장 릴리스 제목

`v0.1.0 - South Korean Election MCP initial public release`

## 대안 릴리스 제목

`v0.1.0 - Local FastMCP server for South Korean election data`

## 릴리스 본문

```md
## South Korean Election MCP v0.1.0

대한민국 선거 연구 워크플로를 위한 로컬 Python FastMCP 서버의 첫 공개 릴리스입니다.

### 주요 내용

- raw NEC endpoint 미러링 대신 task-oriented MCP tools 제공
- profile, policy, `krpoltext`, results를 결합한 candidate packet 조립
- 선거구 결과 및 요약 tool 제공
- public `krpoltext` 공보물 텍스트와 메타데이터 조회 지원
- 공개 배포에 적합한 OS keyring 기반 NEC API 키 설정
- 핵심 흐름에 대한 mock/stub 기반 pytest 커버리지

### 포함된 MCP tools

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
- `diagnose_full_api_access`
- `get_krpoltext_text`

### 보안과 키 처리

권장 API 키 설정:

```bash
kr-elections-mcp setup-key
```

이 방식은 사용자가 API 키를 채팅, tool input, 추적되는 repo 파일에 붙여 넣지 않고 로컬 OS keyring에 저장하도록 합니다.

### 빠른 시작

```bash
pip install .
kr-elections-mcp setup-key
kr-elections-mcp run
```

### 메모 및 제한사항

- NEC API 커버리지는 선거 종류와 시기에 따라 달라집니다
- 정책 데이터 가용성은 모든 선거에서 균일하지 않습니다
- 선거구명은 역사적으로 달라질 수 있으므로 매칭에는 정규화와 confidence metadata를 남깁니다
- `assemble_candidate_packet`은 가능할 때 `krpoltext` 텍스트와 메타데이터를 포함합니다
- 공개 릴리스는 live NEC 공보물 탐색, URL 해석, PDF 다운로드를 노출하지 않습니다
- `krpoltext` 지원은 설정된 static data API에 의존하며 NEC booklet를 실시간 OCR하지 않습니다

### 검증 상태

- 릴리스 시점 로컬 pytest 통과
- FastMCP stdio 서버 시작 확인 완료
```

## 짧은 공지 문구

South Korean Election MCP (kr-elections-mcp)가 공개되었습니다. 대한민국 선거 데이터를 candidate packet, district summary, `krpoltext` 공보물 텍스트, result lookup에 바로 쓸 수 있는 MCP tools로 바꿔 주는 로컬 FastMCP 서버입니다.
