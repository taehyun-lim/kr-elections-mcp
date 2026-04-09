from __future__ import annotations

from app.config import Settings
from app.krpoltext_api import KrPolTextClient
from app.models import KrPolTextInput


TRUSTED_TEXT_URL = "https://taehyun-lim.github.io/krpoltext/data/records/kt1.json"


class RecordingResponse:
    def __init__(self, *, payload: dict[str, str] | None = None, text: str = "", content_type: str = "application/json") -> None:
        self._payload = payload
        self._text = text
        self.headers = {"Content-Type": content_type}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, str]:
        if self._payload is None:
            raise ValueError("No JSON payload configured")
        return self._payload

    @property
    def text(self) -> str:
        return self._text


class RecordingSession:
    def __init__(self, response: RecordingResponse | None = None) -> None:
        self.response = response or RecordingResponse(payload={"text": "Fetched trusted text"})
        self.calls: list[str] = []

    def get(self, url: str, **_: object) -> RecordingResponse:
        self.calls.append(url)
        return self.response


class FailingSession:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get(self, url: str, **_: object) -> RecordingResponse:
        self.calls.append(url)
        raise AssertionError("Untrusted URLs should not be fetched")


def test_krpoltext_lookup_returns_ranked_record():
    client = KrPolTextClient(
        Settings(nec_api_key="test-key"),
        index_loader=lambda: [
            {
                "record_id": "KT1",
                "candidate_name": "Alice Kim",
                "office_name": "national_assembly",
                "election_year": 2024,
                "district_name": "Seoul Jongno",
                "dataset_version": "2024.04",
                "text": "Transit and housing pledge text",
                "source_url": TRUSTED_TEXT_URL,
                "time_range": "2024",
            }
        ],
    )
    items = client.get_text(
        KrPolTextInput(
            candidate_name="Alice Kim",
            election_year=2024,
            office_name="national_assembly",
            district_name="Seoul Jongno",
        )
    )
    assert len(items) == 1
    assert items[0].dataset_version == "2024.04"
    assert "Transit" in (items[0].text or "")
    assert items[0].match_confidence >= 0.7


def test_krpoltext_fetches_relative_source_url_from_trusted_host():
    session = RecordingSession(response=RecordingResponse(payload={"text": "Fetched trusted text"}))
    client = KrPolTextClient(
        Settings(nec_api_key="test-key"),
        session=session,
        index_loader=lambda: [
            {
                "record_id": "KT2",
                "candidate_name": "Alice Kim",
                "office_name": "national_assembly",
                "election_year": 2024,
                "district_name": "Seoul Jongno",
                "source_url": "records/kt2.json",
            }
        ],
    )

    items = client.get_text(
        KrPolTextInput(
            candidate_name="Alice Kim",
            election_year=2024,
            office_name="national_assembly",
            district_name="Seoul Jongno",
        )
    )

    assert len(items) == 1
    assert items[0].text == "Fetched trusted text"
    assert items[0].source_url == TRUSTED_TEXT_URL.replace("kt1", "kt2")
    assert session.calls == [TRUSTED_TEXT_URL.replace("kt1", "kt2")]


def test_krpoltext_rejects_untrusted_source_url_without_fetching():
    session = FailingSession()
    client = KrPolTextClient(
        Settings(nec_api_key="test-key"),
        session=session,
        index_loader=lambda: [
            {
                "record_id": "KT3",
                "candidate_name": "Alice Kim",
                "office_name": "national_assembly",
                "election_year": 2024,
                "district_name": "Seoul Jongno",
                "source_url": "https://evil.test/records/kt3.json",
            }
        ],
    )

    items = client.get_text(
        KrPolTextInput(
            candidate_name="Alice Kim",
            election_year=2024,
            office_name="national_assembly",
            district_name="Seoul Jongno",
        )
    )

    assert len(items) == 1
    assert items[0].source_url is None
    assert items[0].text is None
    assert any("trusted krpoltext hosts" in warning for warning in items[0].warnings)
    assert session.calls == []

def test_krpoltext_rejects_private_base_host_without_fetching():
    session = FailingSession()
    client = KrPolTextClient(
        Settings(
            nec_api_key="test-key",
            krpoltext_base_url="https://127.0.0.1/krpoltext/data",
        ),
        session=session,
        index_loader=lambda: [
            {
                "record_id": "KT4",
                "candidate_name": "Alice Kim",
                "office_name": "national_assembly",
                "election_year": 2024,
                "district_name": "Seoul Jongno",
                "source_url": "records/kt4.json",
            }
        ],
    )

    items = client.get_text(
        KrPolTextInput(
            candidate_name="Alice Kim",
            election_year=2024,
            office_name="national_assembly",
            district_name="Seoul Jongno",
        )
    )

    assert len(items) == 1
    assert items[0].source_url is None
    assert items[0].text is None
    assert any("trusted krpoltext hosts" in warning for warning in items[0].warnings)
    assert session.calls == []
