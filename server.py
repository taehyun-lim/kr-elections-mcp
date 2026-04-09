from __future__ import annotations

import argparse
import getpass
import logging
from pathlib import Path

from fastmcp import FastMCP

from app.cache import SimpleFileCache
from app.config import Settings
from app.diagnostics import DiagnosticsService
from app.errors import SecretStoreError
from app.krpoltext_api import KrPolTextClient
from app.nec_api import NecApiClient
from app.redact import mask_secret
from app.resources import register_resources
from app.results_api import ResultsApiClient
from app.secret_store import SecretStore
from app.tool_handlers import ToolHandlers, register_tools


def create_server(settings: Settings | None = None) -> FastMCP:
    settings = settings or Settings.from_env()
    logging.basicConfig(level=_resolve_log_level(settings.log_level))
    cache = SimpleFileCache(settings.cache_dir, settings.cache_ttl_seconds)
    nec_client = NecApiClient(settings=settings, cache=cache)
    results_client = ResultsApiClient(settings=settings, nec_client=nec_client)
    krpoltext_client = KrPolTextClient(settings=settings)
    diagnostics_service = DiagnosticsService(nec_client=nec_client, results_client=results_client)
    handlers = ToolHandlers(
        nec_client=nec_client,
        results_client=results_client,
        krpoltext_client=krpoltext_client,
        diagnostics_service=diagnostics_service,
    )

    mcp = FastMCP("South Korean Election MCP")
    register_tools(mcp, handlers)
    register_resources(mcp, handlers)
    return mcp


def __getattr__(name: str):
    if name == "mcp":
        return create_server()
    raise AttributeError(name)


def setup_key(*, env_file: str | None = None, skip_validate: bool = False) -> int:
    store = SecretStore()
    print("This command stores your NEC API key variants in the OS keyring.")
    print(f"Storage target: {store.describe_storage()}")
    print("Do not paste the key into chat or commit it to the repository.")
    try:
        encoded_key = _prompt_secret("encoded NEC service key")
        decoded_key = _prompt_secret("decoded NEC service key")
    except ValueError as exc:
        print(str(exc))
        return 1

    if not encoded_key and not decoded_key:
        print("No key was entered.")
        return 1

    try:
        store.set_nec_api_keys(encoded=encoded_key, decoded=decoded_key)
    except SecretStoreError as exc:
        print(str(exc))
        print("Fallback: set NEC_API_KEY_DECODED and/or NEC_API_KEY_ENCODED in your MCP client env instead.")
        return 1

    print(f"Stored NEC API key variants in {store.describe_storage()}.")
    if encoded_key:
        print(f"Stored encoded key: {_mask_key(encoded_key)}")
    if decoded_key:
        print(f"Stored decoded key: {_mask_key(decoded_key)}")

    if skip_validate:
        print("Validation skipped.")
        return 0

    ok, message = validate_keys(encoded_key=encoded_key, decoded_key=decoded_key, env_file=env_file)
    if ok:
        print(f"Validation succeeded: {message}")
        return 0
    print(f"Key was saved, but validation did not fully succeed: {message}")
    return 1


def clear_key() -> int:
    store = SecretStore()
    try:
        store.delete_nec_api_keys()
    except SecretStoreError as exc:
        print(str(exc))
        return 1
    print("Removed the NEC API key variants from the OS keyring if they existed.")
    return 0


def show_key_source(*, env_file: str | None = None) -> int:
    settings = Settings.from_env(env_file=env_file)
    source = settings.nec_api_key_source or "none"
    print(f"NEC API key source: {source}")
    formats = settings.configured_key_formats()
    print(f"Configured key formats: {', '.join(formats) if formats else 'none'}")
    if source == "keyring":
        print(f"Storage: {SecretStore().describe_storage()}")
    elif source == "dotenv":
        print(f"Source file: {Path(env_file).resolve() if env_file else 'not provided'}")
    elif source == "env":
        print("The key is coming from the current process or MCP client environment.")
    else:
        print("No NEC API key is configured.")
    if formats:
        print("Request order: decoded first, encoded second.")
    return 0


def validate_keys(
    *,
    encoded_key: str | None = None,
    decoded_key: str | None = None,
    env_file: str | None = None,
) -> tuple[bool, str]:
    settings = Settings.from_env(env_file=env_file)
    settings = settings.model_copy(
        update={
            "nec_api_key": decoded_key or encoded_key,
            "nec_api_key_encoded": encoded_key,
            "nec_api_key_decoded": decoded_key,
            "nec_api_key_source": "setup-key",
        }
    )
    nec_client = NecApiClient(settings=settings)
    try:
        elections = nec_client.list_elections(include_history=True)
    except Exception as exc:  # pragma: no cover - depends on remote API state
        return False, str(exc)
    if elections:
        return True, f"Received {len(elections)} election rows from NEC."
    return False, "The NEC endpoint responded but returned no election rows."


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="South Korean Election MCP (kr-elections-mcp) server and local key-management CLI")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Run the stdio MCP server")
    run_parser.add_argument("--env-file", default=None, help="Optional dotenv file for development fallback settings")

    setup_parser = subparsers.add_parser("setup-key", help="Prompt for the NEC API key and store it in the OS keyring")
    setup_parser.add_argument("--env-file", default=None, help="Optional dotenv file used only for validation-time settings")
    setup_parser.add_argument("--skip-validate", action="store_true")

    source_parser = subparsers.add_parser("show-key-source", help="Show where the NEC API key would be loaded from")
    source_parser.add_argument("--env-file", default=None, help="Optional dotenv file to inspect as a development fallback")

    subparsers.add_parser("clear-key", help="Delete the stored NEC API key from the OS keyring")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.command or "run"

    if command == "setup-key":
        return setup_key(env_file=args.env_file, skip_validate=args.skip_validate)
    if command == "clear-key":
        return clear_key()
    if command == "show-key-source":
        return show_key_source(env_file=args.env_file)
    if command == "run":
        settings = Settings.from_env(env_file=getattr(args, "env_file", None))
        create_server(settings).run()
        return 0

    parser.error(f"Unknown command: {command}")
    return 2


def _mask_key(value: str) -> str:
    return mask_secret(value)


def _prompt_secret(label: str) -> str | None:
    value = getpass.getpass(f"Paste the {label} (press Enter to skip): ").strip()
    if not value:
        return None
    confirm = getpass.getpass(f"Paste the {label} again to confirm: ").strip()
    if value != confirm:
        raise ValueError(f"The two {label} values did not match. Nothing was stored.")
    return value


def _resolve_log_level(value: str) -> int:
    return getattr(logging, value.upper(), logging.INFO)


if __name__ == "__main__":
    raise SystemExit(main())

