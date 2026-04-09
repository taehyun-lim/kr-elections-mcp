# Data Sources

[Korean](data-sources_kr.md)

## South Korean NEC Open Data

The primary structured source is the [South Korean National Election Commission (NEC)](http://data.nec.go.kr/open-data/api-info.do) open-data ecosystem, with API keys and product applications handled through the [Public Data Portal (data.go.kr)](https://www.data.go.kr/).

Core usage in this repository:

- election lists and code information
- district lists
- party lists
- candidate search
- candidate profile details
- candidate policy data when supported
- winner and result data
- turnout and election-summary inputs

Processing rules:

- prefer `resultType=json`
- use XML fallback when needed
- interpret standard `data.go.kr` error responses
- normalize important fields before exposing them to higher layers
- cache stable responses when that helps local workflows

## `krpoltext`

`krpoltext` is used as a text-oriented companion source for campaign booklet text.

Current implementation:

- it uses the current `krpoltext` data root at `https://taehyun-lim.github.io/krpoltext/data`
- it reads the current dataset manifest from `/data/index.json`
- it resolves the `campaign_booklet` resource from that manifest
- it reads campaign booklet rows from the resource download URL
- it can match on candidate name plus optional year, office, and district hints
- it can also match directly on booklet `code`
- it preserves corpus metadata such as `party_name` and `page_count` when those fields exist

This MCP can therefore return booklet-related text through the maintained campaign booklet corpus, but it does not OCR live NEC booklet PDFs on demand or expose live NEC booklet download mechanics in the public surface.

## Result Harmonization Notes

Election results can come from different NEC-oriented views or partially normalized files. The repository standardizes them into shared models with:

- vote count
- vote share
- winner flag
- source metadata
- coverage scope
- match method
- match confidence

## References

- Tae Hyun Lim's dataset page notes that both corpora are accessible through the `krpoltext` R package and a static data API, and describes the South Korean Election Campaign Booklet Corpus: [Data Sets - Tae Hyun Lim](https://taehyun-lim.github.io/data_sets/)
- The current `krpoltext` package page documents the campaign booklet corpus, OSF-backed downloads, and the package's maintained data access workflow: [krpoltext package page](https://taehyun-lim.github.io/krpoltext/)
- The Scientific Data data descriptor describes the campaign booklet corpus and its coverage from 2000 to 2022: [Scientific Data article](https://www.nature.com/articles/s41597-025-05220-4)

