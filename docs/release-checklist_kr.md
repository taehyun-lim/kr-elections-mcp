# 릴리스 체크리스트

[English](release-checklist.md)

## 사전 검증

- `pytest`를 실행합니다.
- `kr-elections-mcp --help`를 실행합니다.
- `kr-elections-mcp show-key-source`를 실행합니다.
- stdio 서버가 여전히 정상적으로 시작하는지 확인합니다.
- README Quick Start가 현재 CLI와 일치하는지 확인합니다.

## 보안 점검

- live NEC API 키가 커밋되어 있지 않은지 확인합니다.
- 로컬 전용 secret 경로가 문서에 남아 있지 않은지 확인합니다.
- 예제가 사용자가 키를 채팅에 붙여 넣도록 유도하지 않는지 확인합니다.
- 공개 릴리스가 live NEC 공보물 탐색, URL 해석, PDF 다운로드를 다시 노출하지 않는지 확인합니다.
- `krpoltext` 데이터셋과 텍스트 fetch가 계속 설정된 host로만 제한되는지 확인합니다.

## 문서 점검

- `README.md`와 `README_kr.md`가 서로 맞는지 확인합니다.
- 영문/국문 문서가 서로 올바르게 연결되는지 확인합니다.
- docs의 tool 이름이 실제 MCP surface와 일치하는지 확인합니다.
- 릴리스 노트가 실제 배포 동작을 설명하는지 확인합니다.

## GitHub 저장소 점검

- 저장소 About description과 topics를 설정합니다.
- 가능하면 social preview 이미지를 업로드합니다.
- 필요하면 branch protection 또는 review rule을 활성화합니다.
- `.github/CODEOWNERS`가 실제 owner handle을 반영하는지 확인합니다.

## 패키징 / 릴리스 페이지

- Git tag와 release title을 생성합니다.
- 준비한 릴리스 노트 초안을 붙여 넣습니다.
- 릴리스 본문에 중요한 문서 링크를 포함합니다.
- BYOK와 OS keyring 기반 키 설정 방식을 명시적으로 설명합니다.
