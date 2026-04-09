from __future__ import annotations

from app.campaign_booklet_corpus import CampaignBookletCorpus
from app.config import Settings
from app.krpoltext_api import KrPolTextClient
from app.models import KrPolTextInput


TRUSTED_DATASET_URL = "https://taehyun-lim.github.io/krpoltext/data/campaign_booklet.csv"


class FailingSession:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get(self, url: str, **_: object) -> object:
        self.calls.append(url)
        raise AssertionError("Untrusted campaign booklet URLs should not be fetched")


def test_campaign_booklet_corpus_matches_code_and_candidate():
    corpus = CampaignBookletCorpus(
        Settings(nec_api_key="test-key"),
        row_loader=lambda: [
            {
                "date": "2022-03-09",
                "name": "Alice Kim",
                "region": "Seoul",
                "district": "Jongno",
                "office": "president",
                "party": "Future Party",
                "pages": "15",
                "code": "ECM0120220001_0002S",
                "text": "Core pledge text",
                "filtered": "Filtered pledge text",
            }
        ],
    )
    rows = corpus.search_rows(candidate_name="Alice Kim", election_year=2022, office_name="president")
    assert len(rows) == 1
    assert rows[0]["code"] == "ECM0120220001_0002S"

    code_rows = corpus.search_rows(code="ECM0120220001_0002S")
    assert len(code_rows) == 1
    assert code_rows[0]["name"] == "Alice Kim"




def test_krpoltext_client_uses_campaign_booklet_corpus_for_code_lookup():
    corpus = CampaignBookletCorpus(
        Settings(nec_api_key="test-key"),
        manifest_loader=lambda: {
            "generated_at": "2026-04-06T00:00:00Z",
            "resources": [{"name": "campaign_booklet", "download_url": TRUSTED_DATASET_URL}],
        },
        row_loader=lambda: [
            {
                "date": "2022-03-09",
                "name": "Alice Kim",
                "region": "Seoul",
                "district": "Jongno",
                "office": "president",
                "party": "Future Party",
                "pages": "15",
                "code": "ECM0120220001_0002S",
                "text": "Core pledge text",
                "filtered": "Filtered pledge text",
            }
        ],
    )
    client = KrPolTextClient(Settings(nec_api_key="test-key"), corpus=corpus)
    items = client.get_text(KrPolTextInput(code="ECM0120220001_0002S"))
    assert len(items) == 1
    assert items[0].code == "ECM0120220001_0002S"
    assert items[0].party_name == "Future Party"
    assert items[0].page_count == 15
    assert items[0].text == "Filtered pledge text"
    assert items[0].source_url == TRUSTED_DATASET_URL


def test_campaign_booklet_download_url_rejects_untrusted_manifest_url_and_uses_relative_path():
    corpus = CampaignBookletCorpus(
        Settings(nec_api_key="test-key"),
        manifest_loader=lambda: {
            "resources": [
                {
                    "name": "campaign_booklet",
                    "download_url": "https://evil.test/campaign_booklet.csv",
                    "path": "exports/campaign_booklet.csv",
                }
            ]
        },
    )

    assert corpus.campaign_booklet_download_url() == "https://taehyun-lim.github.io/krpoltext/data/exports/campaign_booklet.csv"


def test_campaign_booklet_iter_rows_skips_untrusted_manifest_url():
    session = FailingSession()
    corpus = CampaignBookletCorpus(
        Settings(nec_api_key="test-key"),
        session=session,
        manifest_loader=lambda: {
            "resources": [
                {
                    "name": "campaign_booklet",
                    "download_url": "https://evil.test/campaign_booklet.csv",
                }
            ]
        },
    )

    assert list(corpus.iter_rows()) == []
    assert session.calls == []

def test_campaign_booklet_download_url_prefers_csv_from_download_urls():
    corpus = CampaignBookletCorpus(
        Settings(nec_api_key="test-key"),
        manifest_loader=lambda: {
            "resources": [
                {
                    "name": "campaign_booklet",
                    "download_urls": {
                        "parquet": "https://taehyun-lim.github.io/krpoltext/data/campaign_booklet.parquet",
                        "csv": TRUSTED_DATASET_URL,
                    },
                }
            ]
        },
    )

    assert corpus.campaign_booklet_download_url() == TRUSTED_DATASET_URL


def test_campaign_booklet_download_url_supports_metadata_style_payload():
    corpus = CampaignBookletCorpus(
        Settings(nec_api_key="test-key"),
        manifest_loader=lambda: {
            "campaign_booklet": {
                "download_urls": {
                    "csv": TRUSTED_DATASET_URL,
                }
            }
        },
    )

    assert corpus.campaign_booklet_download_url() == TRUSTED_DATASET_URL


def test_campaign_booklet_iter_rows_skips_parquet_when_reader_is_unavailable(monkeypatch):
    session = FailingSession()
    corpus = CampaignBookletCorpus(
        Settings(nec_api_key="test-key"),
        session=session,
        manifest_loader=lambda: {
            "resources": [
                {
                    "name": "campaign_booklet",
                    "download_urls": {
                        "parquet": "https://taehyun-lim.github.io/krpoltext/data/campaign_booklet.parquet",
                    },
                }
            ]
        },
    )
    monkeypatch.setattr(corpus, "_parquet_supported", lambda: False)

    assert list(corpus.iter_rows()) == []
    assert session.calls == []



def test_campaign_booklet_download_url_accepts_osf_managed_csv_artifacts():
    osf_url = "https://osf.io/download/6ybj8/"
    corpus = CampaignBookletCorpus(
        Settings(nec_api_key="test-key"),
        manifest_loader=lambda: {
            "resources": [
                {
                    "name": "campaign_booklet",
                    "download_urls": {
                        "csv": osf_url,
                    },
                }
            ]
        },
    )

    assert corpus.campaign_booklet_download_url() == osf_url


class CsvResponse:
    def __init__(self, content: bytes, url: str) -> None:
        self.content = content
        self.url = url

    def raise_for_status(self) -> None:
        return None


class RecordingCsvSession:
    def __init__(self, content: bytes, url: str) -> None:
        self.content = content
        self.url = url
        self.calls: list[str] = []

    def get(self, url: str, **_: object) -> CsvResponse:
        self.calls.append(url)
        return CsvResponse(self.content, self.url)


def test_campaign_booklet_iter_rows_accepts_osf_redirect_host():
    csv_bytes = (
        b"date,name,region,district,office,party,code\n"
        b"2022-03-09,Alice Kim,Seoul,Jongno,president,Future Party,ECM0120220001_0002S\n"
    )
    session = RecordingCsvSession(
        csv_bytes,
        "https://files.osf.io/v1/resources/rct9y/providers/osfstorage/example.csv",
    )
    corpus = CampaignBookletCorpus(
        Settings(nec_api_key="test-key"),
        session=session,
        manifest_loader=lambda: {
            "resources": [
                {
                    "name": "campaign_booklet",
                    "download_urls": {
                        "csv": "https://osf.io/download/6ybj8/",
                    },
                }
            ]
        },
    )

    rows = list(corpus.iter_rows())

    assert len(rows) == 1
    assert rows[0]["code"] == "ECM0120220001_0002S"
    assert session.calls == ["https://osf.io/download/6ybj8/"]


def test_campaign_booklet_iter_rows_uses_parquet_loader_when_supported(monkeypatch):
    session = RecordingCsvSession(b"unused", "https://taehyun-lim.github.io/krpoltext/data/campaign_booklet.parquet")
    corpus = CampaignBookletCorpus(
        Settings(nec_api_key="test-key"),
        session=session,
        manifest_loader=lambda: {
            "resources": [
                {
                    "name": "campaign_booklet",
                    "download_urls": {
                        "parquet": "https://taehyun-lim.github.io/krpoltext/data/campaign_booklet.parquet",
                    },
                }
            ]
        },
    )
    monkeypatch.setattr(corpus, "_parquet_supported", lambda: True)
    monkeypatch.setattr(
        corpus,
        "_iter_parquet_rows",
        lambda content: iter([
            {
                "code": "ECM0120220001_0002S",
                "name": "Alice Kim",
            }
        ]),
    )

    rows = list(corpus.iter_rows())

    assert rows == [{"code": "ECM0120220001_0002S", "name": "Alice Kim"}]
    assert session.calls == ["https://taehyun-lim.github.io/krpoltext/data/campaign_booklet.parquet"]


