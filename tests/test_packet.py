from __future__ import annotations

from app.models import (
    AssembleCandidatePacketInput,
    AvailabilityState,
    Candidate,
    CandidatePolicy,
    CandidateProfile,
    CandidateRef,
    CandidateResolution,
    CandidateResult,
    KrPolTextInput,
    KrPolTextRecord,
    ResolutionStatus,
)
from app.normalize import canonicalize_district
from app.tool_handlers import ToolHandlers


class StubNecClient:
    def __init__(self) -> None:
        district = canonicalize_district("20240410", "2", "서울특별시", "종로구")
        self.candidate = Candidate(
            candidate_ref=CandidateRef(
                sg_id="20240410",
                sg_typecode="2",
                huboid="H1",
                candidate_name="홍길동",
                sd_name="서울특별시",
                sgg_name="종로구",
                district_label=district.district_label,
                party_name="무소속",
                giho="7",
            ),
            district=district,
            party_name="무소속",
            giho="7",
            sg_name="제22대 국회의원선거",
            election_date="2024-04-10",
        )

    def resolve_candidate(self, **kwargs):
        return CandidateResolution(
            status=ResolutionStatus.RESOLVED,
            candidate=self.candidate,
            candidates=[self.candidate],
            message="resolved",
        )

    def get_candidate_profile(self, candidate_ref, include_raw_fields: bool = False):
        return CandidateProfile(candidate=self.candidate, job="변호사")

    def get_candidate_policies(self, candidate_ref):
        return (
            [CandidatePolicy(policy_id="P1", candidate_ref=candidate_ref, policy_source="manifesto", title="교통 공약")],
            AvailabilityState.AVAILABLE,
        )


class StubResultsClient:
    def get_candidate_result(self, candidate):
        return CandidateResult(
            candidate_ref=candidate.candidate_ref,
            candidate_name=candidate.candidate_ref.candidate_name,
            party_name=candidate.party_name,
            district_label=candidate.candidate_ref.district_label,
            vote_count=12345,
            vote_share=51.2,
            result_source="tally_api",
            coverage_scope="all_candidates",
            match_method="huboid+name+district",
            match_confidence=0.95,
        )


class StubKrPolTextClient:
    def get_text(self, payload):
        return [
            KrPolTextRecord(
                record_id="K1",
                candidate_name="홍길동",
                election_year=2024,
                source_url="https://example.test/krpoltext/K1",
                text="정책 텍스트",
                availability="available",
                match_confidence=0.9,
            )
        ]


class EmptyKrPolTextClient:
    def get_text(self, payload):
        return []

    def time_coverage(self):
        return "2000-2022"

    def supported_year_range(self):
        return (2000, 2022)


class StubDiagnostics:
    def diagnose_core_api_access(self):
        raise AssertionError("not used in this test")

    def diagnose_full_api_access(self):
        raise AssertionError("not used in this test")


def test_assemble_candidate_packet_structure():
    handlers = ToolHandlers(
        nec_client=StubNecClient(),
        results_client=StubResultsClient(),
        krpoltext_client=StubKrPolTextClient(),
        diagnostics_service=StubDiagnostics(),
    )
    packet = handlers.assemble_candidate_packet(AssembleCandidatePacketInput(candidate_name="홍길동"))
    assert packet.profile is not None
    assert packet.profile.job == "변호사"
    assert packet.policies[0].title == "교통 공약"
    assert packet.result is not None
    assert packet.result.vote_count == 12345
    assert packet.krpoltext[0].record_id == "K1"


def test_get_krpoltext_text_warns_for_years_outside_corpus_coverage():
    handlers = ToolHandlers(
        nec_client=StubNecClient(),
        results_client=StubResultsClient(),
        krpoltext_client=EmptyKrPolTextClient(),
        diagnostics_service=StubDiagnostics(),
    )

    output = handlers.get_krpoltext_text(KrPolTextInput(candidate_name="홍길동", election_year=2024))

    assert output.items == []
    assert any("2000-2022" in warning and "2024" in warning for warning in output.warnings)
    assert any("search_candidates" in warning for warning in output.warnings)
