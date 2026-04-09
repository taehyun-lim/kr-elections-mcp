from __future__ import annotations

from typing import Any, Callable

from .coerce import as_bool, as_float, as_int, as_str
from .config import Settings
from .models import (
    Candidate,
    CandidateResult,
    CandidateRef,
    District,
    DistrictSummary,
    Election,
    ElectionOverview,
    PartyVoteSharePoint,
    ProvenanceRecord,
)
from .nec_api import NecApiClient
from .normalize import (
    build_district_label,
    canonicalize_district,
    first_of,
    map_party_name,
    score_candidate_match,
    similarity,
)


class ResultsApiClient:
    def __init__(
        self,
        settings: Settings,
        nec_client: NecApiClient,
        *,
        file_result_provider: Callable[[str, str, str | None], list[dict[str, Any]]] | None = None,
    ) -> None:
        self.settings = settings
        self.nec_client = nec_client
        self.file_result_provider = file_result_provider

    def fetch_result_rows(
        self,
        *,
        sg_id: str,
        sg_typecode: str,
        sd_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Collect winner, tally, and optional file-backed result rows for one election scope."""
        rows: list[dict[str, Any]] = []
        for row in self.nec_client.fetch_winner_rows(sg_id=sg_id, sg_typecode=sg_typecode, sd_name=sd_name):
            rows.append({**row, "_result_source": "winner_api", "_coverage_scope": "winner_only"})
        for row in self.nec_client.fetch_tally_rows(sg_id=sg_id, sg_typecode=sg_typecode, sd_name=sd_name):
            rows.append({**row, "_result_source": "tally_api", "_coverage_scope": "all_candidates"})
        if self.file_result_provider:
            for row in self.file_result_provider(sg_id, sg_typecode, sd_name):
                rows.append({**row, "_result_source": "file_data", "_coverage_scope": "all_candidates"})
        return rows

    def get_candidate_result(self, candidate: Candidate) -> CandidateResult | None:
        """Return the best-matching result row for a resolved candidate, if one exists."""
        rows = self.fetch_result_rows(
            sg_id=candidate.candidate_ref.sg_id,
            sg_typecode=candidate.candidate_ref.sg_typecode,
            sd_name=candidate.candidate_ref.sd_name,
        )
        if not rows:
            return None
        scored: list[tuple[float, dict[str, Any], CandidateResult]] = []
        for row in rows:
            match = score_candidate_match(candidate, row, district_label=candidate.candidate_ref.district_label)
            result = self._row_to_result(
                row,
                sg_id=candidate.candidate_ref.sg_id,
                sg_typecode=candidate.candidate_ref.sg_typecode,
                district_label=candidate.candidate_ref.district_label,
                default_sd_name=candidate.candidate_ref.sd_name,
            )
            result.match_method = match.match_method
            result.match_confidence = match.match_confidence
            scored.append((match.match_confidence or 0.0, row, result))
        scored.sort(key=lambda item: item[0], reverse=True)
        return scored[0][2] if scored else None

    def get_district_results(
        self,
        *,
        sg_id: str,
        sg_typecode: str,
        sd_name: str,
        sgg_name: str | None = None,
        wiw_name: str | None = None,
    ) -> tuple[District, list[CandidateResult]]:
        """Return ranked candidate results for one normalized district."""
        district = canonicalize_district(
            sg_id=sg_id,
            sg_typecode=sg_typecode,
            sd_name=sd_name,
            sgg_name=sgg_name,
            wiw_name=wiw_name,
        )
        rows = self.fetch_result_rows(sg_id=sg_id, sg_typecode=sg_typecode, sd_name=sd_name)
        filtered = [row for row in rows if self._row_matches_district(row, district)]
        results = [
            self._row_to_result(
                row,
                sg_id=sg_id,
                sg_typecode=sg_typecode,
                district_label=district.district_label,
                default_sd_name=sd_name,
            )
            for row in filtered
        ]
        results.sort(key=lambda item: (item.vote_count or 0, item.vote_share or 0.0), reverse=True)
        for index, result in enumerate(results, start=1):
            result.rank_in_district = index
            result.match_method = "district"
            result.match_confidence = round(similarity(result.district_label, district.district_label), 3)
        return district, results

    def get_district_summary(
        self,
        *,
        sg_id: str,
        sg_typecode: str,
        sd_name: str,
        sgg_name: str | None = None,
        wiw_name: str | None = None,
    ) -> DistrictSummary:
        """Return turnout and vote summary metrics for one normalized district."""
        election = self.nec_client.get_election(sg_id, sg_typecode)
        district, results = self.get_district_results(
            sg_id=sg_id,
            sg_typecode=sg_typecode,
            sd_name=sd_name,
            sgg_name=sgg_name,
            wiw_name=wiw_name,
        )
        turnout_rows = self.nec_client.fetch_turnout_rows(sg_id=sg_id, sg_typecode=sg_typecode, sd_name=sd_name)
        turnout_row = self._select_district_metric_row(turnout_rows, district)
        tally_rows = self.nec_client.fetch_tally_rows(sg_id=sg_id, sg_typecode=sg_typecode, sd_name=sd_name)
        metric_row = turnout_row or self._select_district_metric_row(tally_rows, district)
        metric_source = "turnout" if turnout_row else ("tally" if metric_row else None)
        valid_vote_count = sum(result.vote_count or 0 for result in results) or self._as_int(
            first_of(metric_row or {}, "validVoteCount", "valid_vote_count", "yutusu")
        )
        electorate_count = self._as_int(first_of(metric_row or {}, "sungeoInwon", "electorate_count", "totSunsu", "sunsu"))
        turnout_count = self._as_int(first_of(metric_row or {}, "tusuInwon", "turnout_count", "totTusu", "tusu"))
        invalid_vote_count = self._as_int(first_of(metric_row or {}, "muhyoTupyoSu", "invalid_vote_count", "mutusu"))
        abstention_count = None
        if electorate_count is not None and turnout_count is not None:
            abstention_count = max(electorate_count - turnout_count, 0)
        turnout_rate = self._as_float(first_of(metric_row or {}, "tupyoYul", "turnout_rate", "turnout", "Turnout"))
        if turnout_rate is None and electorate_count and turnout_count is not None:
            turnout_rate = round((turnout_count / electorate_count) * 100, 3)
        warnings: list[str] = []
        if metric_row is None:
            warnings.append("Turnout row not available; summary partially derived from candidate results.")
        elif metric_source == "tally":
            warnings.append("Turnout rows unavailable; summary turnout derived from tally results.")
        return DistrictSummary(
            election=election,
            district=district,
            candidate_count=len(results),
            electorate_count=electorate_count,
            turnout_count=turnout_count,
            valid_vote_count=valid_vote_count,
            invalid_vote_count=invalid_vote_count,
            abstention_count=abstention_count,
            turnout_rate=turnout_rate,
            result_source=results[0].result_source if results else None,
            coverage_scope=results[0].coverage_scope if results else None,
            provenance=[self._provenance("nec_results", "district_summary", district.district_uid)],
            warnings=warnings,
        )

    def get_party_vote_share_history(
        self,
        *,
        party_name: str,
        district_name: str,
        sd_name: str | None = None,
        sg_typecode: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[PartyVoteSharePoint]:
        """Return matched district-level vote share points for a party across elections."""
        canonical_party = map_party_name(party_name)
        elections = self.nec_client.list_elections(
            sg_typecode=sg_typecode,
            year_from=year_from,
            year_to=year_to,
            include_history=True,
        )
        history: list[PartyVoteSharePoint] = []
        for election in elections:
            district = self._find_best_district(
                self.nec_client.list_districts(
                    sg_id=election.sg_id,
                    sg_typecode=election.sg_typecode,
                    sd_name=sd_name,
                ),
                district_name,
            )
            if not district:
                continue
            _, results = self.get_district_results(
                sg_id=election.sg_id,
                sg_typecode=election.sg_typecode,
                sd_name=district.sd_name or district_name,
                sgg_name=district.sgg_name,
                wiw_name=district.wiw_name,
            )
            for result in results:
                if map_party_name(result.party_name) != canonical_party:
                    continue
                history.append(
                    PartyVoteSharePoint(
                        election=election,
                        district_label=result.district_label,
                        party_name=result.party_name or party_name,
                        vote_count=result.vote_count,
                        vote_share=result.vote_share,
                        result_source=result.result_source,
                        match_method=result.match_method,
                        match_confidence=result.match_confidence,
                        provenance=result.provenance,
                    )
                )
        history.sort(key=lambda point: point.election.election_date or "")
        return history

    def get_election_overview(self, *, sg_id: str, sg_typecode: str) -> ElectionOverview:
        """Return election-wide district, party, winner, and turnout aggregates."""
        election = self.nec_client.get_election(sg_id, sg_typecode) or Election(
            election_uid=f"{sg_id}:{sg_typecode}",
            sg_id=sg_id,
            sg_typecode=sg_typecode,
        )
        districts = self.nec_client.list_districts(sg_id=sg_id, sg_typecode=sg_typecode)
        parties = self.nec_client.list_parties(sg_id=sg_id, sg_typecode=sg_typecode)
        winner_rows = self.nec_client.fetch_winner_rows(sg_id=sg_id, sg_typecode=sg_typecode)
        winners = [
            self._row_to_result(
                {**row, "_result_source": "winner_api", "_coverage_scope": "winner_only"},
                sg_id=sg_id,
                sg_typecode=sg_typecode,
                district_label=build_district_label(
                    first_of(row, "sdName", "sd_name"),
                    first_of(row, "sggName", "sgg_name"),
                    first_of(row, "wiwName", "wiw_name"),
                ),
                default_sd_name=first_of(row, "sdName", "sd_name"),
            )
            for row in winner_rows
        ]
        turnout_rows = self.nec_client.fetch_turnout_rows(sg_id=sg_id, sg_typecode=sg_typecode)
        tally_rows = self.nec_client.fetch_tally_rows(sg_id=sg_id, sg_typecode=sg_typecode)
        turnout_aggregate = self._select_aggregate_metric_row(turnout_rows)
        metric_row = turnout_aggregate or self._select_aggregate_metric_row(tally_rows)
        metric_source = "turnout" if turnout_aggregate else ("tally" if metric_row else None)
        electorate_total = self._as_int(first_of(metric_row or {}, "sungeoInwon", "electorate_count", "totSunsu", "sunsu"))
        turnout_total = self._as_int(first_of(metric_row or {}, "tusuInwon", "turnout_count", "totTusu", "tusu"))
        turnout_rate = self._as_float(first_of(metric_row or {}, "tupyoYul", "turnout_rate", "turnout", "Turnout"))
        if turnout_rate is None and electorate_total and turnout_total is not None:
            turnout_rate = round((turnout_total / electorate_total) * 100, 3)
        warnings: list[str] = []
        if metric_row is None:
            warnings.append("Turnout rows unavailable for election overview.")
        elif metric_source == "tally":
            warnings.append("Turnout rows unavailable; overview turnout derived from tally results.")
        return ElectionOverview(
            election=election,
            district_count=len(districts),
            party_count=len(parties),
            winner_count=len(winners),
            electorate_count=electorate_total,
            turnout_count=turnout_total,
            turnout_rate=turnout_rate,
            winners=winners,
            districts=districts,
            parties=parties,
            provenance=[self._provenance("nec_results", "election_overview", election.election_uid)],
            warnings=warnings,
        )

    @staticmethod
    def _select_district_metric_row(rows: list[dict[str, Any]], district: District) -> dict[str, Any] | None:
        return next((row for row in rows if ResultsApiClient._row_matches_district(row, district)), None)

    @staticmethod
    def _select_aggregate_metric_row(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not rows:
            return None
        for row in rows:
            sd_name = as_str(first_of(row, "sdName", "sd_name"))
            sgg_name = as_str(first_of(row, "sggName", "sgg_name"))
            wiw_name = as_str(first_of(row, "wiwName", "wiw_name"))
            if (
                sd_name in {"합계", "전국", "??"}
                and (sgg_name in {None, "", "합계", "비례대표", "??", "????"})
                and (wiw_name in {None, "", "합계", "??"})
            ):
                return row
        for row in rows:
            sd_name = as_str(first_of(row, "sdName", "sd_name"))
            wiw_name = as_str(first_of(row, "wiwName", "wiw_name"))
            if sd_name in {"합계", "전국", "??"} and wiw_name in {None, "", "합계", "??"}:
                return row
        return rows[0]

    def _row_to_result(
        self,
        row: dict[str, Any],
        *,
        sg_id: str,
        sg_typecode: str,
        district_label: str | None,
        default_sd_name: str | None,
    ) -> CandidateResult:
        candidate_name = self._as_str(first_of(row, "huboNm", "candidate_name", "name"))
        party_name = self._as_str(first_of(row, "jdName", "party_name", "partyNm"))
        ref = CandidateRef(
            candidacy_uid=f"{sg_id}:{sg_typecode}:{self._as_str(first_of(row, 'huboid', 'huboId')) or candidate_name}",
            huboid=self._as_str(first_of(row, "huboid", "huboId")),
            sg_id=sg_id,
            sg_typecode=sg_typecode,
            candidate_name=candidate_name,
            sd_name=self._as_str(first_of(row, "sdName", "sd_name")) or default_sd_name,
            sgg_name=self._as_str(first_of(row, "sggName", "sgg_name")),
            wiw_name=self._as_str(first_of(row, "wiwName", "wiw_name")),
            district_label=district_label or build_district_label(
                self._as_str(first_of(row, "sdName", "sd_name")) or default_sd_name,
                self._as_str(first_of(row, "sggName", "sgg_name")),
                self._as_str(first_of(row, "wiwName", "wiw_name")),
            ),
            party_name=party_name,
            giho=self._as_str(first_of(row, "giho", "num")),
        )
        return CandidateResult(
            candidate_ref=ref,
            candidate_name=candidate_name,
            party_name=party_name,
            giho=self._as_str(first_of(row, "giho", "num")),
            district_label=ref.district_label,
            vote_count=self._as_int(first_of(row, "dugsu", "voteCount", "vote_count")),
            vote_share=self._as_float(first_of(row, "dugyul", "voteShare", "vote_share")),
            is_winner=self._as_bool(first_of(row, "winnerYn", "is_winner", "dangseonYn", "elcoYn")),
            result_source=row.get("_result_source", "tally_api"),
            coverage_scope=row.get("_coverage_scope", "all_candidates"),
            provenance=[self._provenance("nec_results", "candidate_result", ref.candidacy_uid)],
            raw_fields=row,
        )

    @staticmethod
    def _row_matches_district(row: dict[str, Any], district: District) -> bool:
        row_label = build_district_label(
            first_of(row, "sdName", "sd_name"),
            first_of(row, "sggName", "sgg_name"),
            first_of(row, "wiwName", "wiw_name"),
        )
        return similarity(row_label, district.district_label) >= 0.65

    @staticmethod
    def _find_best_district(districts: list[District], district_name: str) -> District | None:
        if not districts:
            return None
        scored = sorted(districts, key=lambda item: similarity(item.district_label, district_name), reverse=True)
        return scored[0] if scored and similarity(scored[0].district_label, district_name) >= 0.65 else None

    @staticmethod
    def _as_bool(value: Any) -> bool | None:
        return as_bool(value)

    @staticmethod
    def _as_int(value: Any) -> int | None:
        return as_int(value)

    @staticmethod
    def _as_float(value: Any) -> float | None:
        return as_float(value)

    @staticmethod
    def _as_str(value: Any) -> str | None:
        return as_str(value)

    @staticmethod
    def _provenance(source_name: str, entity_type: str, source_ref: str | None) -> ProvenanceRecord:
        return ProvenanceRecord(
            source_name=source_name,
            entity_type=entity_type,
            source_ref=source_ref,
            access_method="api",
        )


