"""Golden tests against real-shape NEC fixtures (report section 8, G1-G14)."""
from __future__ import annotations

import pytest
import requests

from app.config import Settings
from app.errors import ApiAuthorizationError, ApiQuotaError
from app.models import Candidate, CandidateRef
from app.nec_api import NecApiClient
from app.results_api import ResultsApiClient
from tests.fixtures.nec_stub import GoldenNec, NoCache, unauthorized

SEOUL = "서울특별시"
BUSAN = "부산광역시"
JONGNO = "종로구"


def results_client(nec: GoldenNec) -> ResultsApiClient:
    return ResultsApiClient(Settings(nec_api_key="test-key"), nec)


# G1
def test_g1_jongno_results_are_exactly_the_seven_jongno_candidates():
    district, results, warnings = results_client(GoldenNec()).get_district_results_with_warnings(
        sg_id="20240410", sg_typecode="2", sd_name=SEOUL, sgg_name=JONGNO
    )

    assert [r.candidate_name for r in results] == [
        "곽상언", "최재형", "금태섭", "진예찬",
        "차은정", "김종갑", "김준수",
    ]
    assert [r.vote_count for r in results] == [44713, 38752, 2835, 1080, 290, 85, 54]
    assert [r.vote_share for r in results[:3]] == [50.92, 44.13, 3.22]
    assert [r.is_winner for r in results] == [True] + [False] * 6
    assert results[0].candidate_ref.huboid == "100151444"
    assert results[0].giho == "1"
    assert all(r.giho is None for r in results[1:])
    assert all(r.candidate_ref.sgg_name == JONGNO for r in results)
    assert [r.rank_in_district for r in results] == [1, 2, 3, 4, 5, 6, 7]
    assert district.district_label == f"{SEOUL} {JONGNO}"
    assert all(r.match_confidence == 1.0 for r in results)
    assert warnings == []


# G2
def test_g2_aliases_resolve_and_split_districts_are_ambiguous():
    client = results_client(GoldenNec())
    _, results = client.get_district_results(
        sg_id="20240410", sg_typecode="2", sd_name="서울", sgg_name="종로"
    )
    assert [r.vote_count for r in results] == [44713, 38752, 2835, 1080, 290, 85, 54]

    _, results, warnings = client.get_district_results_with_warnings(
        sg_id="20240410", sg_typecode="2", sd_name=SEOUL, sgg_name="구로구"
    )
    assert results == []
    assert any("구로구갑" in w and "구로구을" in w for w in warnings)


# G3
def test_g3_busan_multi_area_vacant_ballot_and_divisions():
    client = results_client(GoldenNec("20240410_2_busan_tally.json"))

    _, results = client.get_district_results(
        sg_id="20240410", sg_typecode="2", sd_name=BUSAN, sgg_name="중구영도구"
    )
    assert [r.vote_count for r in results] == [46254, 36739, 1374]

    _, results = client.get_district_results(
        sg_id="20240410", sg_typecode="2", sd_name=BUSAN, sgg_name="사하구갑"
    )
    assert len(results) == 2

    _, results = client.get_district_results(
        sg_id="20240410", sg_typecode="2", sd_name=BUSAN, sgg_name="연제구"
    )
    assert [r.ballot_position for r in results] == [1, 2]
    assert all(r.giho is None for r in results)
    assert all(r.is_winner is False for r in results)  # winner API answered with no rows

    district, results, _ = client.get_district_results_with_warnings(
        sg_id="20240410", sg_typecode="2", sd_name=BUSAN, sgg_name="부산진구갑"
    )
    assert district.sgg_name == "부산진구갑"
    assert results[0].match_method == "district:exact"


# G4
def test_g4_missing_total_rows_are_rebuilt_from_sub_areas():
    nec = GoldenNec("20240410_2_busan_tally.json")
    nec.tally_rows = [row for row in nec.tally_rows if row["wiwName"] != "합계"]
    district, results, warnings = results_client(nec).get_district_results_with_warnings(
        sg_id="20240410", sg_typecode="2", sd_name=BUSAN, sgg_name="중구영도구"
    )
    assert [r.vote_count for r in results] == [46254, 36739, 1374]
    assert any("summed from 2 sub-area rows" in w for w in warnings)


# G5
def test_g5_jongno_summary_comes_from_the_total_row():
    summary = results_client(GoldenNec()).get_district_summary(
        sg_id="20240410", sg_typecode="2", sd_name=SEOUL, sgg_name=JONGNO
    )
    assert (
        summary.candidate_count,
        summary.electorate_count,
        summary.turnout_count,
        summary.valid_vote_count,
        summary.invalid_vote_count,
        summary.abstention_count,
        summary.turnout_rate,
    ) == (7, 126041, 88779, 87809, 970, 37262, 70.437)
    assert summary.election is not None


# G6
@pytest.mark.parametrize(
    ("fixture", "sd_name", "sgg_name", "electorate", "rate"),
    [
        ("20240410_2_seoul.json", SEOUL, "용산구", 188998, round(130243 / 188998 * 100, 3)),
        ("20240410_2_seoul.json", SEOUL, "구로구갑", 205069, 71.059),
        ("20240410_2_busan_tally.json", BUSAN, "사하구갑", 131310, round(88121 / 131310 * 100, 3)),
    ],
)
def test_g6_each_district_keeps_its_own_metrics(fixture, sd_name, sgg_name, electorate, rate):
    summary = results_client(GoldenNec(fixture)).get_district_summary(
        sg_id="20240410", sg_typecode="2", sd_name=sd_name, sgg_name=sgg_name
    )
    assert summary.electorate_count == electorate
    assert summary.turnout_rate == rate


# G7
def test_g7_summary_survives_code_api_401_with_minimal_requests():
    nec = GoldenNec(election_error=unauthorized(), code_list_error=unauthorized())
    summary = results_client(nec).get_district_summary(
        sg_id="20240410", sg_typecode="2", sd_name=SEOUL, sgg_name=JONGNO
    )
    assert summary.electorate_count == 126041
    assert len(summary.warnings) == 1
    assert "Election metadata unavailable" in summary.warnings[0]
    assert nec.calls["district_tally"] == 1
    assert nec.calls["winner_results"] == 1
    assert nec.calls["turnout"] == 0
    # The built-in calendar still names the election.
    assert summary.election is not None and summary.election.sg_id == "20240410"


# G8
def test_g8_candidate_result_is_the_candidates_own_row():
    client = results_client(GoldenNec())

    def candidate(name: str, huboid: str | None = None) -> Candidate:
        return Candidate(
            candidate_ref=CandidateRef(
                sg_id="20240410", sg_typecode="2", huboid=huboid, candidate_name=name, sd_name=SEOUL, sgg_name=JONGNO
            )
        )

    result = client.get_candidate_result(candidate("금태섭"))
    assert result is not None
    assert result.vote_count == 2835
    assert result.is_winner is False

    winner = client.get_candidate_result(candidate("곽상언", huboid="100151444"))
    assert winner is not None and winner.is_winner is True and winner.match_method.startswith("huboid")

    missing, warnings = client.get_candidate_result_with_warnings(candidate("홍길동"))
    assert missing is None
    assert warnings


# G9
def test_g9_party_history_includes_losing_party_and_uses_calendar_fallback():
    nec = GoldenNec(election_error=unauthorized(), code_list_error=unauthorized())
    history, warnings = results_client(nec).get_party_vote_share_history_with_warnings(
        party_name="국민의힘",
        district_name=JONGNO,
        sd_name=SEOUL,
        sg_typecode="2",
        year_from=2024,
    )
    assert [(p.vote_count, p.vote_share) for p in history] == [(38752, 44.13)]
    assert history[0].election.sg_id == "20240410"
    assert any("built-in calendar" in w for w in warnings)


# G10
def test_g10_overview_sums_district_totals_when_no_national_row():
    nec = GoldenNec(code_list_error=unauthorized())
    overview = results_client(nec).get_election_overview(sg_id="20240410", sg_typecode="2")
    assert overview.electorate_count == 869611
    assert overview.turnout_count == 598184
    assert overview.turnout_rate == round(598184 / 869611 * 100, 3)
    assert any("summed from 5 district total rows" in w for w in overview.warnings)
    assert overview.district_count == 5
    assert overview.winner_count == 3
    assert all(w.is_winner is True for w in overview.winners)


# G11
class StatusResponse:
    def __init__(self, status: int) -> None:
        self.status_code = status
        self.headers: dict[str, str] = {}
        self.text = ""

    def raise_for_status(self):
        raise requests.HTTPError(f"{self.status_code} for url with serviceKey=secret")

    def json(self):
        raise ValueError("no body")


class CountingSession:
    def __init__(self, response) -> None:
        self.response = response
        self.urls: list[str] = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        return self.response


def test_g11_http_401_fails_fast_without_sleep(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("app.nec_api.time.sleep", lambda seconds: sleeps.append(seconds))
    session = CountingSession(StatusResponse(401))
    client = NecApiClient(Settings(nec_api_key="test-key", retry_attempts=3), session=session, cache=NoCache())

    with pytest.raises(ApiAuthorizationError):
        client.fetch_winner_rows(sg_id="20240410", sg_typecode="2")
    assert len(session.urls) == 1
    assert sleeps == []


# G12
class JsonResponse:
    status_code = 200
    headers: dict[str, str] = {}

    def __init__(self, payload) -> None:
        self._payload = payload
        self.text = ""

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class RecordingCache:
    def __init__(self) -> None:
        self.stored: list[object] = []

    def remember(self, key, fn, ttl_seconds=None):
        value = fn()
        self.stored.append(value)
        return value


@pytest.mark.parametrize(("code", "error"), [("30", ApiAuthorizationError), ("22", ApiQuotaError)])
def test_g12_gateway_envelope_errors_are_classified_and_not_cached(code, error):
    payload = {"OpenAPI_ServiceResponse": {"cmmMsgHeader": {"errMsg": "SERVICE ERROR", "returnReasonCode": code}}}
    cache = RecordingCache()
    client = NecApiClient(
        Settings(nec_api_key="test-key", retry_attempts=1),
        session=CountingSession(JsonResponse(payload)),
        cache=cache,
    )
    with pytest.raises(error):
        client.fetch_tally_rows(sg_id="20240410", sg_typecode="2")
    assert cache.stored == []


# G13
def test_g13_sub_area_of_a_split_district_is_flagged():
    district, results, warnings = results_client(GoldenNec("20200415_2_busan_tally.json")).get_district_results_with_warnings(
        sg_id="20200415",
        sg_typecode="2",
        sd_name=BUSAN,
        sgg_name="북구강서구을",
        wiw_name="강서구",
    )
    assert results and all(r.coverage_scope == "sub_area" for r in results)
    assert district.wiw_name == "강서구"
    assert any("관할 구시군 기준" in w for w in warnings)


# G14
def test_g14_published_share_matches_truncated_computation():
    _, results, warnings = results_client(GoldenNec()).get_district_results_with_warnings(
        sg_id="20240410", sg_typecode="2", sd_name=SEOUL, sgg_name="구로구을"
    )
    assert results[0].vote_share == 59.86
    assert not any("differs from computed" in w for w in warnings)


# Province-level and national contests (row shapes captured live for 세종)
SEJONG = "\uc138\uc885\ud2b9\ubcc4\uc790\uce58\uc2dc"


def test_governor_race_needs_no_district_name():
    nec = GoldenNec("20220601_3_sejong.json")
    _, results, warnings = results_client(nec).get_district_results_with_warnings(
        sg_id="20220601", sg_typecode="3", sd_name="\uc138\uc885"
    )
    assert [(r.candidate_name, r.vote_count, r.is_winner) for r in results] == [
        ("\ucd5c\ubbfc\ud638", 78415, True),
        ("\uc774\ucd98\ud76c", 69995, False),
    ]
    assert results[0].giho == "2"
    assert results[0].vote_share == 52.83
    assert warnings == []


def test_presidential_province_result_uses_the_province_total_row():
    nec = GoldenNec("20220309_1_sejong.json")
    summary = results_client(nec).get_district_summary(sg_id="20220309", sg_typecode="1", sd_name=SEJONG)
    assert (summary.candidate_count, summary.electorate_count, summary.valid_vote_count) == (12, 288895, 229891)
    _, results = results_client(nec).get_district_results(sg_id="20220309", sg_typecode="1", sd_name=SEJONG)
    assert results[0].candidate_name == "\uc774\uc7ac\uba85"
    assert results[0].vote_share == 51.91


def test_presidential_province_share_ignores_the_nationwide_winner_share():
    nec = GoldenNec("20220309_1_sejong.json")
    nec.winner_rows.append(
        {
            "sgId": "20220309", "sgTypecode": "1", "huboid": "100138362", "sdName": "\uc804\uad6d",
            "sggName": "\ub300\ud55c\ubbfc\uad6d", "giho": "2", "jdName": "\uad6d\ubbfc\uc758\ud798",
            "name": "\uc724\uc11d\uc5f4", "dugsu": "16394815", "dugyul": "48.56",
        }
    )
    _, results, warnings = results_client(nec).get_district_results_with_warnings(
        sg_id="20220309", sg_typecode="1", sd_name=SEJONG
    )
    yoon = next(r for r in results if r.candidate_name == "\uc724\uc11d\uc5f4")
    assert yoon.is_winner is True
    assert yoon.vote_count == 101491
    assert yoon.vote_share == 44.14  # Sejong share, not the nationwide 48.56
    assert sum(r.vote_share for r in results) <= 100
    assert not any("differs from computed" in w for w in warnings)


# 2025 presidential rows without sdName: one nationwide row (sdName '합계') and 17 province rows, all with
# sggName '대한민국'.
PRESIDENTIAL_2025 = "20250603_1_national.json"


def test_presidential_overview_uses_the_nationwide_row():
    nec = GoldenNec(PRESIDENTIAL_2025, code_list_error=unauthorized())
    overview = results_client(nec).get_election_overview(sg_id="20250603", sg_typecode="1")
    assert (overview.electorate_count, overview.turnout_count) == (44391871, 35236497)
    assert overview.turnout_rate == round(35236497 / 44391871 * 100, 3)
    assert not any("summed from" in w or "Turnout rows unavailable" in w for w in overview.warnings)
    assert overview.district_count == 17
    assert overview.winner_count == 1


def test_presidential_nationwide_result_needs_no_province():
    _, results, warnings = results_client(GoldenNec(PRESIDENTIAL_2025)).get_district_results_with_warnings(
        sg_id="20250603", sg_typecode="1", sd_name="전국"
    )
    lee = results[0]
    assert (lee.candidate_name, lee.vote_count, lee.vote_share, lee.is_winner) == (
        "이재명", 17287513, 49.42, True
    )
    assert sum(r.vote_count for r in results) <= 34980616  # valid votes nationwide
    assert not any("districts exist" in w for w in warnings)


def test_presidential_districts_derived_from_tally_are_the_provinces():
    districts = results_client(GoldenNec(PRESIDENTIAL_2025)).list_districts_from_results(
        sg_id="20250603", sg_typecode="1"
    )
    assert len(districts) == 17
    assert "합계" not in {d.sd_name for d in districts}
