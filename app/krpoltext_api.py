from __future__ import annotations

import logging
from typing import Any, Callable

import requests

from .campaign_booklet_corpus import (
    CampaignBookletCorpus,
    build_region_district_label,
    resolve_trusted_krpoltext_url,
)
from .coerce import as_float, as_int, as_str
from .config import Settings
from .models import (
    AvailabilityState,
    KrPolTextInput,
    KrPolTextMetaRecord,
    KrPolTextRecord,
    ProvenanceRecord,
)
from .normalize import map_party_name, similarity


logger = logging.getLogger(__name__)


class KrPolTextClient:
    def __init__(
        self,
        settings: Settings,
        *,
        session: requests.Session | None = None,
        index_loader: Callable[[], list[dict[str, Any]]] | None = None,
        corpus: CampaignBookletCorpus | None = None,
    ) -> None:
        self.settings = settings
        self.session = session or requests.Session()
        self.index_loader = index_loader
        self._index_cache: list[dict[str, Any]] | None = None
        self._manifest_payload: dict[str, Any] | None = None
        self.corpus = corpus or CampaignBookletCorpus(
            settings,
            session=self.session,
            manifest_loader=self._manifest_loader,
        )

    def get_text(self, query: KrPolTextInput) -> list[KrPolTextRecord]:
        legacy_records = self._load_legacy_index()
        if legacy_records is not None:
            matches: list[tuple[float, KrPolTextRecord]] = []
            for row in legacy_records:
                score = self._score_legacy_row(row, query)
                if score < 0.45:
                    continue
                record = self._legacy_row_to_record(row, score)
                matches.append((score, record))
            matches.sort(key=lambda item: item[0], reverse=True)
            return [record for _, record in matches[: query.limit]]

        rows = self._search_corpus_rows(query)
        return [self._corpus_row_to_record(row) for row in rows]

    def get_metadata(self, query: KrPolTextInput) -> list[KrPolTextMetaRecord]:
        legacy_records = self._load_legacy_index()
        if legacy_records is not None:
            matches: list[tuple[float, KrPolTextMetaRecord]] = []
            for row in legacy_records:
                score = self._score_legacy_row(row, query)
                if score < 0.45:
                    continue
                record = self._legacy_row_to_meta_record(row, score)
                matches.append((score, record))
            matches.sort(key=lambda item: item[0], reverse=True)
            return [record for _, record in matches[: query.limit]]

        rows = self._search_corpus_rows(query)
        return [self._corpus_row_to_meta_record(row) for row in rows]

    def time_coverage(self) -> str | None:
        return self.corpus.time_coverage()

    def supported_year_range(self) -> tuple[int | None, int | None]:
        return self.corpus.supported_year_range()

    def _search_corpus_rows(self, query: KrPolTextInput) -> list[dict[str, Any]]:
        return self.corpus.search_rows(
            candidate_name=query.candidate_name,
            election_year=query.election_year,
            office_name=query.office_name,
            district_name=query.district_name,
            party_name=query.party_name,
            code=query.code,
            limit=query.limit,
        )

    def _load_legacy_index(self) -> list[dict[str, Any]] | None:
        if self._index_cache is not None:
            return self._index_cache
        if self.index_loader:
            self._index_cache = self.index_loader()
            return self._index_cache
        try:
            response = self.session.get(
                f"{self.settings.krpoltext_base_url.rstrip('/')}/index.json",
                headers={"User-Agent": self.settings.user_agent},
                timeout=self.settings.request_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            logger.warning("krpoltext legacy index fetch failed: %s", exc)
            self._index_cache = None
            return self._index_cache
        if isinstance(payload, list):
            self._index_cache = [row for row in payload if isinstance(row, dict)]
        elif isinstance(payload, dict):
            self._manifest_payload = payload
            self._index_cache = None
        else:
            self._index_cache = None
        return self._index_cache

    def _score_legacy_row(self, row: dict[str, Any], query: KrPolTextInput) -> float:
        score = 0.0
        if query.code:
            row_code = str(row.get("code") or row.get("record_id") or row.get("id") or "")
            requested = str(query.code).strip()
            if requested.lower() == row_code.lower():
                score += 0.75
            elif requested.replace("_", "").replace("-", "").lower() == row_code.replace("_", "").lower():
                score += 0.7
            else:
                return 0.0
        if query.candidate_name:
            score += similarity(row.get("candidate_name"), query.candidate_name) * 0.55
        if query.election_year and row.get("election_year"):
            if int(row["election_year"]) == query.election_year:
                score += 0.2
            elif not query.code:
                return 0.0
            else:
                score -= 0.3
        if query.office_name and row.get("office_name"):
            score += similarity(row.get("office_name"), query.office_name) * 0.15
        if query.district_name and row.get("district_name"):
            score += similarity(row.get("district_name"), query.district_name) * 0.1
        if query.party_name:
            party_score = similarity(map_party_name(row.get("party_name") or row.get("party")), query.party_name)
            if party_score < 0.45 and not query.code:
                return 0.0
            score += party_score * 0.05
        return round(max(score, 0.0), 3)

    def _legacy_row_to_record(self, row: dict[str, Any], score: float) -> KrPolTextRecord:
        text = row.get("text") or row.get("body")
        raw_source_url = row.get("source_url") or row.get("url")
        source_url = resolve_trusted_krpoltext_url(self.settings, raw_source_url)
        warnings: list[str] = []
        if not text and source_url:
            text = self._fetch_text(source_url)
        if not text and raw_source_url and not source_url:
            warnings.append("Text source URL was rejected because it is outside trusted krpoltext hosts.")
        if not text and not warnings:
            warnings.append("Text body was not embedded in the index record.")
        availability = AvailabilityState.AVAILABLE if text else AvailabilityState.PARTIAL
        record_marker = row.get("record_id") or row.get("id") or row.get("code") or row.get("candidate_name")
        return KrPolTextRecord(
            record_id=str(record_marker or "krpoltext-record"),
            code=row.get("code"),
            candidate_name=row.get("candidate_name"),
            office_name=row.get("office_name"),
            election_year=self._as_int(row.get("election_year")),
            district_name=row.get("district_name"),
            party_name=row.get("party_name") or row.get("party"),
            dataset_version=row.get("dataset_version") or row.get("version"),
            source="krpoltext",
            source_url=source_url,
            text=text,
            time_range=row.get("time_range") or row.get("date_range"),
            availability=availability,
            match_method="year+office+candidate",
            match_confidence=score,
            provenance=[
                ProvenanceRecord(
                    source_name="krpoltext",
                    entity_type="text_asset",
                    source_ref=source_url or str(record_marker or "krpoltext-record"),
                    access_method="index_json",
                )
            ],
            warnings=warnings,
        )

    def _legacy_row_to_meta_record(self, row: dict[str, Any], score: float) -> KrPolTextMetaRecord:
        raw_source_url = row.get("source_url") or row.get("url")
        source_url = resolve_trusted_krpoltext_url(self.settings, raw_source_url)
        warnings: list[str] = []
        if raw_source_url and not source_url:
            warnings.append("Metadata source URL was rejected because it is outside trusted krpoltext hosts.")
        has_text = bool(row.get("text") or row.get("body"))
        availability = AvailabilityState.AVAILABLE if (has_text or source_url) else AvailabilityState.PARTIAL
        record_marker = row.get("record_id") or row.get("id") or row.get("code") or row.get("candidate_name")
        return KrPolTextMetaRecord(
            record_id=str(record_marker or "krpoltext-record"),
            code=row.get("code"),
            candidate_name=row.get("candidate_name"),
            office_id=self._as_int(row.get("office_id")),
            office_name=row.get("office_name"),
            election_year=self._as_int(row.get("election_year")),
            region_name=row.get("region") or row.get("region_name"),
            district_raw=row.get("district") or row.get("district_name"),
            district_name=row.get("district_name"),
            giho=self._as_str(row.get("giho")),
            party_name=row.get("party_name") or row.get("party"),
            party_name_eng=row.get("party_name_eng") or row.get("party_eng"),
            result=row.get("result"),
            result_code=self._as_int(row.get("result_code")),
            sex=row.get("sex") or row.get("gender"),
            sex_code=self._as_int(row.get("sex_code")),
            birthday=self._as_str(row.get("birthday")),
            age=self._as_int(row.get("age")),
            job_id=self._as_str(row.get("job_id")),
            job=self._as_str(row.get("job")),
            job_name=self._as_str(row.get("job_name")),
            job_name_eng=self._as_str(row.get("job_name_eng")),
            job_code=self._as_int(row.get("job_code")),
            edu_id=self._as_str(row.get("edu_id")),
            edu=self._as_str(row.get("edu")),
            edu_name=self._as_str(row.get("edu_name")),
            edu_name_eng=self._as_str(row.get("edu_name_eng")),
            edu_code=self._as_int(row.get("edu_code")),
            career1=self._as_str(row.get("career1")),
            career2=self._as_str(row.get("career2")),
            page_count=self._as_int(row.get("page_count") or row.get("pages")),
            has_text=has_text,
            dataset_version=row.get("dataset_version") or row.get("version"),
            source="krpoltext",
            source_url=source_url,
            time_range=row.get("time_range") or row.get("date_range"),
            availability=availability,
            match_method="year+office+candidate",
            match_confidence=score,
            provenance=[
                ProvenanceRecord(
                    source_name="krpoltext",
                    entity_type="text_asset",
                    source_ref=source_url or str(record_marker or "krpoltext-record"),
                    access_method="index_json",
                )
            ],
            warnings=warnings,
            raw_fields=self._raw_metadata_fields(row),
        )

    def _corpus_row_to_record(self, row: dict[str, Any]) -> KrPolTextRecord:
        dataset_url = self.corpus.campaign_booklet_download_url()
        text = row.get("filtered") or row.get("filtered_text") or row.get("text")
        district_name = build_region_district_label(row.get("region"), row.get("district"))
        return KrPolTextRecord(
            record_id=str(row.get("code") or row.get("name") or dataset_url or "krpoltext-campaign-booklet"),
            code=row.get("code"),
            candidate_name=row.get("name"),
            office_name=row.get("office"),
            election_year=self._extract_year(row.get("date")),
            district_name=district_name,
            party_name=row.get("party"),
            page_count=self._as_int(row.get("page_count") or row.get("pages")),
            dataset_version=self.corpus.dataset_version(),
            source="krpoltext",
            source_url=dataset_url,
            text=text,
            time_range=row.get("date"),
            availability=AvailabilityState.AVAILABLE if text else AvailabilityState.PARTIAL,
            match_method="campaign_booklet_dataset",
            match_confidence=self._as_float(row.get("_match_score")),
            provenance=[
                ProvenanceRecord(
                    source_name="krpoltext",
                    entity_type="text_asset",
                    source_ref=str(row.get("code") or dataset_url),
                    access_method="campaign_booklet_dataset",
                )
            ],
            warnings=[] if text else ["The matched campaign_booklet row did not contain text."],
        )

    def _corpus_row_to_meta_record(self, row: dict[str, Any]) -> KrPolTextMetaRecord:
        dataset_url = self.corpus.campaign_booklet_download_url()
        district_name = build_region_district_label(row.get("region"), row.get("district"))
        has_text = bool(row.get("filtered") or row.get("filtered_text") or row.get("text"))
        return KrPolTextMetaRecord(
            record_id=str(row.get("code") or row.get("name") or dataset_url or "krpoltext-campaign-booklet"),
            code=row.get("code"),
            candidate_name=row.get("name"),
            office_id=self._as_int(row.get("office_id")),
            office_name=row.get("office"),
            election_year=self._extract_year(row.get("date")),
            region_name=self._as_str(row.get("region")),
            district_raw=self._as_str(row.get("district")),
            district_name=district_name,
            giho=self._as_str(row.get("giho")),
            party_name=self._as_str(row.get("party")),
            party_name_eng=self._as_str(row.get("party_eng")),
            result=self._as_str(row.get("result")),
            result_code=self._as_int(row.get("result_code")),
            sex=self._as_str(row.get("sex")),
            sex_code=self._as_int(row.get("sex_code")),
            birthday=self._as_str(row.get("birthday")),
            age=self._as_int(row.get("age")),
            job_id=self._as_str(row.get("job_id")),
            job=self._as_str(row.get("job")),
            job_name=self._as_str(row.get("job_name")),
            job_name_eng=self._as_str(row.get("job_name_eng")),
            job_code=self._as_int(row.get("job_code")),
            edu_id=self._as_str(row.get("edu_id")),
            edu=self._as_str(row.get("edu")),
            edu_name=self._as_str(row.get("edu_name")),
            edu_name_eng=self._as_str(row.get("edu_name_eng")),
            edu_code=self._as_int(row.get("edu_code")),
            career1=self._as_str(row.get("career1")),
            career2=self._as_str(row.get("career2")),
            page_count=self._as_int(row.get("page_count") or row.get("pages")),
            has_text=has_text,
            dataset_version=self.corpus.dataset_version(),
            source="krpoltext",
            source_url=dataset_url,
            time_range=row.get("date"),
            availability=AvailabilityState.AVAILABLE if has_text else AvailabilityState.PARTIAL,
            match_method="campaign_booklet_dataset",
            match_confidence=self._as_float(row.get("_match_score")),
            provenance=[
                ProvenanceRecord(
                    source_name="krpoltext",
                    entity_type="text_asset",
                    source_ref=str(row.get("code") or dataset_url),
                    access_method="campaign_booklet_dataset",
                )
            ],
            warnings=[] if has_text else ["The matched campaign_booklet row did not contain text."],
            raw_fields=self._raw_metadata_fields(row),
        )

    def _raw_metadata_fields(self, row: dict[str, Any]) -> dict[str, Any]:
        excluded = {"text", "filtered", "filtered_text", "body", "_match_score"}
        return {
            str(key): value
            for key, value in row.items()
            if key not in excluded and value not in (None, "")
        }

    def _fetch_text(self, source_url: str) -> str | None:
        resolved = resolve_trusted_krpoltext_url(self.settings, source_url)
        if not resolved:
            logger.warning("krpoltext text fetch rejected for untrusted host: %s", source_url)
            return None
        try:
            response = self.session.get(
                resolved,
                headers={"User-Agent": self.settings.user_agent},
                timeout=self.settings.request_timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("krpoltext text fetch failed: %s", exc)
            return None
        final_url = resolve_trusted_krpoltext_url(self.settings, getattr(response, "url", resolved))
        if not final_url:
            logger.warning("krpoltext text fetch redirect resolved outside trusted hosts: %s", source_url)
            return None
        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type:
            try:
                payload = response.json()
            except ValueError:
                return response.text
            if isinstance(payload, dict):
                return payload.get("text") or payload.get("body")
            return response.text
        return response.text

    def _manifest_loader(self) -> dict[str, Any] | None:
        return self._manifest_payload

    @staticmethod
    def _extract_year(value: Any) -> int | None:
        if not value:
            return None
        digits = "".join(character for character in str(value) if character.isdigit())
        if len(digits) >= 4:
            return int(digits[:4])
        return None

    @staticmethod
    def _as_float(value: Any) -> float | None:
        return as_float(value)

    @staticmethod
    def _as_int(value: Any) -> int | None:
        return as_int(value)

    @staticmethod
    def _as_str(value: Any) -> str | None:
        return as_str(value)
