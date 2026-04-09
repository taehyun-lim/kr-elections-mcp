from __future__ import annotations

import sys

import keyring
from keyring.errors import KeyringError, NoKeyringError, PasswordDeleteError

from .errors import SecretStoreError


class SecretStore:
    SERVICE_NAME = "kr-election-mcp"
    NEC_API_KEY_NAME = "nec_api_key"
    NEC_API_KEY_ENCODED_NAME = "nec_api_key_encoded"
    NEC_API_KEY_DECODED_NAME = "nec_api_key_decoded"

    def __init__(
        self,
        *,
        service_name: str = SERVICE_NAME,
        key_name: str = NEC_API_KEY_NAME,
        encoded_key_name: str = NEC_API_KEY_ENCODED_NAME,
        decoded_key_name: str = NEC_API_KEY_DECODED_NAME,
    ) -> None:
        self.service_name = service_name
        self.key_name = key_name
        self.encoded_key_name = encoded_key_name
        self.decoded_key_name = decoded_key_name

    def get_nec_api_key(self, *, silent: bool = False) -> str | None:
        keys = self.get_nec_api_keys(silent=silent)
        return keys["decoded"] or keys["encoded"] or keys["legacy"]

    def get_nec_api_keys(self, *, silent: bool = False) -> dict[str, str | None]:
        return {
            "legacy": self._get_password(self.key_name, silent=silent),
            "encoded": self._get_password(self.encoded_key_name, silent=silent),
            "decoded": self._get_password(self.decoded_key_name, silent=silent),
        }

    def set_nec_api_keys(self, *, encoded: str | None = None, decoded: str | None = None) -> None:
        self._set_or_delete_password(self.encoded_key_name, encoded)
        self._set_or_delete_password(self.decoded_key_name, decoded)
        self._delete_password(self.key_name, silent=True)

    def set_nec_api_key(self, value: str) -> None:
        self._set_or_delete_password(self.key_name, value)

    def delete_nec_api_keys(self) -> None:
        self._delete_password(self.encoded_key_name, silent=True)
        self._delete_password(self.decoded_key_name, silent=True)
        self._delete_password(self.key_name, silent=True)

    def delete_nec_api_key(self) -> None:
        self.delete_nec_api_keys()

    def _get_password(self, key_name: str, *, silent: bool = False) -> str | None:
        try:
            return keyring.get_password(self.service_name, key_name)
        except NoKeyringError as exc:
            if silent:
                return None
            raise SecretStoreError(self._missing_backend_message()) from exc
        except KeyringError as exc:
            if silent:
                return None
            raise SecretStoreError(f"Unable to read the NEC API key from the OS keyring: {exc}") from exc

    def _set_or_delete_password(self, key_name: str, value: str | None) -> None:
        if value in (None, ""):
            self._delete_password(key_name, silent=True)
            return
        try:
            keyring.set_password(self.service_name, key_name, value)
        except NoKeyringError as exc:
            raise SecretStoreError(self._missing_backend_message()) from exc
        except KeyringError as exc:
            raise SecretStoreError(f"Unable to store the NEC API key in the OS keyring: {exc}") from exc

    def _delete_password(self, key_name: str, *, silent: bool = False) -> None:
        try:
            keyring.delete_password(self.service_name, key_name)
        except PasswordDeleteError:
            return
        except NoKeyringError as exc:
            if silent:
                return
            raise SecretStoreError(self._missing_backend_message()) from exc
        except KeyringError as exc:
            if silent:
                return
            raise SecretStoreError(f"Unable to delete the NEC API key from the OS keyring: {exc}") from exc

    def backend_name(self) -> str:
        return keyring.get_keyring().__class__.__name__

    def describe_storage(self) -> str:
        backend = self.backend_name()
        if sys.platform.startswith("win"):
            return f"OS keyring ({backend}, typically Windows Credential Manager)"
        if sys.platform == "darwin":
            return f"OS keyring ({backend}, typically macOS Keychain)"
        return f"OS keyring ({backend})"

    @staticmethod
    def _missing_backend_message() -> str:
        return (
            "No OS keyring backend is available. Configure the key through your MCP client env "
            "or install a supported keyring backend for this machine."
        )
