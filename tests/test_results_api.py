from __future__ import annotations

from app.config import Settings
from app.models import Candidate, CandidateRef
from app.results_api import ResultsApiClient
from tests.fixtures.nec_stub import GoldenNec

SEOUL = "서울특별시"
BUSAN = "부산광역시"
JONGNO = "종로구"


def client_for(*fixtures: str) -> ResultsApiClient:
    return ResultsApiClient(Settings(nec_api_key="test-key"), GoldenNec(*fixtures))


def build_candidate(name: str, *, huboid: str | None = None, sgg_name: str = JONGNO, party: str | None = None) -> Candidate:
    return Candidate(
        candidate_ref=CandidateRef(
            sg_id="20240410",
            sg_typecode="2",
            huboid=huboid,
            candidate_name=name,
            sd_name=SEOUL,
            sgg_name=sgg_name,
            party_name=party,
        ),
        party_name=party,
    )


def test_result_matching_success():
    result = client_for().get_candidate_result(build_candidate("곽상언", huboid="100151444"))
    assert result is not None
    assert result.vote_count == 44713
    assert result.vote_share == 50.92
    assert result.match_confidence == 1.0
    assert (result.match_method or "").startswith("huboid")


def test_result_matching_returns_none_instead_of_a_wrong_row():
    # A candidate from another district must not borrow a row from the requested one.
    result, warnings = client_for().get_candidate_result_with_warnings(
        build_candidate("이인영", sgg_name=JONGNO)
    )
    assert result is None
    assert any("not in the district tally" in warning for warning in warnings)


def test_get_district_results_marks_winner_and_ranks():
    district, results = client_for().get_district_results(
        sg_id="20240410", sg_typecode="2", sd_name=SEOUL, sgg_name="구로구갑"
    )
    assert district.sgg_name == "구로구갑"
    assert [result.candidate_name for result in results] == ["이인영", "호준석"]
    assert [result.is_winner for result in results] == [True, False]
    assert [result.rank_in_district for result in results] == [1, 2]
    assert results[0].candidate_ref.huboid == "100152973"
    assert all(result.match_method == "district:exact" for result in results)
    assert all(result.coverage_scope == "district_rollup" for result in results)


def test_get_district_results_without_sgg_name_asks_for_one():
    _, results, warnings = client_for().get_district_results_with_warnings(
        sg_id="20240410", sg_typecode="2", sd_name=SEOUL
    )
    assert results == []
    assert any("5 districts" in warning and "sgg_name" in warning for warning in warnings)


def test_get_party_vote_share_history_across_elections():
    client = client_for("20200415_2_busan_tally.json", "20240410_2_busan_tally.json")

    history = client.get_party_vote_share_history(
        party_name="더불어민주당",
        district_name="사하구갑",
        sd_name=BUSAN,
        sg_typecode="2",
        year_from=2020,
        year_to=2024,
    )

    assert [point.election.sg_id for point in history] == ["20200415", "20240410"]
    assert [point.vote_count for point in history] == [39875, 43216]
    assert [point.vote_share for point in history] == [50.0, 49.6]
    assert all(point.match_method == "district:exact" for point in history)


def test_party_history_accepts_short_names():
    history = client_for().get_party_vote_share_history(
        party_name="민주당",
        district_name="서울 종로",
        sg_typecode="2",
        year_from=2024,
    )
    assert [(point.vote_count, point.vote_share) for point in history] == [(44713, 50.92)]


def test_party_lineage_is_opt_in():
    client = client_for("20200415_2_busan_tally.json", "20240410_2_busan_tally.json")
    kwargs = dict(
        party_name="\uad6d\ubbfc\uc758\ud798",
        district_name="\uc0ac\ud558\uad6c\uc744",
        sd_name=BUSAN,
        sg_typecode="2",
        year_from=2020,
        year_to=2024,
    )

    plain = client.get_party_vote_share_history(**kwargs)
    assert [point.election.sg_id for point in plain] == ["20240410"]

    lineage = client.get_party_vote_share_history(**kwargs, follow_lineage=True)
    assert [(point.election.sg_id, point.party_name, point.vote_count) for point in lineage] == [
        ("20200415", "\ubbf8\ub798\ud1b5\ud569\ub2f9", 59042),
        ("20240410", "\uad6d\ubbfc\uc758\ud798", 46855),
    ]
