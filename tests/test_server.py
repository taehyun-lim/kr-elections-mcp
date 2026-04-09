from __future__ import annotations

import server


def test_setup_key_returns_error_when_validation_fails(monkeypatch):
    stored: dict[str, str | None] = {}

    class FakeStore:
        def describe_storage(self) -> str:
            return "fake keyring"

        def set_nec_api_keys(self, *, encoded: str | None = None, decoded: str | None = None) -> None:
            stored["encoded"] = encoded
            stored["decoded"] = decoded

    prompts = iter(["encoded-key", "decoded-key"])

    monkeypatch.setattr(server, "SecretStore", lambda: FakeStore())
    monkeypatch.setattr(server, "_prompt_secret", lambda label: next(prompts))
    monkeypatch.setattr(server, "validate_keys", lambda **kwargs: (False, "validation failed"))

    assert server.setup_key() == 1
    assert stored == {"encoded": "encoded-key", "decoded": "decoded-key"}
