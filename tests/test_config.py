from __future__ import annotations

from app.config import Settings
from app.secret_store import SecretStore


class FakeSecretStore:
    def __init__(
        self,
        key: str | None = None,
        *,
        encoded: str | None = None,
        decoded: str | None = None,
    ) -> None:
        self.key = key
        self.encoded = encoded
        self.decoded = decoded

    def get_nec_api_key(self, *, silent: bool = False) -> str | None:
        return self.key

    def get_nec_api_keys(self, *, silent: bool = False) -> dict[str, str | None]:
        return {"legacy": self.key, "encoded": self.encoded, "decoded": self.decoded}


def test_settings_prefers_env_over_keyring_and_dotenv(tmp_path, monkeypatch):
    env_file = tmp_path / '.env'
    env_file.write_text('NEC_API_KEY=file-value\nNEC_RESULT_FORMAT=json\n', encoding='utf-8')
    monkeypatch.setenv('NEC_API_KEY', 'env-value')

    settings = Settings.from_env(env_file=env_file, secret_store=FakeSecretStore('keyring-value'))

    assert settings.nec_api_key == 'env-value'
    assert settings.nec_api_key_source == 'env'


def test_settings_uses_keyring_before_dotenv(tmp_path, monkeypatch):
    env_file = tmp_path / '.env'
    env_file.write_text('NEC_API_KEY=file-value\n', encoding='utf-8')
    monkeypatch.delenv('NEC_API_KEY', raising=False)
    monkeypatch.delenv('NEC_API_KEY_ENCODED', raising=False)
    monkeypatch.delenv('NEC_API_KEY_DECODED', raising=False)

    settings = Settings.from_env(env_file=env_file, secret_store=FakeSecretStore('keyring-value'))

    assert settings.nec_api_key == 'keyring-value'
    assert settings.nec_api_key_source == 'keyring'


def test_settings_falls_back_to_dotenv(tmp_path, monkeypatch):
    env_file = tmp_path / '.env'
    env_file.write_text('NEC_API_KEY=file-value\n', encoding='utf-8')
    monkeypatch.delenv('NEC_API_KEY', raising=False)
    monkeypatch.delenv('NEC_API_KEY_ENCODED', raising=False)
    monkeypatch.delenv('NEC_API_KEY_DECODED', raising=False)

    settings = Settings.from_env(env_file=env_file, secret_store=FakeSecretStore(None))

    assert settings.nec_api_key == 'file-value'
    assert settings.nec_api_key_source == 'dotenv'
    assert settings.configured_key_formats() == ['decoded', 'encoded']


def test_settings_supports_typed_env_keys(tmp_path, monkeypatch):
    env_file = tmp_path / '.env'
    env_file.write_text('', encoding='utf-8')
    monkeypatch.delenv('NEC_API_KEY', raising=False)
    monkeypatch.setenv('NEC_API_KEY_ENCODED', 'env%2Bvalue')
    monkeypatch.setenv('NEC_API_KEY_DECODED', 'env+value')

    settings = Settings.from_env(env_file=env_file, secret_store=FakeSecretStore(None))

    assert settings.nec_api_key_source == 'env'
    assert settings.nec_api_key_encoded == 'env%2Bvalue'
    assert settings.nec_api_key_decoded == 'env+value'
    assert [candidate.key_format for candidate in settings.api_key_candidates()] == ['decoded', 'encoded']


def test_secret_store_round_trip(monkeypatch):
    store = {}

    class FakeBackend:
        pass

    monkeypatch.setattr('app.secret_store.keyring.set_password', lambda service, key, value: store.__setitem__((service, key), value))
    monkeypatch.setattr('app.secret_store.keyring.get_password', lambda service, key: store.get((service, key)))

    def fake_delete(service, key):
        store.pop((service, key), None)

    monkeypatch.setattr('app.secret_store.keyring.delete_password', fake_delete)
    monkeypatch.setattr('app.secret_store.keyring.get_keyring', lambda: FakeBackend())

    secret_store = SecretStore()
    secret_store.set_nec_api_keys(encoded='abc%2B123', decoded='abc+123')
    keys = secret_store.get_nec_api_keys()
    assert keys['encoded'] == 'abc%2B123'
    assert keys['decoded'] == 'abc+123'
    assert secret_store.get_nec_api_key() == 'abc+123'
    assert 'FakeBackend' in secret_store.describe_storage()
    secret_store.delete_nec_api_keys()
    assert secret_store.get_nec_api_key() is None

def test_settings_ignores_dotenv_unless_explicit(tmp_path, monkeypatch):
    env_file = tmp_path / '.env'
    env_file.write_text('NEC_API_KEY=file-value\n', encoding='utf-8')
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('NEC_API_KEY', raising=False)
    monkeypatch.delenv('NEC_API_KEY_ENCODED', raising=False)
    monkeypatch.delenv('NEC_API_KEY_DECODED', raising=False)

    settings = Settings.from_env(secret_store=FakeSecretStore(None))

    assert settings.nec_api_key is None
    assert settings.nec_api_key_source is None
