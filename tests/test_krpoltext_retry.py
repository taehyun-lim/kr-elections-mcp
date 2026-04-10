from app.models import (
    Candidate,
    CandidateRef,
    CandidateResolution,
    Election,
    KrPolTextInput,
    KrPolTextMetaRecord,
    KrPolTextRecord,
    ResolutionStatus,
)
from app.normalize import canonicalize_district
from app.tool_handlers import ToolHandlers


class StubNecClient:
    def __init__(self, candidate: Candidate) -> None:
        self.candidate = candidate
        self.resolve_calls: list[dict[str, object]] = []

    def list_elections(self, *, sg_typecode=None, year_from=None, year_to=None, include_history=True):
        if sg_typecode == "2" and year_from == 2020 and year_to == 2020:
            return [
                Election(
                    election_uid="20200415:2",
                    sg_id="20200415",
                    sg_typecode="2",
                    sg_name="national_assembly",
                    election_date="2020-04-15",
                )
            ]
        return []

    def resolve_candidate(self, **kwargs):
        self.resolve_calls.append(kwargs)
        return CandidateResolution(
            status=ResolutionStatus.RESOLVED,
            candidate=self.candidate,
            candidates=[self.candidate],
            message="resolved",
        )


class RecordingKrPolTextClient:
    def __init__(self, candidate: Candidate) -> None:
        self.candidate = candidate
        self.text_calls: list[KrPolTextInput] = []
        self.meta_calls: list[KrPolTextInput] = []

    def get_text(self, payload: KrPolTextInput):
        self.text_calls.append(payload)
        if payload.district_name != self.candidate.candidate_ref.district_label:
            return []
        return [
            KrPolTextRecord(
                record_id="K1",
                code="ECM0120200001_5066S",
                candidate_name=self.candidate.candidate_ref.candidate_name,
                office_name="national_assembly",
                election_year=2020,
                district_name=payload.district_name,
                party_name=self.candidate.party_name,
                text="booklet text",
                match_confidence=1.0,
                availability="available",
            )
        ]

    def get_metadata(self, payload: KrPolTextInput):
        self.meta_calls.append(payload)
        if payload.district_name != self.candidate.candidate_ref.district_label:
            return []
        return [
            KrPolTextMetaRecord(
                record_id="K1",
                code="ECM0120200001_5066S",
                candidate_name=self.candidate.candidate_ref.candidate_name,
                office_name="national_assembly",
                election_year=2020,
                district_name=payload.district_name,
                party_name=self.candidate.party_name,
                has_text=True,
                match_confidence=1.0,
                availability="available",
            )
        ]

    def time_coverage(self):
        return "2000-2022"

    def supported_year_range(self):
        return (2000, 2022)


class StubResultsClient:
    pass


class StubDiagnostics:
    def diagnose_core_api_access(self):
        raise AssertionError("not used in this test")

    def diagnose_full_api_access(self):
        raise AssertionError("not used in this test")


def make_candidate() -> Candidate:
    district = canonicalize_district("20200415", "2", "Gyeonggi", "UiwangGwacheon", "Uiwang")
    return Candidate(
        candidate_ref=CandidateRef(
            sg_id="20200415",
            sg_typecode="2",
            huboid="100137284",
            candidate_name="Lee Soyoung",
            sd_name="Gyeonggi",
            sgg_name="UiwangGwacheon",
            wiw_name="Uiwang",
            district_label=district.district_label,
            party_name="Democratic Party of Korea",
            giho="1",
        ),
        district=district,
        party_name="Democratic Party of Korea",
        giho="1",
        sg_name="national_assembly",
        election_date="2020-04-15",
    )


def test_get_krpoltext_text_retries_with_resolved_candidate_context():
    candidate = make_candidate()
    nec_client = StubNecClient(candidate)
    krpoltext_client = RecordingKrPolTextClient(candidate)
    handlers = ToolHandlers(
        nec_client=nec_client,
        results_client=StubResultsClient(),
        krpoltext_client=krpoltext_client,
        diagnostics_service=StubDiagnostics(),
    )

    output = handlers.get_krpoltext_text(
        KrPolTextInput(
            candidate_name="Lee Soyoung",
            election_year=2020,
            office_name="national_assembly",
            district_name="UiwangGwacheon",
            party_name="Democratic Party of Korea",
            limit=3,
        )
    )

    assert len(output.items) == 1
    assert output.items[0].code == "ECM0120200001_5066S"
    assert output.warnings == []
    assert len(krpoltext_client.text_calls) == 2
    assert krpoltext_client.text_calls[0].district_name == "UiwangGwacheon"
    assert krpoltext_client.text_calls[1].district_name == candidate.candidate_ref.district_label
    assert nec_client.resolve_calls[0]["sg_id"] == "20200415"
    assert nec_client.resolve_calls[0]["sg_typecode"] == "2"


def test_get_krpoltext_meta_retries_with_resolved_candidate_context():
    candidate = make_candidate()
    nec_client = StubNecClient(candidate)
    krpoltext_client = RecordingKrPolTextClient(candidate)
    handlers = ToolHandlers(
        nec_client=nec_client,
        results_client=StubResultsClient(),
        krpoltext_client=krpoltext_client,
        diagnostics_service=StubDiagnostics(),
    )

    output = handlers.get_krpoltext_meta(
        KrPolTextInput(
            candidate_name="Lee Soyoung",
            election_year=2020,
            office_name="national_assembly",
            district_name="UiwangGwacheon",
            party_name="Democratic Party of Korea",
            limit=3,
        )
    )

    assert len(output.items) == 1
    assert output.items[0].code == "ECM0120200001_5066S"
    assert output.warnings == []
    assert len(krpoltext_client.meta_calls) == 2
    assert krpoltext_client.meta_calls[0].district_name == "UiwangGwacheon"
    assert krpoltext_client.meta_calls[1].district_name == candidate.candidate_ref.district_label
    assert nec_client.resolve_calls[0]["sg_id"] == "20200415"
    assert nec_client.resolve_calls[0]["sg_typecode"] == "2"
