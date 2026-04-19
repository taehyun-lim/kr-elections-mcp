from __future__ import annotations

import requests

from app.campaign_booklet_corpus import CampaignBookletCorpus
from app.config import Settings
from app.krpoltext_api import KrPolTextClient
from app.krpoltext_matching import rank_krpoltext_candidate_matches
from app.models import Candidate, CandidateProfile, CandidateRef, KrPolTextInput, KrPolTextMetaRecord
from app.normalize import canonicalize_district


class JsonResponse:
    def __init__(self, payload, url: str) -> None:
        self._payload = payload
        self.url = url
        self.content = b""
        self.headers = {"Content-Type": "application/json"}

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class CsvResponse:
    def __init__(self, content: bytes, url: str) -> None:
        self.content = content
        self.url = url
        self.headers = {"Content-Type": "text/csv"}

    def raise_for_status(self) -> None:
        return None


class MetadataFallbackSession:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get(self, url: str, **_: object):
        self.calls.append(url)
        if url.endswith("/index.json"):
            raise requests.RequestException("index unavailable")
        if url.endswith("/metadata.json"):
            return JsonResponse(
                {
                    "campaign_booklet": {
                        "time_coverage": "2000-2022",
                        "variants": {
                            "original": {
                                "download_urls": {
                                    "csv": "https://osf.io/download/6ybj8/",
                                }
                            },
                            "enriched": {
                                "download_urls": {
                                    "csv": "https://osf.io/download/6ybj8/",
                                }
                            },
                        },
                    }
                },
                url,
            )
        if url == "https://osf.io/download/6ybj8/":
            return CsvResponse(
                (
                    b"date,name,region,district,office,party,code,huboid,sg_id,sg_typecode\n"
                    b"2024-04-10,Alice Kim,Seoul,Jongno,national_assembly,Independent,ECM0120240001_0007S,H1,20240410,2\n"
                ),
                "https://files.osf.io/v1/resources/rct9y/providers/osfstorage/example.csv",
            )
        raise AssertionError(f"Unexpected URL {url}")


def test_krpoltext_client_falls_back_to_metadata_manifest_when_index_is_unavailable(monkeypatch):
    session = MetadataFallbackSession()
    client = KrPolTextClient(Settings(nec_api_key="test-key"), session=session)
    monkeypatch.setattr(client.corpus, "_parquet_supported", lambda: False)

    items = client.get_metadata(KrPolTextInput(code="ECM0120240001_0007S", limit=1))

    assert len(items) == 1
    assert items[0].code == "ECM0120240001_0007S"
    assert items[0].huboid == "H1"
    assert items[0].sg_id == "20240410"
    assert items[0].sg_typecode == "2"
    assert session.calls == [
        "https://taehyun-lim.github.io/krpoltext/data/index.json",
        "https://taehyun-lim.github.io/krpoltext/data/metadata.json",
        "https://osf.io/download/6ybj8/",
    ]


def test_campaign_booklet_download_url_supports_nested_metadata_variants(monkeypatch):
    corpus = CampaignBookletCorpus(
        Settings(nec_api_key="test-key"),
        manifest_loader=lambda: {
            "campaign_booklet": {
                "time_coverage": "2000-2022",
                "variants": {
                    "original": {
                        "download_urls": {
                            "csv": "https://osf.io/download/6ybj8/",
                        }
                    },
                    "enriched": {
                        "download_urls": {
                            "csv": "https://osf.io/download/6ybj8/",
                            "parquet": "https://osf.io/download/69e3ee72a0e06b0928fd8ae2/",
                        }
                    },
                },
            }
        },
    )
    monkeypatch.setattr(corpus, "_parquet_supported", lambda: True)

    assert corpus.campaign_booklet_download_url() == "https://osf.io/download/69e3ee72a0e06b0928fd8ae2/"


def test_krpoltext_matching_uses_candidate_identifier_when_available():
    district = canonicalize_district("20240410", "2", "Seoul", "Jongno")
    candidate = Candidate(
        candidate_ref=CandidateRef(
            sg_id="20240410",
            sg_typecode="2",
            huboid="H1",
            candidate_name="Alice Kim",
            district_label=district.district_label,
            party_name="Independent",
            giho="7",
        ),
        district=district,
        party_name="Independent",
        giho="7",
        sg_name="national_assembly",
        election_date="2024-04-10",
    )
    profile = CandidateProfile(candidate=candidate)

    ranked = rank_krpoltext_candidate_matches(
        candidate,
        profile,
        [
            KrPolTextMetaRecord(
                record_id="K1",
                code="ECM0120240001_0007S",
                candidate_name="Alice Kim",
                huboid="H1",
                sg_id="20240410",
                sg_typecode="2",
                office_id=2,
                office_name="national_assembly",
                election_year=2024,
                district_name="Seoul Jongno",
                district_raw="Jongno",
                party_name="Independent",
            ),
            KrPolTextMetaRecord(
                record_id="K2",
                code="ECM0120240001_0008S",
                candidate_name="Alice Kim",
                huboid="H2",
                sg_id="20240410",
                sg_typecode="2",
                office_id=2,
                office_name="national_assembly",
                election_year=2024,
                district_name="Seoul Jongno",
                district_raw="Jongno",
                party_name="Independent",
            ),
        ],
    )

    assert ranked[0].item.code == "ECM0120240001_0007S"
    assert ranked[0].candidate_identifier_exact is True
    assert "candidate_identifier" in (ranked[0].metadata.match_method or "")
    assert ranked[0].identity_verified is True
    assert ranked[0].metadata.match_confidence > (ranked[1].metadata.match_confidence or 0.0)


def test_krpoltext_matching_falls_back_to_huboid_when_identifier_is_incomplete():
    district = canonicalize_district("20240410", "2", "Seoul", "Jongno")
    candidate = Candidate(
        candidate_ref=CandidateRef(
            sg_id="20240410",
            sg_typecode="2",
            huboid="H1",
            candidate_name="Alice Kim",
            district_label=district.district_label,
            party_name="Independent",
            giho="7",
        ),
        district=district,
        party_name="Independent",
        giho="7",
        sg_name="national_assembly",
        election_date="2024-04-10",
    )
    profile = CandidateProfile(candidate=candidate)

    ranked = rank_krpoltext_candidate_matches(
        candidate,
        profile,
        [
            KrPolTextMetaRecord(
                record_id="K1",
                code="ECM0120240001_0007S",
                candidate_name="Alice Kim",
                huboid="H1",
                office_id=2,
                office_name="national_assembly",
                election_year=2024,
                district_name="Seoul Jongno",
                district_raw="Jongno",
                party_name="Independent",
            ),
            KrPolTextMetaRecord(
                record_id="K2",
                code="ECM0120240001_0008S",
                candidate_name="Alice Kim",
                huboid="H2",
                office_id=2,
                office_name="national_assembly",
                election_year=2024,
                district_name="Seoul Jongno",
                district_raw="Jongno",
                party_name="Independent",
            ),
        ],
    )

    assert ranked[0].item.code == "ECM0120240001_0007S"
    assert ranked[0].candidate_identifier_exact is False
    assert "huboid" in (ranked[0].metadata.match_method or "")
    assert ranked[0].identity_verified is True
