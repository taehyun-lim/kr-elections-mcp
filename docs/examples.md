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

