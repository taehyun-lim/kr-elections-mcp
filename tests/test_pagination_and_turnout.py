from __future__ import annotations

from app.config import Settings
from app.models import CandidateRef, Election
from app.nec_api import NecApiClient
from app.results_api import ResultsApiClient


class NoCache:
    def remember(self, key, fn, ttl_seconds=None):
        return fn()


class PaginatedDistrictClient(NecApiClient):
    def __init__(self) -> None:
        super().__init__(Settings(nec_api_key="test-key"), cache=NoCache())
        self.calls: list[tuple[str, int, int]] = []

    def _request_rows(self, service_key: str, params: dict[str, object]) -> list[dict[str, object]]:
        page_no = int(params["pageNo"])
        page_size = int(params["numOfRows"])
        self.calls.append((service_key, page_no, page_size))
        if service_key != "districts":
            raise AssertionError(service_key)
        if page_no == 1:
            return [
                {"sgId": "20240410", "sgTypecode": "2", "sdName": "Seoul", "sggName": f"District-{index}"}
                for index in range(page_size)
            ]
        if page_no == 2:
            return [{"sgId": "20240410", "sgTypecode": "2", "sdName": "Busan", "sggName": "District-100"}]
        return []


def test_fetch_district_rows_paginates_until_last_page():
    client = PaginatedDistrictClient()

    rows = client._fetch_district_rows(sg_id="20240410", sg_typecode="2")

    assert len(rows) == 101
    assert rows[0]["sggName"] == "District-0"
    assert rows[-1]["sggName"] == "District-100"
    assert client.calls == [("districts", 1, 100), ("districts", 2, 100)]


class DistrictFilterClient(NecApiClient):
    def __init__(self) -> None:
        super().__init__(Settings(nec_api_key="test-key"))

    def _fetch_district_rows(self, *, sg_id: str, sg_typecode: str, sd_name: str | None = None):
        return [
            {"sdName": "Seoul", "sggName": "Jongno"},
            {"sdName": "Seoul", "sggName": "Jung"},
            {"sdName": "Busan", "sggName": "Suyeong"},
        ]


def test_list_districts_filters_rows_locally_when_api_ignores_sd_name():
    client = DistrictFilterClient()

    districts = client.list_districts(sg_id="20240410", sg_typecode="2", sd_name="Seoul")

    assert [district.sd_name for district in districts] == ["Seoul", "Seoul"]
    assert [district.sgg_name for district in districts] == ["Jongno", "Jung"]


class SummaryFallbackNecClient:
    def get_election(self, sg_id: str, sg_typecode: str):
        return Election(
            election_uid=f"{sg_id}:{sg_typecode}",
            sg_id=sg_id,
            sg_typecode=sg_typecode,
            sg_name="Legislative",
            election_date="2024-04-10",
        )

    def list_elections(self, **kwargs):
        return [self.get_election("20240410", "2")]

    def list_districts(self, **kwargs):
        return []

    def list_parties(self, **kwargs):
        return []

    def fetch_winner_rows(self, **kwargs):
        return []

    def fetch_tally_rows(self, **kwargs):
        return [
            {
                "sgId": "20240410",
                "sgTypecode": "2",
                "sdName": "Seoul",
                "sggName": "Jongno",
                "wiwName": "Jongno",
                "sunsu": "126041",
                "tusu": "88779",
                "yutusu": "87809",
                "mutusu": "970",
                "hbj01": "Candidate A",
                "jd01": "Party A",
                "dugsu01": "44713",
                "hbj02": "Candidate B",
                "jd02": "Party B",
                "dugsu02": "38752",
            },
            {
                "sgId": "20240410",
                "sgTypecode": "2",
                "sdName": "합계",
                "sggName": "비례대표",
                "wiwName": "합계",
                "sunsu": "44200000",
                "tusu": "30000000",
                "yutusu": "29500000",
                "mutusu": "500000",
            },
        ]

    def fetch_turnout_rows(self, **kwargs):
        return []


def test_district_summary_uses_the_tally_row_and_flags_inconsistent_votes():
    client = ResultsApiClient(Settings(nec_api_key="test-key"), SummaryFallbackNecClient())

    summary = client.get_district_summary(
        sg_id="20240410",
        sg_typecode="2",
        sd_name="Seoul",
        sgg_name="Jongno",
        wiw_name="Jongno",
    )

    assert summary.electorate_count == 126041
    assert summary.turnout_count == 88779
    assert summary.valid_vote_count == 87809
    assert summary.invalid_vote_count == 970
    assert summary.candidate_count == 2
    assert summary.turnout_rate == round((88779 / 126041) * 100, 3)
    # The stub row lists only two of the candidates, so the vote total cannot match yutusu.
    assert any("candidate votes sum to 83465" in warning for warning in summary.warnings)


def test_election_overview_uses_the_national_total_row():
    client = ResultsApiClient(Settings(nec_api_key="test-key"), SummaryFallbackNecClient())

    overview = client.get_election_overview(sg_id="20240410", sg_typecode="2")

    assert overview.electorate_count == 44200000
    assert overview.turnout_count == 30000000
    assert overview.turnout_rate == round((30000000 / 44200000) * 100, 3)
    assert not any("summed" in warning for warning in overview.warnings)
