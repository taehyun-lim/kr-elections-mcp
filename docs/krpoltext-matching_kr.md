# krpoltext 매칭 가이드

이 문서는 NEC 후보자 데이터와 `krpoltext` 공보물 메타데이터를 함께 쓸 때의 공개 MCP 워크플로를 설명합니다.

## 공개 워크플로

1. `search_candidates` 또는 후보자 관련 tool로 NEC 후보자를 먼저 확정합니다.
2. `get_krpoltext_meta`로 구조화된 공보물 메타데이터를 확인합니다.
3. 보수적인 NEC-`krpoltext` 조인을 위해 `match_krpoltext_candidate`를 사용합니다.
4. row가 확정되었거나 `code`를 이미 알고 있을 때 `get_krpoltext_text`로 본문 텍스트를 가져옵니다.

## 매칭 상태

- `resolved`: 선거, 직위, 선거구와 더 강한 개인 식별 신호를 적용한 뒤 한 row만 남은 상태입니다.
- `ambiguous`: plausible한 row가 여러 개 남아서 MCP가 자동 선택하지 않은 상태입니다.
- `not_found`: 해결된 NEC 후보자와 충분히 강하게 맞는 metadata row를 찾지 못한 상태입니다.

## 매칭 신호

공용 matcher는 먼저 NEC 후보자 컨텍스트를 씁니다.

- NEC 선거일에서 파생한 선거연도
- 직위명
- 정규화된 선거구 라벨
- 후보자 이름
- 가능하면 정당명

그 다음 `krpoltext` metadata에 있는 더 강한 개인 식별 신호를 사용합니다.

- `giho`
- `birthday`
- `age`
- `job*`
- `edu*`
- `career1`
- `career2`

matcher는 의도적으로 보수적입니다. 같은 선거, 같은 선거구, 같은 이름 충돌은 더 강한 개인 식별자가 유일하게 맞지 않으면 계속 `ambiguous`로 남깁니다.

## Upstream에서 더 제공되면 좋은 점

현재 `krpoltext` metadata는 텍스트만 있을 때보다 훨씬 낫지만, upstream dataset 또는 API가 아래 항목을 함께 제공하면 공개 통합이 더 쉽고 안전해집니다.

- merge에 사용된 NEC 후보자 식별자, 예: `huboid` 또는 `cnddtId`
- 정확한 NEC 선거 식별자, 예: `sgId`, `sgTypecode`
- region/district 문자열만이 아니라 canonical district identifier
- 긴 본문 텍스트를 기본 제외한 metadata-only endpoint 또는 artifact
- booklet `code` 기준의 row-level lookup endpoint
- metadata field와 type을 설명하는 안정적인 schema endpoint

이런 항목이 있으면 fuzzy join이 줄고, MCP client 구현이 단순해지며, 재현성도 좋아집니다.
