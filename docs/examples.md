# Examples
[Korean](examples_kr.md)

## Candidate Packet Workflow

Typical user prompts:

- "Build a packet for candidate Lee Jae-myung."
- "Collect one candidate's profile, policies, results, and corpus text for Seoul Jongno."

Typical tool flow:

1. `search_candidates`
2. internal candidate resolution
3. `get_candidate_profile`
4. `get_candidate_policies`
5. result lookup through district or candidate matching
6. `get_krpoltext_text`
7. `assemble_candidate_packet`

## `krpoltext` Code Lookup

User prompts:

- "Use this booklet code to fetch the matching corpus text."
- "Check whether `krpoltext` has a row for this booklet code."
- "Show the campaign booklet text and page metadata if the corpus has it."

Typical tool call:

```text
get_krpoltext_text(code="ECM0120250014_0001S")
```

Notes:

- the public repository can use a known booklet `code` for corpus lookup
- the public repository does not derive live NEC booklet download URLs or save booklet PDFs



## `krpoltext` Metadata and Matching

User prompts:

- "Show the structured metadata for this booklet code."
- "Match this NEC candidate against `krpoltext` without guessing across same-name collisions."
- "Show me the `krpoltext` metadata row before fetching the full booklet text."

Typical tool flow:

1. `search_candidates`
2. `get_krpoltext_meta`
3. `match_krpoltext_candidate`
4. optional `get_krpoltext_text`

Typical metadata call:

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

Illustrative metadata response snippet:

```json
{
  "items": [
    {
      "code": "ECM0120240001_0007S",
      "candidate_name": "Alice Kim",
      "giho": "7",
      "birthday": "1970-01-02",
      "age": 54,
      "edu": "Seoul National University",
      "career1": "Former lawmaker",
      "career2": "Attorney",
      "has_text": true
    }
  ]
}
```

Typical conservative match call:

```text
match_krpoltext_candidate(
  candidate_name="Alice Kim",
  sg_id="20240410",
  sg_typecode="2",
  district_name="Seoul Jongno",
  limit=5
)
```

Illustrative match response snippet:

```json
{
  "status": "resolved",
  "item": {
    "code": "ECM0120240001_0007S",
    "match_method": "name+year+office+district+party+giho+birthday+age+education",
    "match_confidence": 1.0
  },
  "warnings": []
}
```

Ambiguous same-name collision example:

```json
{
  "status": "ambiguous",
  "item": null,
  "items": [
    {"code": "ECM0120240001_0007S"},
    {"code": "ECM0120240001_0008S"}
  ],
  "warnings": [
    "Multiple krpoltext rows remain plausible for the resolved NEC candidate; review giho, birthday, education, and career fields before choosing one."
  ]
}
```

These are illustrative response snippets meant to show the shape of the tool outputs.

## District Summary

User prompts:

- "Show the district summary for Jongno-gu in the 22nd legislative election."
- "Give me district-level results and turnout for this election and district."

Typical tool flow:

1. `list_elections`
2. `list_districts`
3. `get_district_results`
4. `get_district_summary`

## Diagnostics

User prompts:

- "Check whether my NEC API key is configured correctly."
- "Tell me which NEC access group is failing."

Typical tool flow:

1. `diagnose_core_api_access`
2. optional `diagnose_full_api_access`


