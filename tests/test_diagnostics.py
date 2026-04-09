from __future__ import annotations

from app.diagnostics import DiagnosticsService
from app.models import AvailabilityState, Candidate, CandidatePolicy, CandidateProfile, CandidateRef, ResolutionStatus
from app.normalize import canonicalize_district


class StubDiagnosticsNecClient:
    def __init__(self) -> None:
        self.candidate = Candidate(
            candidate_ref=CandidateRef(
                sg_id="20240410",
                sg_typecode="2",
                huboid="H1",
                candidate_name="홍길동",
                sd_name="서울특별시",
                sgg_name="종로구",
                district_label="서울특별시 종로구",
            ),
            district=canonicalize_district("20240410", "2", "서울특별시", "종로구"),
            party_name="무소속",
        )

    def list_elections(self, **kwargs):
        from app.models import Election

        return [Election(election_uid="20240410:2", sg_id="20240410", sg_typecode="2", sg_name="제22대 국회의원선거", election_date="2024-04-10")]

    def list_districts(self, **kwargs):
        return [canonicalize_district("20240410", "2", "서울특별시", "종로구")]

    def search_candidates(self, **kwargs):
        return [self.candidate]

    def get_candidate_profile(self, candidate_ref, include_raw_fields: bool = False):
        return CandidateProfile(candidate=self.candidate, job="변호사")

    def get_candidate_policies(self, candidate_ref):
        return ([CandidatePolicy(policy_id="P1", candidate_ref=candidate_ref, policy_source="manifesto", title="주거 공약")], AvailabilityState.AVAILABLE)

    def fetch_winner_rows(self, **kwargs):
        return [{"huboNm": "홍길동", "sdName": "서울특별시", "sggName": "종로구"}]

    def fetch_tally_rows(self, **kwargs):
        return [{"huboNm": "홍길동", "dugsu": "12345", "sdName": "서울특별시", "sggName": "종로구"}]


class DummyResultsClient:
    pass


def test_diagnostics_core_report_returns_statuses():
    service = DiagnosticsService(StubDiagnosticsNecClient(), DummyResultsClient())
    report = service.diagnose_core_api_access()
    statuses = {check.name: check.status for check in report.checks}
    assert statuses["elections"] == "ok"
    assert statuses["districts"] == "ok"
    assert statuses["candidate_search"] == "ok"
    assert statuses["candidate_profile"] == "ok"
    assert statuses["candidate_policies"] == "ok"


def test_diagnostics_picks_latest_sample_election():
    items = [
        {"sg_id": "19971218", "sg_typecode": "1", "election_date": "19971218"},
        {"sg_id": "20240410", "sg_typecode": "2", "election_date": "2024-04-10"},
    ]

    sample = DiagnosticsService._pick_sample_election(items)

    assert sample == items[1]


def test_diagnostics_skips_future_elections_for_sampling():
    items = [
        {"sg_id": "20240410", "sg_typecode": "2", "election_date": "2024-04-10"},
        {"sg_id": "20260603", "sg_typecode": "9", "election_date": "20260603"},
    ]

    sample = DiagnosticsService._pick_sample_election(items)

    assert sample == items[0]



class CandidateOnlyDiagnosticsNecClient(StubDiagnosticsNecClient):
    def list_elections(self, **kwargs):
        return []


class EmptyResultsClient:
    pass


def test_diagnostics_candidate_search_runs_without_sample_election():
    service = DiagnosticsService(CandidateOnlyDiagnosticsNecClient(), EmptyResultsClient())

    report = service.diagnose_core_api_access()
    statuses = {check.name: check.status for check in report.checks}

    assert statuses["districts"] == "empty"
    assert statuses["candidate_search"] == "ok"
    assert statuses["candidate_profile"] == "ok"
    assert statuses["candidate_policies"] == "ok"
