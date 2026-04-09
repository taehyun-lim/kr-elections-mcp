# Examples
[English](examples.md)

## Candidate Packet 워크플로

대표적인 사용자 질의:

- "이재명 후보 packet 만들어줘."
- "서울 종로에서 후보자 한 명의 profile, policies, results, 코퍼스 text를 모아줘."

대표적인 tool 흐름:

1. `search_candidates`
2. 내부 후보자 해석
3. `get_candidate_profile`
4. `get_candidate_policies`
5. 선거구 또는 후보자 기준 결과 조회
6. `get_krpoltext_text`
7. `assemble_candidate_packet`

## `krpoltext` Code Lookup

사용자 질의:

- "이 공보물 code로 매칭되는 코퍼스 텍스트를 찾아줘."
- "`krpoltext`에 이 booklet code row가 있는지 확인해줘."
- "코퍼스에 page metadata가 있으면 같이 보여줘."

대표적인 tool 호출:

```text
get_krpoltext_text(code="ECM0120250014_0001S")
```

메모:

- 공개 저장소는 이미 알고 있는 booklet `code`로 코퍼스 조회를 할 수 있습니다.
- 공개 저장소는 live NEC 공보물 URL을 해석하거나 PDF를 저장하지 않습니다.


사용자 질의:

- "이 공보물 code로 매칭되는 코퍼스 텍스트를 찾아줘."
- "`krpoltext`에 이 booklet code row가 있는지 확인해줘."

대표적인 tool 호출:

```text
get_krpoltext_text(code="ECM0120250014_0001S")
```

## 선거구 요약

사용자 질의:

- "제22대 총선 종로구 district summary 보여줘."
- "이 선거와 선거구의 district-level results와 turnout을 보여줘."

대표적인 tool 흐름:

1. `list_elections`
2. `list_districts`
3. `get_district_results`
4. `get_district_summary`

## Diagnostics

사용자 질의:

- "내 NEC API 키 설정이 맞는지 확인해줘."
- "어느 NEC access group에서 실패하는지 알려줘."

대표적인 tool 흐름:

1. `diagnose_core_api_access`
2. 필요하면 `diagnose_full_api_access`

