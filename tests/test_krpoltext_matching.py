from app.models import (
    Candidate,
    CandidateProfile,
    CandidateRef,
    CandidateResolution,
    KrPolTextCandidateMatchInput,
    KrPolTextMetaRecord,
    ResolutionStatus,
)
from app.normalize import canonicalize_district
from app.tool_handlers import ToolHandlers


class StubNecClient:
    def __init__(self, candidate: Candidate, profile: CandidateProfile) -> None:
        self.candidate = candidate
        self.profile = profile

    def resolve_candidate(self, **_: object) -> CandidateResolution:
        return CandidateResolution(
            status=ResolutionStatus.RESOLVED,
            candidate=self.candidate,
            candidates=[self.candidate],
            message="resolved",
        )

    def get_candidate_profile(self, candidate_ref: CandidateRef):
        assert candidate_ref.huboid == self.candidate.candidate_ref.huboid
        return self.profile


class StubKrPolTextClient:
    def __init__(self, items: list[KrPolTextMetaRecord]) -> None:
        self.items = items

    def get_metadata(self, payload):
        return self.items[: payload.limit]

    def get_text(self, payload):
        return []

    def time_coverage(self):
        return "2000-2024"

    def supported_year_range(self):
        return (2000, 2024)


class StubResultsClient:
    pass


class StubDiagnostics:
    def diagnose_core_api_access(self):
        raise AssertionError("not used in this test")

    def diagnose_full_api_access(self):
        raise AssertionError("not used in this test")


def make_candidate() -> tuple[Candidate, CandidateProfile]:
    district = canonicalize_district("20240410", "2", "Seoul", "Jongno")
    candidate = Candidate(
        candidate_ref=CandidateRef(
            sg_id="20240410",
            sg_typecode="2",
            huboid="H1",
            candidate_name="Alice Kim",
            sd_name="Seoul",
            sgg_name="Jongno",
            district_label=district.district_label,
            party_name="Independent",
            giho="7",
        ),
        district=district,
        party_name="Independent",
        giho="7",
        sg_name="national_assembly",
        election_date="2024-04-10",
    )
    profile = CandidateProfile(
        candidate=candidate,
        birthday="1970-01-02",
        age=54,
        job="Lawyer",
        education="Seoul National University",
        career1="Former lawmaker",
        career2="Attorney",
    )
    return candidate, profile


def test_match_krpoltext_candidate_resolves_with_strong_personal_identifiers():
    candidate, profile = make_candidate()
    handlers = ToolHandlers(
        nec_client=StubNecClient(candidate, profile),
        results_client=StubResultsClient(),
        krpoltext_client=StubKrPolTextClient(
            [
                KrPolTextMetaRecord(
                    record_id="K1",
                    code="ECM0120240001_0007S",
                    candidate_name="Alice Kim",
                    office_id=2,
                    office_name="national_assembly",
                    election_year=2024,
                    district_name="Seoul Jongno",
                    district_raw="Jongno",
                    party_name="Independent",
                    giho="7",
                    birthday="1970.01.02",
                    age=54,
                    edu="Seoul National University",
                    career1="Former lawmaker",
                    career2="Attorney",
                ),
                KrPolTextMetaRecord(
                    record_id="K2",
                    code="ECM0120240001_0008S",
                    candidate_name="Alice Kim",
                    office_id=2,
                    office_name="national_assembly",
                    election_year=2024,
                    district_name="Seoul Jongno",
                    district_raw="Jongno",
                    party_name="Independent",
                    giho="8",
                    birthday="1968-01-02",
                    age=56,
                    edu="Other University",
                    career1="Teacher",
                ),
            ]
        ),
        diagnostics_service=StubDiagnostics(),
    )

    output = handlers.match_krpoltext_candidate(
        KrPolTextCandidateMatchInput(candidate_name="Alice Kim", sg_id="20240410", sg_typecode="2", limit=5)
    )

    assert output.status == ResolutionStatus.RESOLVED
    assert output.item is not None
    assert output.item.code == "ECM0120240001_0007S"
    assert "birthday" in (output.item.match_method or "")


def test_match_krpoltext_candidate_keeps_same_name_independent_collision_ambiguous():
    candidate, profile = make_candidate()
    handlers = ToolHandlers(
        nec_client=StubNecClient(candidate, profile),
        results_client=StubResultsClient(),
        krpoltext_client=StubKrPolTextClient(
            [
                KrPolTextMetaRecord(
                    record_id="K1",
                    code="ECM0120240001_0007S",
                    candidate_name="Alice Kim",
                    office_id=2,
                    office_name="national_assembly",
                    election_year=2024,
                    district_name="Seoul Jongno",
                    district_raw="Jongno",
                    party_name="Independent",
                ),
                KrPolTextMetaRecord(
                    record_id="K2",
                    code="ECM0120240001_0008S",
                    candidate_name="Alice Kim",
                    office_id=2,
                    office_name="national_assembly",
                    election_year=2024,
                    district_name="Seoul Jongno",
                    district_raw="Jongno",
                    party_name="Independent",
                ),
            ]
        ),
        diagnostics_service=StubDiagnostics(),
    )

    output = handlers.match_krpoltext_candidate(
        KrPolTextCandidateMatchInput(candidate_name="Alice Kim", sg_id="20240410", sg_typecode="2", limit=5)
    )

    assert output.status == ResolutionStatus.AMBIGUOUS
    assert output.item is None
    assert len(output.items) == 2
    assert any("ambiguous" in warning.lower() or "plausible" in warning.lower() for warning in output.warnings)
