# 운영 보안 메모

[English](security.md)

이 문서는 South Korean Election MCP를 실행하고 확장할 때 지켜야 할 실무 보안 원칙을 정리합니다.

## 인증 정보 처리

권장 우선순위:

1. MCP client 또는 현재 프로세스 환경변수
2. OS keyring
3. `.env` 개발용 fallback

원칙:

- 사용자에게 MCP 채팅창에 API 키를 붙여 넣으라고 요구하지 않습니다.
- API 키를 저장하는 public MCP tool을 추가하지 않습니다.
- raw `serviceKey` 값을 로그에 남기지 않습니다.
- live API 키나 키가 보이는 스크린샷을 커밋하지 않습니다.
- 공개 저장소 사용자에게는 `kr-elections-mcp setup-key`를 우선 안내합니다.

## 공개 공보물 경계

공개 저장소는 live NEC 공보물 탐색, URL 해석, PDF 다운로드를 노출하면 안 됩니다.

필수 동작:

- NEC 공보물 다운로드 URL을 해석하는 public tool을 추가하지 않습니다.
- 공보물 파일을 로컬에 저장하는 public tool을 추가하지 않습니다.
- `assemble_candidate_packet`이 간접적으로 공보물 다운로드를 트리거하지 않게 유지합니다.
- `krpoltext` 텍스트 조회는 코퍼스와 trusted-host fetch 경로로만 제한합니다.
## 외부 데이터셋 안전성

- `krpoltext` 데이터셋과 legacy 텍스트 fetch는 설정된 host로만 제한합니다.
- 관련 없는 host를 가리키는 manifest URL이나 legacy index URL은 거부합니다.
- 제3자 dataset redirect를 그대로 따라가기보다 명시적 설정을 우선합니다.

## 로깅과 진단

- 가능하면 traceback에 secret 값이 드러나지 않게 합니다.
- 매칭과 판정 과정을 디버깅할 수 있을 만큼 provenance는 남깁니다.
- diagnostics 출력에서는 `unauthorized`, `not_applied`, `empty`, `error`를 구분합니다.
- debug dump나 cache payload를 통해 raw credential이 새지 않게 합니다.

## 로컬 파일 쓰기

- 실패가 보여야 하므로 structured warning과 partial-success 결과를 유지하고, 안전하지 않은 재시도는 피합니다.

## 공개 저장소 위생

릴리즈 전에 반드시 확인할 사항:

- live 키가 들어 있는 `.env`가 추적되고 있지 않은지 확인합니다.
- 테스트 파일에 복사된 secret이 없는지 확인합니다.
- 예제가 사용자에게 키를 채팅에 붙여 넣으라고 안내하지 않는지 확인합니다.
- README와 문서가 계속 keyring 또는 environment 기반 설정을 우선 안내하는지 확인합니다.
