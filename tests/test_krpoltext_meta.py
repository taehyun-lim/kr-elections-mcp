from app.campaign_booklet_corpus import CampaignBookletCorpus
from app.config import Settings
from app.krpoltext_api import KrPolTextClient
from app.models import KrPolTextInput


TRUSTED_DATASET_URL = "https://taehyun-lim.github.io/krpoltext/data/campaign_booklet.csv"


def test_krpoltext_metadata_preserves_bio_fields_without_text_body():
    corpus = CampaignBookletCorpus(
        Settings(nec_api_key="test-key"),
        manifest_loader=lambda: {
            "generated_at": "2026-04-10T00:00:00Z",
            "resources": [{"name": "campaign_booklet", "download_url": TRUSTED_DATASET_URL}],
        },
        row_loader=lambda: [
            {
                "date": "2024-04-10",
                "name": "Alice Kim",
                "region": "Seoul",
                "district": "Jongno",
                "office_id": "2",
                "office": "national_assembly",
                "giho": "7",
                "party": "Independent",
                "party_eng": "Independent",
                "result": "elected",
                "result_code": "1",
                "sex": "female",
                "sex_code": "0",
                "birthday": "1970-01-02",
                "age": "54",
                "job_id": "100",
                "job": "Lawyer",
                "job_name": "lawyer",
                "job_name_eng": "lawyer",
                "job_code": "12",
                "edu_id": "200",
                "edu": "Seoul National University",
                "edu_name": "college",
                "edu_name_eng": "college",
                "edu_code": "4",
                "career1": "Former lawmaker",
                "career2": "Attorney",
                "pages": "12",
                "code": "ECM0120240001_0007S",
                "text": "Long booklet text",
            }
        ],
    )
    client = KrPolTextClient(Settings(nec_api_key="test-key"), corpus=corpus)

    items = client.get_metadata(KrPolTextInput(code="ECM0120240001_0007S", limit=1))

    assert len(items) == 1
    item = items[0]
    assert item.code == "ECM0120240001_0007S"
    assert item.office_id == 2
    assert item.giho == "7"
    assert item.birthday == "1970-01-02"
    assert item.age == 54
    assert item.job == "Lawyer"
    assert item.edu == "Seoul National University"
    assert item.career1 == "Former lawmaker"
    assert item.party_name_eng == "Independent"
    assert item.has_text is True
    assert item.raw_fields["giho"] == "7"
    assert "text" not in item.raw_fields

def test_krpoltext_metadata_clamps_exact_match_confidence_to_one():
    corpus = CampaignBookletCorpus(
        Settings(nec_api_key="test-key"),
        manifest_loader=lambda: {
            "generated_at": "2026-04-10T00:00:00Z",
            "resources": [{"name": "campaign_booklet", "download_url": TRUSTED_DATASET_URL}],
        },
        row_loader=lambda: [
            {
                "date": "2024-04-10",
                "name": "Alice Kim",
                "region": "Seoul",
                "district": "Jongno",
                "office_id": "2",
                "office": "national_assembly",
                "giho": "7",
                "party": "Independent",
                "code": "ECM0120240001_0007S",
                "text": "Long booklet text",
            }
        ],
    )
    client = KrPolTextClient(Settings(nec_api_key="test-key"), corpus=corpus)

    items = client.get_metadata(
        KrPolTextInput(
            candidate_name="Alice Kim",
            election_year=2024,
            office_name="national_assembly",
            district_name="Seoul Jongno",
            party_name="Independent",
            limit=1,
        )
    )

    assert len(items) == 1
    assert items[0].match_confidence == 1.0

