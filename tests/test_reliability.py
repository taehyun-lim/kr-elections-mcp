"""Request classification, section isolation, and fallbacks (report P1)."""
from __future__ import annotations

import pytest

from app.cache import SimpleFileCache
from app.config import NecApiKeyCandidate, Settings
from app.diagnostics import DiagnosticsService
from app.errors import ApiRequestError, ApiTransientError, ResourceUnavailableError
from app.models import (
    AssembleCandidatePacketInput,
    Candidate,
    CandidateRef,
    CandidateResolution,
    ListDistrictsInput,
    ListElectionsInput,
    ListPartiesInput,
    ResolutionStatus,
)
from app.nec_api import NecApiClient
from app.results_api import ResultsApiClient
from app.tool_handlers import ToolHandlers
from tests.fixtures.nec_stub import GoldenNec, NoCache, unauthorized


class StatusResponse:
    def __init__(self, status: int, payload=None, headers=None) -> None:
        self.status_code = status
        self.headers = headers or {}
        self._payload = payload
        self.text = ""

    def raise_for_status(self):
        return None

    def json(self):
        if self._payload is None:
            raise ValueError("no body")
        return self._payload


class ScriptedSession:
    def __init__(self, *responses) -> None:
        self.responses = list(responses)
        self.urls: list[str] = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


OK_PAYLOAD = {"response": {"header": {"resultCode": "00"}, "body": {"items": {"item": [{"sgId": "20240410"}]}}}}


def make_client(session, **settings) -> NecApiClient:
    return NecApiClient(Settings(nec_api_key="test-key", **settings), session=session, cache=NoCache())


def test_transient_5xx_is_retried_then_succeeds(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("app.nec_api.time.sleep", sleeps.append)
    session = ScriptedSession(StatusResponse(503), StatusResponse(200, OK_PAYLOAD))
    rows = make_client(session, retry_attempts=3).fetch_winner_rows(sg_id="20240410", sg_typecode="2")
    assert rows == [{"sgId": "20240410"}]
    assert len(session.urls) == 2
    assert len(sleeps) == 1


def test_retry_after_header_is_honoured(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("app.nec_api.time.sleep", sleeps.append)
    session = ScriptedSession(StatusResponse(429, headers={"Retry-After": "7"}), StatusResponse(200, OK_PAYLOAD))
    make_client(session, retry_attempts=2).fetch_winner_rows(sg_id="20240410", sg_typecode="2")
    assert sleeps == [7.0]


def test_http_404_is_not_retried(monkeypatch):
    monkeypatch.setattr("app.nec_api.time.sleep", lambda seconds: pytest.fail("must not sleep"))
    session = ScriptedSession(StatusResponse(404))
    with pytest.raises(ApiRequestError) as excinfo:
        make_client(session, retry_attempts=3).fetch_winner_rows(sg_id="20240410", sg_typecode="2")
    assert not isinstance(excinfo.value, ApiTransientError)
    assert len(session.urls) == 1


def test_nec_code_99_is_transient(monkeypatch):
    monkeypatch.setattr("app.nec_api.time.sleep", lambda seconds: None)
    payload = {"response": {"header": {"resultCode": "99", "resultMsg": "UNKNOWN"}}}
    session = ScriptedSession(StatusResponse(200, payload))
    with pytest.raises(ApiTransientError):
        make_client(session, retry_attempts=2).fetch_winner_rows(sg_id="20240410", sg_typecode="2")
    assert len(session.urls) == 2


def test_unrecognized_body_is_an_error_not_an_empty_result():
    session = ScriptedSession(StatusResponse(200, {"unexpected": {"shape": True}}))
    with pytest.raises(ApiRequestError):
        make_client(session, retry_attempts=1).fetch_winner_rows(sg_id="20240410", sg_typecode="2")


def test_identical_wire_keys_are_sent_once():
    keys = [NecApiKeyCandidate("abc", "decoded"), NecApiKeyCandidate("abc", "encoded")]
    assert len(NecApiClient._distinct_wire_keys(keys)) == 1
    keys = [NecApiKeyCandidate("a+b", "decoded"), NecApiKeyCandidate("a%2Bb", "encoded")]
    assert len(NecApiClient._distinct_wire_keys(keys)) == 1
    keys = [NecApiKeyCandidate("a+b", "decoded"), NecApiKeyCandidate("a+b", "encoded")]
    assert len(NecApiClient._distinct_wire_keys(keys)) == 2


class PolicyClient(NecApiClient):
    def __init__(self) -> None:
        super().__init__(Settings(nec_api_key="test-key"), cache=NoCache())

    def _fetch_candidate_policy_rows(self, candidate_ref):
        return [
            {
                "cnddtId": "100156011",
                "krName": "윤석열",
                "prmsCnt": "2",
                "prmsOrd1": "1",
                "prmsRealmName1": "경제",
                "prmsTitle1": "Title one",
                "prmmCont1": "Content one",
                "prmsOrd2": "2",
                "prmsRealmName2": "복지",
                "prmsTitle2": "Title two",
                "prmmCont2": "Content two",
                "prmsTitle3": "",
                "prmmCont3": "",
            }
        ]


def test_wide_policy_rows_are_expanded():
    ref = CandidateRef(sg_id="20220309", sg_typecode="1", huboid="100156011", candidate_name="윤석열")
    items, availability = PolicyClient().get_candidate_policies(ref)
    assert availability == "available"
    assert [(item.order_no, item.title, item.content, item.realm) for item in items] == [
        (1, "Title one", "Content one", "경제"),
        (2, "Title two", "Content two", "복지"),
    ]
    assert items[0].policy_id == "100156011:1"


class DuplicateSearchClient(NecApiClient):
    def __init__(self) -> None:
        super().__init__(Settings(nec_api_key="test-key"), cache=NoCache())

    def _fetch_candidate_search_rows(self, **kwargs):
        base = {"sgId": "20220309", "sgTypecode": "1", "huboid": "100156011", "name": "윤석열", "jdName": "국민의힘"}
        return [{**base, "num": "2", "elcoYn": "N"}, {**base, "num": "3", "elcoYn": ""}]


def test_search_results_are_deduplicated_by_candidacy():
    items = DuplicateSearchClient().search_candidates(candidate_name="윤석열")
    assert len(items) == 1
    assert items[0].is_winner is False
    assert items[0].ambiguity_score == 0.0


class InexactSearchClient(NecApiClient):
    def __init__(self) -> None:
        super().__init__(Settings(nec_api_key="test-key"), cache=NoCache())

    def _fetch_candidate_search_rows(self, **kwargs):
        return [{"sgId": "20240410", "sgTypecode": "2", "huboid": "H1", "name": "홍길동이"}]


def test_resolve_candidate_requires_an_exact_name():
    resolution = InexactSearchClient().resolve_candidate(candidate_name="홍길동")
    assert resolution.status == ResolutionStatus.AMBIGUOUS


def test_cache_ttl_zero_bypasses_the_cache(tmp_path):
    cache = SimpleFileCache(tmp_path, default_ttl_seconds=0)
    calls = {"count": 0}

    def producer():
        calls["count"] += 1
        return [1]

    cache.remember("k", producer)
    cache.remember("k", producer)
    assert calls["count"] == 2
    assert not any(tmp_path.glob("*.json"))


def test_cache_prune_leaves_foreign_files_alone(tmp_path):
    foreign = tmp_path / "notes.json"
    foreign.write_text("not json", encoding="utf-8")
    SimpleFileCache(tmp_path).prune()
    assert foreign.exists()


# ---- tool-level fallbacks


class BrokenProfileNec:
    def __init__(self) -> None:
        self.candidate = Candidate(
            candidate_ref=CandidateRef(
                sg_id="20240410",
                sg_typecode="2",
                candidate_name="금태섭",
                sd_name="서울특별시",
                sgg_name="종로구",
            ),
            party_name="개혁신당",
        )

    def resolve_candidate(self, **kwargs):
        return CandidateResolution(status=ResolutionStatus.RESOLVED, candidate=self.candidate, candidates=[self.candidate])

    def get_candidate_profile(self, candidate_ref, include_raw_fields: bool = False):
        raise ResourceUnavailableError("Candidate profile could not be found.")

    def get_candidate_policies(self, candidate_ref):
        raise unauthorized()


class EmptyKrPolText:
    def get_text(self, payload):
        return []


def test_packet_keeps_working_sections_when_others_fail():
    handlers = ToolHandlers(
        nec_client=BrokenProfileNec(),
        results_client=ResultsApiClient(Settings(nec_api_key="test-key"), GoldenNec()),
        krpoltext_client=EmptyKrPolText(),
        diagnostics_service=None,
    )
    packet = handlers.assemble_candidate_packet(AssembleCandidatePacketInput(candidate_name="금태섭"))
    assert packet.result is not None and packet.result.vote_count == 2835
    assert packet.profile is None
    assert any(error.startswith("profile:") for error in packet.errors)
    assert any(error.startswith("policies:") for error in packet.errors)


def build_handlers(nec: GoldenNec) -> ToolHandlers:
    return ToolHandlers(
        nec_client=nec,
        results_client=ResultsApiClient(Settings(nec_api_key="test-key"), nec),
        krpoltext_client=EmptyKrPolText(),
        diagnostics_service=None,
    )


def test_list_tools_fall_back_when_code_api_is_unauthorized():
    nec = GoldenNec(election_error=unauthorized(), code_list_error=unauthorized())
    handlers = build_handlers(nec)

    elections = handlers.list_elections(ListElectionsInput(sg_typecode="2", year_from=2024, year_to=2024))
    assert [item.sg_id for item in elections.items] == ["20240410"]
    assert elections.warnings

    districts = handlers.list_districts(ListDistrictsInput(sg_id="20240410", sg_typecode="2", sd_name="서울"))
    assert [item.sgg_name for item in districts.items] == [
        "종로구", "용산구", "구로구갑", "구로구을", "금천구"
    ]
    assert districts.warnings

    parties = handlers.list_parties(ListPartiesInput(sg_id="20240410", sg_typecode="2"))
    assert "국민의힘" in [party.party_name for party in parties.items]
    assert parties.warnings


def test_diagnostics_probe_result_apis_when_code_api_fails():
    nec = GoldenNec(election_error=unauthorized())
    report = DiagnosticsService(nec, None).diagnose_core_api_access()
    statuses = {check.name: check.status for check in report.checks}
    assert statuses["elections"] == "unauthorized"
    assert statuses["districts"] == "skipped"
    assert statuses["winner_results"] == "ok"
    assert statuses["district_tally"] == "ok"
    assert report.warnings


# ---- cache lifetimes and request budgets (report P2)


def test_ttl_depends_on_election_age():
    from datetime import date

    client = NecApiClient(Settings(nec_api_key="test-key", cache_ttl_seconds=3600), cache=NoCache())
    today = date(2026, 9, 26)
    old = {"sgId": "20240410"}
    assert client._ttl_for("district_tally", old, [{"x": 1}], today=today) == 30 * 24 * 3600
    assert client._ttl_for("district_tally", old, [], today=today) == 3600
    assert client._ttl_for("district_tally", {"sgId": "20260801"}, [], today=today) == 600
    assert client._ttl_for("district_tally", {"sgId": "20260801"}, [{"x": 1}], today=today) == 3600
    assert client._ttl_for("district_tally", {"sgId": "20270303"}, [{"x": 1}], today=today) == 600
    assert client._ttl_for("elections", {}, [{"x": 1}], today=today) == 24 * 3600


def test_district_results_cost_one_tally_and_one_winner_request():
    nec = GoldenNec()
    client = ResultsApiClient(Settings(nec_api_key="test-key"), nec)
    client.get_district_results(sg_id="20240410", sg_typecode="2", sd_name="\uc11c\uc6b8", sgg_name="\uc885\ub85c\uad6c")
    assert dict(nec.calls) == {"district_tally": 1, "winner_results": 1}
    # The alias was sent to NEC as the official province name.
    assert all(params.get("sdName") == "\uc11c\uc6b8\ud2b9\ubcc4\uc2dc" for _, params in nec.params)
