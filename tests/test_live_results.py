"""Live acceptance checks against the real NEC API (report section 8).

Run with:  python -m pytest -m live tests/test_live_results.py
Skipped automatically when no NEC key is configured.
"""
from __future__ import annotations

import pytest

from app.config import Settings
from app.nec_api import NecApiClient
from app.results_api import ResultsApiClient

SEOUL = "서울특별시"
JONGNO = "종로구"

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def client() -> ResultsApiClient:
    settings = Settings.from_env()
    if not settings.api_key_candidates():
        pytest.skip("NEC API key is not configured")
    return ResultsApiClient(settings, NecApiClient(settings))


def test_live_jongno_results(client):
    _, results = client.get_district_results(sg_id="20240410", sg_typecode="2", sd_name=SEOUL, sgg_name=JONGNO)
    assert len(results) == 7
    assert (results[0].candidate_name, results[0].vote_count, results[0].vote_share, results[0].is_winner) == (
        "곽상언",
        44713,
        50.92,
        True,
    )


def test_live_jongno_summary(client):
    summary = client.get_district_summary(sg_id="20240410", sg_typecode="2", sd_name=SEOUL, sgg_name=JONGNO)
    assert (
        summary.electorate_count,
        summary.turnout_count,
        summary.valid_vote_count,
        summary.invalid_vote_count,
        summary.abstention_count,
    ) == (126041, 88779, 87809, 970, 37262)


def test_live_party_history(client):
    history = client.get_party_vote_share_history(
        party_name="국민의힘",
        district_name=JONGNO,
        sd_name=SEOUL,
        sg_typecode="2",
        year_from=2024,
    )
    assert [point.vote_count for point in history] == [38752]
