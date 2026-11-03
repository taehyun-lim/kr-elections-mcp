"""NEC stub that serves captured real-shape fixtures through the real NecApiClient stack.

Only `_request_rows` is replaced, so pagination, parsing of rows, election lookup,
and everything above them run exactly as in production.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from app.config import Settings
from app.errors import ApiAuthorizationError
from app.nec_api import NecApiClient

FIXTURE_DIR = Path(__file__).parent / "nec"


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


class NoCache:
    def remember(self, key, fn, ttl_seconds=None):
        return fn()


class GoldenNec(NecApiClient):
    def __init__(
        self,
        *fixture_names: str,
        election_error: Exception | None = None,
        code_list_error: Exception | None = None,
        elections: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(Settings(nec_api_key="test-key", retry_attempts=1), cache=NoCache())
        self.winner_rows: list[dict[str, Any]] = []
        self.tally_rows: list[dict[str, Any]] = []
        for name in fixture_names or ("20240410_2_seoul.json",):
            fixture = load_fixture(name)
            self.winner_rows.extend(fixture["winner_rows"])
            self.tally_rows.extend(fixture["tally_rows"])
        self.election_error = election_error
        self.code_list_error = code_list_error
        self.election_rows = elections if elections is not None else [
            {"sgId": "20200415", "sgTypecode": "2", "sgName": "제21대 국회의원선거", "sgVotedate": "20200415"},
            {"sgId": "20240410", "sgTypecode": "2", "sgName": "제22대 국회의원선거", "sgVotedate": "20240410"},
        ]
        self.calls: Counter[str] = Counter()
        self.params: list[tuple[str, dict[str, Any]]] = []

    def _request_rows(self, service_key: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        self.calls[service_key] += 1
        self.params.append((service_key, dict(params)))
        if service_key == "elections":
            if self.election_error:
                raise self.election_error
            rows = self.election_rows
        elif service_key in {"districts", "parties"}:
            if self.code_list_error:
                raise self.code_list_error
            rows = []
        elif service_key == "winner_results":
            rows = self._scoped(self.winner_rows, params)
        elif service_key == "district_tally":
            rows = self._scoped(self.tally_rows, params)
        elif service_key == "turnout":
            rows = []
        else:
            rows = []
        page_no = int(params.get("pageNo", 1))
        page_size = int(params.get("numOfRows", 100))
        return rows[(page_no - 1) * page_size : page_no * page_size]

    @staticmethod
    def _scoped(rows: list[dict[str, Any]], params: dict[str, Any]) -> list[dict[str, Any]]:
        selected = []
        for row in rows:
            if params.get("sgId") and row.get("sgId") != params["sgId"]:
                continue
            if params.get("sgTypecode") and row.get("sgTypecode") != params["sgTypecode"]:
                continue
            # NEC filters sdName by exact name.
            if params.get("sdName") and row.get("sdName") != params["sdName"]:
                continue
            selected.append(row)
        return selected


def unauthorized() -> ApiAuthorizationError:
    return ApiAuthorizationError("HTTP 401: the service key was rejected.")
