from __future__ import annotations

from urllib.parse import unquote

import requests

from app.config import Settings
from app.models import AvailabilityState, CandidateRef
from app.nec_api import NecApiClient


class StubNecApiClient(NecApiClient):
    def __init__(self) -> None:
        super().__init__(Settings(nec_api_key="test-key"))
        self.search_rows = [
            {
                "sgId": "20240410",
                "sgTypecode": "2",
                "huboid": "H1",
                "huboNm": "Kim Candidate",
                "jdName": "Independent",
                "sdName": "Seoul",
                "sggName": "Jongno",
                "giho": "7",
                "sgName": "National Assembly Election",
                "sgVotedate": "2024-04-10",
            },
            {
                "sgId": "20240410",
                "sgTypecode": "2",
                "huboid": "H2",
                "huboNm": "Kim Candidate",
                "jdName": "Future Party",
                "sdName": "Seoul",
                "sggName": "Jung",
                "giho": "2",
                "sgName": "National Assembly Election",
                "sgVotedate": "2024-04-10",
            },
        ]
        self.profile_rows = {
            "H1": {
                **self.search_rows[0],
                "birthday": "1975-01-01",
                "age": "49",
                "gender": "M",
                "job": "Lawyer",
                "education": "Seoul National University, Law",
                "career1": "Former prosecutor",
                "career2": "Parliamentary aide",
                "address": "Seoul Jongno",
                "statusName": "Registered",
            },
            "H2": {
                **self.search_rows[1],
                "birthday": "1980-02-02",
                "job": "Professor",
            },
        }
        self.policy_rows = {
            "H1": [
                {
                    "policyId": "P1",
                    "policy_source": "manifesto",
                    "title": "Transit Improvement",
                    "content": "Expand transit options in Jongno.",
                    "budget": "National and city funds",
                    "orderNo": "1",
                }
            ],
            "H2": [],
        }

    def _fetch_election_rows(self, *, include_history: bool = True):
        return [{"sgId": "20240410", "sgTypecode": "2", "sgName": "National Assembly Election", "sgVotedate": "2024-04-10"}]

    def _fetch_district_rows(self, *, sg_id: str, sg_typecode: str, sd_name: str | None = None):
        return [
            {"sdName": "Seoul", "sggName": "Jongno"},
            {"sdName": "Seoul", "sggName": "Jung"},
        ]

    def _fetch_party_rows(self, *, sg_id: str, sg_typecode: str):
        return [{"jdCode": "001", "jdName": "Independent"}, {"jdCode": "002", "jdName": "Future Party"}]

    def _fetch_candidate_search_rows(self, *, candidate_name: str, sg_id: str | None = None, sg_typecode: str | None = None, sd_name: str | None = None):
        return self.search_rows

    def _fetch_candidate_profile_row(self, candidate_ref: CandidateRef):
        return self.profile_rows.get(candidate_ref.huboid)

    def _fetch_candidate_policy_rows(self, candidate_ref: CandidateRef):
        return self.policy_rows.get(candidate_ref.huboid, [])


def test_search_candidates_success():
    client = StubNecApiClient()
    items = client.search_candidates(
        candidate_name="Kim Candidate",
        sg_id="20240410",
        sg_typecode="2",
        district_name="Seoul Jongno",
    )
    assert len(items) == 1
    assert items[0].candidate_ref.huboid == "H1"


def test_search_candidates_ambiguity():
    client = StubNecApiClient()
    items = client.search_candidates(candidate_name="Kim Candidate", sg_id="20240410", sg_typecode="2")
    assert len(items) == 2
    assert all(item.ambiguity_score == 1.0 for item in items)


def test_candidate_profile_normalization():
    client = StubNecApiClient()
    ref = CandidateRef(sg_id="20240410", sg_typecode="2", huboid="H1")
    profile = client.get_candidate_profile(ref, include_raw_fields=True)
    assert profile.job == "Lawyer"
    assert profile.age == 49
    assert profile.candidate.candidate_ref.district_label == "Seoul Jongno"
    assert profile.extra_json["statusName"] == "Registered"


def test_candidate_policies_presence_and_absence():
    client = StubNecApiClient()
    ref_present = CandidateRef(sg_id="20240410", sg_typecode="2", huboid="H1")
    items, availability = client.get_candidate_policies(ref_present)
    assert availability == AvailabilityState.AVAILABLE
    assert len(items) == 1
    assert items[0].title == "Transit Improvement"

    ref_absent = CandidateRef(sg_id="20240410", sg_typecode="2", huboid="H2")
    missing_items, missing_availability = client.get_candidate_policies(ref_absent)
    assert missing_items == []
    assert missing_availability == AvailabilityState.UNAVAILABLE


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class RecordingSession:
    def __init__(self):
        self.urls: list[str] = []

    def get(self, url: str, **kwargs):
        self.urls.append(url)
        if "serviceKey=decoded-key" in url:
            return FakeResponse({"response": {"header": {"resultCode": "30"}}})
        if "serviceKey=encoded%2Bkey" in url:
            return FakeResponse(
                {
                    "response": {
                        "header": {"resultCode": "00"},
                        "body": {"items": {"item": [{"sgId": "20240410", "sgTypecode": "2"}]}},
                    }
                }
            )
        raise requests.HTTPError(f"unexpected url {url}")


class NoCache:
    def remember(self, key, fn, ttl_seconds=None):
        return fn()


def test_request_falls_back_to_second_key_format():
    session = RecordingSession()
    client = NecApiClient(
        Settings(
            nec_api_key_encoded="encoded%2Bkey",
            nec_api_key_decoded="decoded-key",
            retry_attempts=1,
        ),
        session=session,
        cache=NoCache(),
    )

    rows = client.fetch_winner_rows(sg_id="20240410", sg_typecode="2")

    assert rows == [{"sgId": "20240410", "sgTypecode": "2"}]
    assert "serviceKey=decoded-key" in session.urls[0]
    assert "serviceKey=encoded%2Bkey" in session.urls[1]


class XmlResponse:
    text = "<response><header><resultCode>00</resultCode></header><body><items><item><sgId>20240410</sgId><sgTypecode>2</sgTypecode></item></items></body></response>"

    def raise_for_status(self):
        return None

    def json(self):
        raise ValueError("XML only")


class XmlRecordingSession:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def get(self, url: str, **kwargs):
        self.urls.append(url)
        return XmlResponse()


def test_request_prefers_configured_result_format():
    session = XmlRecordingSession()
    client = NecApiClient(
        Settings(
            nec_api_key="test-key",
            nec_result_format="xml",
            retry_attempts=1,
        ),
        session=session,
        cache=NoCache(),
    )

    rows = client.fetch_winner_rows(sg_id="20240410", sg_typecode="2")

    assert rows == [{"sgId": "20240410", "sgTypecode": "2"}]
    assert "resultType=xml" in session.urls[0]


def test_legacy_encoded_key_is_derived_for_request_candidates():
    settings = Settings(nec_api_key="abc%2B123")

    candidates = settings.api_key_candidates()

    assert candidates[0].key_format == "decoded"
    assert candidates[0].value == unquote("abc%2B123")
    assert candidates[1].key_format == "encoded"
    assert candidates[1].value == "abc%2B123"


def test_unwrap_rows_handles_operation_root_payload():
    client = NecApiClient(Settings(nec_api_key="test-key"))

    rows = client._unwrap_rows(
        {
            "getCommonSgCodeList": {
                "numOfRows": 10,
                "pageNo": 1,
                "totalCount": 1,
                "resultCode": "INFO-00",
                "resultMsg": "NORMAL SERVICE.",
                "item": [{"sgId": "20240410", "sgTypecode": "2"}],
            }
        }
    )

    assert rows == [{"sgId": "20240410", "sgTypecode": "2"}]


class CandidateProfileRetryClient(NecApiClient):
    def __init__(self) -> None:
        super().__init__(Settings(nec_api_key="test-key"))
        self.scope_calls: list[tuple[str | None, str | None]] = []
        self.search_rows = [
            {
                "sgId": "20240410",
                "sgTypecode": "2",
                "huboid": "H1",
                "huboNm": "Kim Candidate",
                "jdName": "Independent",
                "sdName": "Seoul",
                "sggName": "Jongno",
                "giho": "7",
                "sgName": "National Assembly Election",
                "sgVotedate": "2024-04-10",
            }
        ]

    def _fetch_candidate_scope_rows(
        self,
        *,
        sg_id: str,
        sg_typecode: str,
        sd_name: str | None = None,
        sgg_name: str | None = None,
    ):
        self.scope_calls.append((sd_name, sgg_name))
        if sd_name or sgg_name:
            return []
        return [self.search_rows[0]]


def test_candidate_profile_row_retries_without_district_filters():
    client = CandidateProfileRetryClient()

    row = client._fetch_candidate_profile_row(
        CandidateRef(
            sg_id="20240410",
            sg_typecode="2",
            huboid="H1",
            sd_name="Seoul",
            sgg_name="Jongno",
        )
    )

    assert row == client.search_rows[0]
    assert client.scope_calls == [("Seoul", "Jongno"), (None, None)]


class PaginatedElectionClient(NecApiClient):
    def __init__(self) -> None:
        super().__init__(Settings(nec_api_key="test-key"))
        self.calls: list[tuple[int, int]] = []

    def _request_rows(self, service_key: str, params: dict[str, object]) -> list[dict[str, object]]:
        assert service_key == "elections"
        page_no = int(params["pageNo"])
        page_size = int(params["numOfRows"])
        self.calls.append((page_no, page_size))
        if page_no == 1:
            return [{"sgId": f"P1-{index}", "sgTypecode": "1"} for index in range(page_size)]
        if page_no == 2:
            return [{"sgId": "P2-0", "sgTypecode": "1"}]
        return []


def test_fetch_election_rows_paginates_until_last_page():
    client = PaginatedElectionClient()

    rows = client._fetch_election_rows()

    assert len(rows) == 101
    assert rows[0]["sgId"] == "P1-0"
    assert rows[-1]["sgId"] == "P2-0"
    assert client.calls == [(1, 100), (2, 100)]


class ElectionHistoryFilterClient(NecApiClient):
    def __init__(self) -> None:
        super().__init__(Settings(nec_api_key="test-key"))

    def _request_paginated_rows(
        self,
        service_key: str,
        params: dict[str, object],
        *,
        page_size: int = 100,
        max_pages: int = 100,
    ) -> list[dict[str, object]]:
        assert service_key == "elections"
        return [
            {"sgId": "20220309", "sgTypecode": "1", "sgVotedate": "2022-03-09"},
            {"sgId": "20250603", "sgTypecode": "1", "sgVotedate": "2025-06-03"},
            {"sgId": "20220415", "sgTypecode": "2", "sgVotedate": "2022-04-15"},
            {"sgId": "20240410", "sgTypecode": "2", "sgVotedate": "2024-04-10"},
        ]


def test_fetch_election_rows_can_exclude_history():
    client = ElectionHistoryFilterClient()

    rows = client._fetch_election_rows(include_history=False)

    assert [row["sgId"] for row in rows] == ["20250603", "20240410"]


class CandidateSearchFallbackClient(NecApiClient):
    def __init__(self) -> None:
        super().__init__(Settings(nec_api_key="test-key"))

    def _fetch_candidate_scope_rows(
        self,
        *,
        sg_id: str,
        sg_typecode: str,
        sd_name: str | None = None,
        sgg_name: str | None = None,
    ):
        return []

    def _fetch_election_rows(self, *, include_history: bool = True):
        return []

    def fetch_winner_rows(self, *, sg_id: str, sg_typecode: str, sd_name: str | None = None):
        return []

    def fetch_tally_rows(self, *, sg_id: str, sg_typecode: str, sd_name: str | None = None):
        return []

    def _request_rows(self, service_key: str, params: dict[str, object]):
        if service_key == "candidate_search_name":
            return [{"sgId": "20220309", "sgTypecode": "1", "huboid": "100138362", "name": "Search Candidate"}]
        raise AssertionError(service_key)


def test_fetch_candidate_search_rows_falls_back_to_name_search():
    client = CandidateSearchFallbackClient()

    rows = client._fetch_candidate_search_rows(
        candidate_name="Search Candidate",
        sg_id="20240410",
        sg_typecode="2",
        sd_name="Seoul",
    )

    assert rows == [{"sgId": "20220309", "sgTypecode": "1", "huboid": "100138362", "name": "Search Candidate"}]


class CandidateProfileNameFallbackClient(NecApiClient):
    def __init__(self) -> None:
        super().__init__(Settings(nec_api_key="test-key"))

    def _fetch_candidate_scope_rows(
        self,
        *,
        sg_id: str,
        sg_typecode: str,
        sd_name: str | None = None,
        sgg_name: str | None = None,
    ):
        return []

    def _request_rows(self, service_key: str, params: dict[str, object]):
        if service_key == "candidate_search_name":
            return [
                {
                    "sgId": "20220309",
                    "sgTypecode": "1",
                    "huboid": "100138362",
                    "name": "Search Candidate",
                    "elctNm": "2022 Presidential Election",
                    "jdName": "Democratic Party",
                    "elcoYn": "Y",
                }
            ]
        raise AssertionError(service_key)


def test_fetch_candidate_profile_row_falls_back_to_name_search():
    client = CandidateProfileNameFallbackClient()

    row = client._fetch_candidate_profile_row(
        CandidateRef(
            sg_id="20220309",
            sg_typecode="1",
            huboid="100138362",
            candidate_name="Search Candidate",
        )
    )

    assert row is not None
    assert row["huboid"] == "100138362"


def test_candidate_from_row_maps_integrated_search_fields():
    client = NecApiClient(Settings(nec_api_key="test-key"))

    candidate = client._candidate_from_row(
        {
            "sgId": "20220309",
            "sgTypecode": "1",
            "elctNm": "2022 Presidential Election",
            "huboid": "100138362",
            "sggName": "Seoul",
            "sdName": "Seoul",
            "jdName": "Democratic Party",
            "name": "Search Candidate",
            "elcoYn": "Y",
        }
    )

    assert candidate.sg_name == "2022 Presidential Election"
    assert candidate.election_date == "20220309"
    assert candidate.is_winner is True


class CandidateResultSlotFallbackClient(NecApiClient):
    def __init__(self) -> None:
        super().__init__(Settings(nec_api_key="test-key"))

    def _fetch_election_rows(self, *, include_history: bool = True):
        return [{"sgId": "20220309", "sgTypecode": "1", "sgName": "Presidential Election", "sgVotedate": "2022-03-09"}]

    def _fetch_candidate_scope_rows(
        self,
        *,
        sg_id: str,
        sg_typecode: str,
        sd_name: str | None = None,
        sgg_name: str | None = None,
    ):
        return []

    def _request_rows(self, service_key: str, params: dict[str, object]):
        if service_key == "candidate_search_name":
            return [{"sgId": "20250603", "sgTypecode": "1", "name": "Target Candidate"}]
        raise AssertionError(service_key)

    def fetch_winner_rows(self, *, sg_id: str, sg_typecode: str, sd_name: str | None = None):
        return [
            {
                "sgId": "20220309",
                "sgTypecode": "1",
                "huboid": "W1",
                "name": "Other Winner",
                "jdName": "Party B",
                "elcoYn": "Y",
            }
        ]

    def fetch_tally_rows(self, *, sg_id: str, sg_typecode: str, sd_name: str | None = None):
        return [
            {
                "sgId": "20220309",
                "sgTypecode": "1",
                "sdName": "합계",
                "sggName": "비례대표",
                "wiwName": "합계",
                "hbj01": "Target Candidate",
                "jd01": "Party A",
                "dugsu01": "100",
                "hbj02": "Other Winner",
                "jd02": "Party B",
                "dugsu02": "150",
            }
        ]


def test_search_candidates_falls_back_to_result_slots_for_scoped_queries():
    client = CandidateResultSlotFallbackClient()

    items = client.search_candidates(candidate_name="Target Candidate", sg_id="20220309", sg_typecode="1")

    assert len(items) == 1
    assert items[0].candidate_ref.sg_id == "20220309"
    assert items[0].candidate_ref.sg_typecode == "1"
    assert items[0].candidate_ref.candidate_name == "Target Candidate"
    assert items[0].party_name == "Party A"


def test_fetch_candidate_profile_row_falls_back_to_result_slots():
    client = CandidateResultSlotFallbackClient()

    row = client._fetch_candidate_profile_row(
        CandidateRef(
            sg_id="20220309",
            sg_typecode="1",
            candidate_name="Target Candidate",
        )
    )

    assert row is not None
    assert row["sgId"] == "20220309"
    assert row["name"] == "Target Candidate"
    assert row["jdName"] == "Party A"


class CandidateResultMultiRowFallbackClient(NecApiClient):
    def __init__(self) -> None:
        super().__init__(Settings(nec_api_key="test-key"))

    def _fetch_election_rows(self, *, include_history: bool = True):
        return [{"sgId": "20240410", "sgTypecode": "2", "sgName": "Assembly Election", "sgVotedate": "2024-04-10"}]

    def _fetch_candidate_scope_rows(
        self,
        *,
        sg_id: str,
        sg_typecode: str,
        sd_name: str | None = None,
        sgg_name: str | None = None,
    ):
        return []

    def _request_rows(self, service_key: str, params: dict[str, object]):
        if service_key == "candidate_search_name":
            return []
        raise AssertionError(service_key)

    def fetch_winner_rows(self, *, sg_id: str, sg_typecode: str, sd_name: str | None = None):
        return []

    def fetch_tally_rows(self, *, sg_id: str, sg_typecode: str, sd_name: str | None = None):
        return [
            {
                "sgId": "20240410",
                "sgTypecode": "2",
                "sdName": "Region",
                "sggName": "District A",
                "wiwName": "Region",
                "hbj01": "Alex Kim",
                "jd01": "Party A",
                "dugsu01": "100",
            },
            {
                "sgId": "20240410",
                "sgTypecode": "2",
                "sdName": "Region",
                "sggName": "District B",
                "wiwName": "Region",
                "hbj01": "Alex Kim",
                "jd01": "Party A",
                "dugsu01": "90",
            },
        ]


class CandidateResultWideAreaFallbackClient(NecApiClient):
    def __init__(self) -> None:
        super().__init__(Settings(nec_api_key="test-key"))

    def _fetch_election_rows(self, *, include_history: bool = True):
        return [{"sgId": "20220309", "sgTypecode": "1", "sgName": "Presidential Election", "sgVotedate": "2022-03-09"}]

    def _fetch_candidate_scope_rows(
        self,
        *,
        sg_id: str,
        sg_typecode: str,
        sd_name: str | None = None,
        sgg_name: str | None = None,
    ):
        return []

    def _request_rows(self, service_key: str, params: dict[str, object]):
        if service_key == "candidate_search_name":
            return []
        raise AssertionError(service_key)

    def fetch_winner_rows(self, *, sg_id: str, sg_typecode: str, sd_name: str | None = None):
        return []

    def fetch_tally_rows(self, *, sg_id: str, sg_typecode: str, sd_name: str | None = None):
        return [
            {
                "sgId": "20220309",
                "sgTypecode": "1",
                "sdName": "Region",
                "sggName": "District A",
                "wiwName": "Region",
                "hbj01": "Alex Kim",
                "jd01": "Party A",
                "dugsu01": "100",
            },
            {
                "sgId": "20220309",
                "sgTypecode": "1",
                "sdName": "Region",
                "sggName": "District B",
                "wiwName": "Region",
                "hbj01": "Alex Kim",
                "jd01": "Party A",
                "dugsu01": "90",
            },
        ]


def test_fetch_candidate_result_fallback_rows_keeps_candidates_from_each_tally_row():
    client = CandidateResultMultiRowFallbackClient()

    rows = client._fetch_candidate_result_fallback_rows(sg_id="20240410", sg_typecode="2")

    alex_rows = [row for row in rows if row["name"] == "Alex Kim"]
    assert len(alex_rows) == 2
    assert {(row["sdName"], row["sggName"]) for row in alex_rows} == {
        ("Region", "District A"),
        ("Region", "District B"),
    }


def test_fetch_candidate_result_fallback_rows_dedupes_wide_area_candidates_across_tally_rows():
    client = CandidateResultWideAreaFallbackClient()

    rows = client._fetch_candidate_result_fallback_rows(sg_id="20220309", sg_typecode="1")

    alex_rows = [row for row in rows if row["name"] == "Alex Kim"]
    assert len(alex_rows) == 1


def test_list_parties():
    client = StubNecApiClient()

    parties = client.list_parties(sg_id="20240410", sg_typecode="2")

    assert [party.party_code for party in parties] == ["001", "002"]
    assert [party.party_uid for party in parties] == ["20240410:2:001", "20240410:2:002"]
    assert all(party.provenance[0].entity_type == "party" for party in parties)

