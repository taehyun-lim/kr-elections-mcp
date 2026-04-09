from __future__ import annotations

from app.config import Settings
from app.models import Candidate, CandidateRef, Election
from app.normalize import canonicalize_district
from app.results_api import ResultsApiClient


class StubResultsNecClient:
    def list_elections(self, **kwargs):
        return [
            Election(
                election_uid="20240410:2",
                sg_id="20240410",
                sg_typecode="2",
                sg_name="National Assembly Election",
                election_date="2024-04-10",
            )
        ]

    def list_districts(self, **kwargs):
        return [canonicalize_district("20240410", "2", "Metro City", "Central")]

    def list_parties(self, **kwargs):
        return []

    def get_election(self, sg_id: str, sg_typecode: str):
        return self.list_elections()[0]

    def fetch_winner_rows(self, **kwargs):
        return []

    def fetch_tally_rows(self, **kwargs):
        return [
            {
                "sgId": "20240410",
                "sgTypecode": "2",
                "huboid": "H1",
                "huboNm": "Alex Kim",
                "jdName": "Party A",
                "giho": "1",
                "sdName": "Metro City",
                "sggName": "Central",
                "dugsu": "50000",
                "dugyul": "55.5",
            },
            {
                "sgId": "20240410",
                "sgTypecode": "2",
                "huboid": "H2",
                "huboNm": "Blair Park",
                "jdName": "Party B",
                "giho": "2",
                "sdName": "Metro City",
                "sggName": "Central",
                "dugsu": "40000",
                "dugyul": "44.5",
            },
        ]

    def fetch_turnout_rows(self, **kwargs):
        return [
            {
                "sdName": "Metro City",
                "sggName": "Central",
                "sungeoInwon": "120000",
                "tusuInwon": "92000",
                "tupyoYul": "76.7",
                "muhyoTupyoSu": "2000",
            }
        ]


class HistoricalResultsNecClient:
    def list_elections(self, **kwargs):
        items = [
            Election(
                election_uid="20200415:2",
                sg_id="20200415",
                sg_typecode="2",
                sg_name="National Assembly Election",
                election_date="2020-04-15",
            ),
            Election(
                election_uid="20240410:2",
                sg_id="20240410",
                sg_typecode="2",
                sg_name="National Assembly Election",
                election_date="2024-04-10",
            ),
        ]
        sg_typecode = kwargs.get("sg_typecode")
        year_from = kwargs.get("year_from")
        year_to = kwargs.get("year_to")
        filtered = []
        for item in items:
            year = int((item.election_date or "")[:4]) if item.election_date else None
            if sg_typecode and item.sg_typecode != sg_typecode:
                continue
            if year_from and year and year < year_from:
                continue
            if year_to and year and year > year_to:
                continue
            filtered.append(item)
        return filtered

    def list_districts(self, **kwargs):
        sg_id = kwargs.get("sg_id", "20240410")
        return [canonicalize_district(sg_id, "2", "Metro City", "Central")]

    def list_parties(self, **kwargs):
        return []

    def get_election(self, sg_id: str, sg_typecode: str):
        for item in self.list_elections():
            if item.sg_id == sg_id and item.sg_typecode == sg_typecode:
                return item
        return None

    def fetch_winner_rows(self, **kwargs):
        return []

    def fetch_tally_rows(self, *, sg_id: str, sg_typecode: str, sd_name: str | None = None):
        rows_by_election = {
            "20200415": [
                {
                    "sgId": "20200415",
                    "sgTypecode": "2",
                    "huboid": "HA",
                    "huboNm": "Alex Kim",
                    "jdName": "Party A",
                    "giho": "1",
                    "sdName": "Metro City",
                    "sggName": "Central",
                    "dugsu": "47000",
                    "dugyul": "52.1",
                },
                {
                    "sgId": "20200415",
                    "sgTypecode": "2",
                    "huboid": "HB",
                    "huboNm": "Blair Park",
                    "jdName": "Party B",
                    "giho": "2",
                    "sdName": "Metro City",
                    "sggName": "Central",
                    "dugsu": "43200",
                    "dugyul": "47.9",
                },
            ],
            "20240410": [
                {
                    "sgId": "20240410",
                    "sgTypecode": "2",
                    "huboid": "HC",
                    "huboNm": "Alex Kim",
                    "jdName": "Party A",
                    "giho": "1",
                    "sdName": "Metro City",
                    "sggName": "Central",
                    "dugsu": "50000",
                    "dugyul": "55.5",
                },
                {
                    "sgId": "20240410",
                    "sgTypecode": "2",
                    "huboid": "HD",
                    "huboNm": "Blair Park",
                    "jdName": "Party B",
                    "giho": "2",
                    "sdName": "Metro City",
                    "sggName": "Central",
                    "dugsu": "40000",
                    "dugyul": "44.5",
                },
            ],
        }
        return rows_by_election[sg_id]

    def fetch_turnout_rows(self, **kwargs):
        return []


def build_candidate(
    huboid: str,
    district_label: str,
    party_name: str,
    *,
    candidate_name: str = "Alex Kim",
    giho: str = "1",
) -> Candidate:
    district = canonicalize_district("20240410", "2", "Metro City", district_label.split()[-1])
    return Candidate(
        candidate_ref=CandidateRef(
            sg_id="20240410",
            sg_typecode="2",
            huboid=huboid,
            candidate_name=candidate_name,
            sd_name="Metro City",
            sgg_name=district_label.split()[-1],
            district_label=district.district_label,
            party_name=party_name,
            giho=giho,
        ),
        district=district,
        party_name=party_name,
        giho=giho,
    )


def test_result_matching_success():
    client = ResultsApiClient(Settings(nec_api_key="test-key"), StubResultsNecClient())
    candidate = build_candidate("H1", "Metro City Central", "Party A")
    result = client.get_candidate_result(candidate)
    assert result is not None
    assert result.vote_count == 50000
    assert result.vote_share == 55.5
    assert result.match_confidence >= 0.8
    assert "huboid" in (result.match_method or "")


def test_result_matching_low_confidence():
    client = ResultsApiClient(Settings(nec_api_key="test-key"), StubResultsNecClient())
    candidate = build_candidate(
        "UNKNOWN",
        "Metro City North",
        "Party Z",
        candidate_name="Taylor Cho",
        giho="9",
    )
    result = client.get_candidate_result(candidate)
    assert result is not None
    assert result.match_confidence < 0.45


def test_get_district_results():
    stub = StubResultsNecClient()
    client = ResultsApiClient(Settings(nec_api_key="test-key"), stub)
    district = stub.list_districts()[0]

    resolved_district, results = client.get_district_results(
        sg_id="20240410",
        sg_typecode="2",
        sd_name=district.sd_name or "",
        sgg_name=district.sgg_name,
        wiw_name=district.wiw_name,
    )

    assert resolved_district.district_uid == district.district_uid
    assert [result.candidate_ref.huboid for result in results] == ["H1", "H2"]
    assert [result.vote_count for result in results] == [50000, 40000]
    assert [result.rank_in_district for result in results] == [1, 2]
    assert all(result.match_method == "district" for result in results)


def test_get_party_vote_share_history():
    client = ResultsApiClient(Settings(nec_api_key="test-key"), HistoricalResultsNecClient())

    history = client.get_party_vote_share_history(
        party_name="Party A",
        district_name="Metro City Central",
        sd_name="Metro City",
        sg_typecode="2",
        year_from=2020,
        year_to=2024,
    )

    assert [point.election.sg_id for point in history] == ["20200415", "20240410"]
    assert [point.vote_share for point in history] == [52.1, 55.5]
    assert all(point.party_name == "Party A" for point in history)
    assert all(point.match_method == "district" for point in history)
