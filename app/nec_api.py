from __future__ import annotations

import hashlib
import json
import logging
import random
import time
from datetime import date
from typing import Any
from urllib.parse import quote
from xml.etree.ElementTree import Element, ParseError  # nosec B405
from defusedxml.ElementTree import fromstring

import requests

from .cache import SimpleFileCache
from .coerce import as_bool, as_int, as_str
from .config import Settings
from .election_catalog import CALENDAR_WARNING, calendar_election, calendar_elections, filter_elections
from .errors import (
    ApiAuthorizationError,
    ApiNotAppliedError,
    ApiQuotaError,
    ApiRequestError,
    ApiTransientError,
    ConfigurationError,
    ResourceUnavailableError,
)
from .models import (
    AvailabilityState,
    Candidate,
    CandidatePolicy,
    CandidateProfile,
    CandidateRef,
    CandidateResolution,
    Election,
    Party,
    ProvenanceRecord,
    ResolutionStatus,
)
from .normalize import (
    build_district_label,
    canonicalize_district,
    candidate_name_similarity,
    first_of,
    map_party_name,
    normalize_candidate_name,
    normalize_district_name,
    normalize_party_name,
)
from .district_resolver import DistrictMatch, resolve_district_name
from .geo import sido_key, split_sido_prefix
from .scope import scope_rule
from .tally import TOTAL_WIW_NAME, build_district_tallies, district_key, is_wide_tally_row, match_winners
from .redact import redact_api_key

logger = logging.getLogger(__name__)

SERVICE_SPECS: dict[str, tuple[str, str]] = {
    "elections": ("CommonCodeService", "getCommonSgCodeList"),
    "districts": ("CommonCodeService", "getCommonSggCodeList"),
    # Inferred from the NEC code-info family naming shown in the official docs.
    "parties": ("CommonCodeService", "getCommonPartyCodeList"),
    "candidate_search": ("PofelcddInfoInqireService", "getPoelpcddRegistSttusInfoInqire"),
    "candidate_search_name": ("CndaSrchService", "getCndaSrchInqire"),
    "candidate_profile": ("PofelcddInfoInqireService", "getPoelpcddRegistSttusInfoInqire"),
    "candidate_policies": ("ElecPrmsInfoInqireService", "getCnddtElecPrmsInfoInqire"),
    "winner_results": ("WinnerInfoInqireService2", "getWinnerInfoInqire"),
    "district_tally": ("VoteXmntckInfoInqireService2", "getXmntckSttusInfoInqire"),
    "turnout": ("VoteXmntckInfoInqireService2", "getVoteSttusInfoInqire"),
}

AUTHORIZATION_CODES = {"30", "31", "32"}
NOT_APPLIED_CODES = {"12", "20"}
QUOTA_CODES = {"22"}
TRANSIENT_CODES = {"01", "02", "04", "05", "99"}
# Bump when cached payload semantics change; v2 drops entries cached before error envelopes were detected.
CACHE_KEY_VERSION = "v2"
ELECTION_INDEX_TTL_SECONDS = 24 * 3600
ELECTION_FAILURE_TTL_SECONDS = 300
LONG_LIVED_SERVICES = {"elections", "districts", "parties", "candidate_search_name"}

ERROR_MESSAGES = {
    "00": None,
    "01": "Application error.",
    "02": "Database error.",
    "03": "No data returned.",
    "04": "HTTP error.",
    "05": "Service timed out.",
    "10": "Invalid request parameter.",
    "11": "Missing required request parameter.",
    "12": "Unknown API service.",
    "20": "Access denied for this API.",
    "22": "Request quota exceeded.",
    "30": "Service key is not registered.",
    "31": "Service key approval has expired.",
    "32": "Unauthorized IP address.",
    "99": "Unknown upstream error.",
}


class NecApiClient:
    def __init__(
        self,
        settings: Settings,
        *,
        session: requests.Session | None = None,
        cache: SimpleFileCache | None = None,
    ) -> None:
        """Initialize the NEC client with settings, HTTP session, and cache hooks."""
        self.settings = settings
        self.session = session or requests.Session()
        self.cache = cache or SimpleFileCache(settings.cache_dir, settings.cache_ttl_seconds)

    def list_elections(
        self,
        *,
        sg_typecode: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        include_history: bool = True,
    ) -> list[Election]:
        """List elections from NEC code tables, optionally filtered by type or year."""
        rows = self._fetch_election_rows(include_history=include_history)
        items: list[Election] = []
        for row in rows:
            sg_id = str(first_of(row, "sgId", "sg_id", "sgid") or "").strip()
            type_code = str(first_of(row, "sgTypecode", "sg_typecode", "sgtypecode") or "").strip()
            election_date = self._as_str(first_of(row, "sgVotedate", "election_date", "voteDate"))
            if sg_typecode and type_code != sg_typecode:
                continue
            year = self._extract_year(election_date)
            if year_from and year and year < year_from:
                continue
            if year_to and year and year > year_to:
                continue
            election = Election(
                election_uid=f"{sg_id}:{type_code}",
                sg_id=sg_id,
                sg_typecode=type_code,
                sg_name=self._as_str(first_of(row, "sgName", "sg_name")),
                election_date=election_date,
                provenance=[self._provenance("nec_openapi", "election", f"{sg_id}:{type_code}")],
            )
            items.append(election)
        return items

    def get_election(self, sg_id: str, sg_typecode: str) -> Election | None:
        """Return one election matching the supplied NEC identifiers, if present."""
        return self._election_index().get((sg_id, sg_typecode))

    def try_get_election(self, sg_id: str, sg_typecode: str) -> tuple[Election | None, list[str]]:
        """Like get_election, but never raises: metadata must not sink a result query."""
        try:
            election = self.get_election(sg_id, sg_typecode)
        except (ApiRequestError, ConfigurationError) as exc:
            fallback = calendar_election(sg_id, sg_typecode)
            return fallback, [f"Election metadata unavailable ({self._short_error(exc)}); results are still shown."]
        return election, []

    def list_elections_with_warnings(
        self,
        *,
        sg_typecode: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        include_history: bool = True,
    ) -> tuple[list[Election], list[str]]:
        """list_elections with a built-in calendar fallback when the code API fails."""
        try:
            items = self.list_elections(
                sg_typecode=sg_typecode,
                year_from=year_from,
                year_to=year_to,
                include_history=include_history,
            )
            return items, []
        except ApiRequestError as exc:
            items = filter_elections(
                calendar_elections(), sg_typecode=sg_typecode, year_from=year_from, year_to=year_to
            )
            if not include_history:
                latest: dict[str, Election] = {}
                for item in items:
                    latest[item.sg_typecode] = item
                items = sorted(latest.values(), key=lambda item: item.sg_id, reverse=True)
            return items, [f"{CALENDAR_WARNING} Cause: {self._short_error(exc)}"]

    def _election_index(self) -> dict[tuple[str, str], Election]:
        now = time.monotonic()
        memo = getattr(self, "_election_memo", None)
        if memo and now < memo[0]:
            return memo[1]
        failure = getattr(self, "_election_failure", None)
        if failure and now < failure[0]:
            raise failure[1]
        try:
            items = self.list_elections(include_history=True)
        except ApiRequestError as exc:
            self._election_failure = (now + ELECTION_FAILURE_TTL_SECONDS, exc)
            raise
        index: dict[tuple[str, str], Election] = {}
        for item in items:
            index.setdefault((item.sg_id, item.sg_typecode), item)
        self._election_memo = (now + ELECTION_INDEX_TTL_SECONDS, index)
        self._election_failure = None
        return index

    @staticmethod
    def _short_error(exc: Exception) -> str:
        text = str(exc).strip() or type(exc).__name__
        return text if len(text) <= 160 else text[:157] + "..."

    def list_districts(
        self,
        *,
        sg_id: str,
        sg_typecode: str,
        sd_name: str | None = None,
        match_mode: str = "strict",
    ) -> list[Any]:
        """List and normalize districts for an election, optionally scoped by province/city."""
        rows = self._fetch_district_rows(sg_id=sg_id, sg_typecode=sg_typecode, sd_name=sd_name)
        districts = []
        seen_district_uids: set[str] = set()
        for row in rows:
            row_sd_name = self._as_str(first_of(row, "sdName", "sd_name"))
            if sd_name and row_sd_name and sido_key(row_sd_name) != sido_key(sd_name):
                continue
            district = canonicalize_district(
                sg_id=sg_id,
                sg_typecode=sg_typecode,
                sd_name=row_sd_name,
                sgg_name=self._as_str(first_of(row, "sggName", "sgg_name")),
                wiw_name=self._as_str(first_of(row, "wiwName", "wiw_name")),
                match_mode=match_mode,
            )
            if district.district_uid in seen_district_uids:
                continue
            seen_district_uids.add(district.district_uid)
            district.provenance.append(
                self._provenance("nec_openapi", "district", district.district_uid)
            )
            districts.append(district)
        return districts

    def list_parties(self, *, sg_id: str, sg_typecode: str) -> list[Party]:
        """List parties registered for a given election."""
        rows = self._fetch_party_rows(sg_id=sg_id, sg_typecode=sg_typecode)
        parties = []
        for row in rows:
            name = self._as_str(first_of(row, "jdName", "party_name", "partyNm")) or ""
            code = self._as_str(first_of(row, "jdCode", "party_code"))
            parties.append(
                Party(
                    party_uid=f"{sg_id}:{sg_typecode}:{code or name}",
                    sg_id=sg_id,
                    sg_typecode=sg_typecode,
                    party_code=code,
                    party_name=name,
                    normalized_party_name=map_party_name(name),
                    provenance=[
                        self._provenance("nec_openapi", "party", f"{sg_id}:{sg_typecode}:{code or name}")
                    ],
                )
            )
        return parties

    def search_candidates(
        self,
        *,
        candidate_name: str,
        sg_id: str | None = None,
        sg_typecode: str | None = None,
        sd_name: str | None = None,
        district_name: str | None = None,
        limit: int = 10,
    ) -> list[Candidate]:
        """Search candidates and filter them against the supplied election scope."""
        rows = self._fetch_candidate_search_rows(
            candidate_name=candidate_name,
            sg_id=sg_id,
            sg_typecode=sg_typecode,
            sd_name=sd_name,
        )
        parsed = self._dedupe_candidates([self._candidate_from_row(row) for row in rows])
        query_norm = normalize_candidate_name(candidate_name)
        items: list[Candidate] = []
        for item in parsed:
            if sg_id and item.candidate_ref.sg_id != sg_id:
                continue
            if sg_typecode and item.candidate_ref.sg_typecode != sg_typecode:
                continue
            if sd_name and item.candidate_ref.sd_name and sido_key(item.candidate_ref.sd_name) != sido_key(sd_name):
                continue

            score = candidate_name_similarity(item.candidate_ref.candidate_name, candidate_name)
            if district_name and not self._district_query_matches(item.candidate_ref, district_name):
                continue
            if score < 0.55:
                continue
            items.append(item)
        same_name_count = sum(
            1 for item in items if normalize_candidate_name(item.candidate_ref.candidate_name) == query_norm
        )
        for item in items:
            item.ambiguity_score = 1.0 if same_name_count > 1 else 0.0
        items.sort(
            key=lambda candidate: (
                candidate_name_similarity(candidate.candidate_ref.candidate_name, candidate_name),
                1 if candidate.is_winner else 0,
            ),
            reverse=True,
        )
        return items[:limit]

    @staticmethod
    def _dedupe_candidates(items: list[Candidate]) -> list[Candidate]:
        """Collapse repeated rows for one candidacy (same election, type, and huboid)."""
        by_key: dict[tuple[str, str, str], int] = {}
        result: list[Candidate] = []
        for item in items:
            ref = item.candidate_ref
            if not ref.huboid:
                result.append(item)
                continue
            key = (ref.sg_id, ref.sg_typecode, ref.huboid)
            index = by_key.get(key)
            if index is None:
                by_key[key] = len(result)
                result.append(item)
                continue
            existing = result[index]
            if existing.is_winner is None and item.is_winner is not None:
                result[index] = item
        return result

    @staticmethod
    def _district_query_matches(ref: CandidateRef, district_name: str) -> bool:
        """True when a user-typed district names the candidate's district (one resolver for all callers)."""
        if ref.district_label and normalize_district_name(ref.district_label) == normalize_district_name(district_name):
            return True
        prefix, rest = split_sido_prefix(district_name)
        if prefix is None and ref.sd_name:
            parts = district_name.split(None, 1)
            if len(parts) == 2 and sido_key(parts[0]) == sido_key(ref.sd_name):
                prefix, rest = parts[0], parts[1]
        if prefix and ref.sd_name and sido_key(prefix) != sido_key(ref.sd_name):
            return False
        query = rest if prefix else district_name
        if not query:
            return True
        names = [name for name in (ref.sgg_name, ref.wiw_name) if name]
        if not names and ref.district_label:
            label_prefix, label_rest = split_sido_prefix(ref.district_label)
            names = [label_rest or ref.district_label]
        for name in names:
            if resolve_district_name(query, [name]).status == DistrictMatch.RESOLVED:
                return True
        # Candidates for province-wide offices carry the province as their district.
        return bool(ref.sd_name) and sido_key(query) == sido_key(ref.sd_name)

    def resolve_candidate(
        self,
        *,
        candidate_ref: CandidateRef | None = None,
        candidate_name: str | None = None,
        sg_id: str | None = None,
        sg_typecode: str | None = None,
        sd_name: str | None = None,
        district_name: str | None = None,
        party_name: str | None = None,
        giho: str | None = None,
    ) -> CandidateResolution:
        """Resolve a candidate query into one candidate when the result is unambiguous."""
        if candidate_ref and candidate_ref.huboid:
            candidate = self._candidate_from_profile_or_ref(candidate_ref)
            return CandidateResolution(
                status=ResolutionStatus.RESOLVED,
                candidate=candidate,
                candidates=[candidate],
                message="Resolved using huboid.",
            )

        if not candidate_name:
            return CandidateResolution(
                status=ResolutionStatus.NOT_FOUND,
                message="candidate_name or candidate_ref.huboid is required.",
            )

        candidates = self.search_candidates(
            candidate_name=candidate_name,
            sg_id=sg_id or (candidate_ref.sg_id if candidate_ref else None),
            sg_typecode=sg_typecode or (candidate_ref.sg_typecode if candidate_ref else None),
            sd_name=sd_name or (candidate_ref.sd_name if candidate_ref else None),
            district_name=district_name or (candidate_ref.district_label if candidate_ref else None),
            limit=20,
        )
        filtered = [candidate for candidate in candidates if self._candidate_matches(candidate, district_name, party_name, giho)]
        query_norm = normalize_candidate_name(candidate_name)
        exact = [
            candidate
            for candidate in filtered
            if normalize_candidate_name(candidate.candidate_ref.candidate_name) == query_norm
        ]
        if filtered and not exact:
            return CandidateResolution(
                status=ResolutionStatus.AMBIGUOUS,
                candidates=filtered,
                message="Only similar names matched; confirm the exact candidate name.",
                warnings=["No candidate has exactly the requested name."],
            )
        filtered = exact
        if len(filtered) == 1:
            return CandidateResolution(
                status=ResolutionStatus.RESOLVED,
                candidate=filtered[0],
                candidates=filtered,
                message="Resolved from candidate search.",
            )
        if not filtered:
            return CandidateResolution(
                status=ResolutionStatus.NOT_FOUND,
                candidates=candidates,
                message="No candidate matched the supplied filters.",
            )
        return CandidateResolution(
            status=ResolutionStatus.AMBIGUOUS,
            candidates=filtered,
            message="Multiple candidates matched; keep huboid/district/party in the next query.",
            warnings=["Candidate name is ambiguous across the provided context."],
        )

    def get_candidate_profile(
        self,
        candidate_ref: CandidateRef,
        *,
        include_raw_fields: bool = False,
    ) -> CandidateProfile:
        """Fetch and normalize a candidate profile row."""
        row = self._fetch_candidate_profile_row(candidate_ref)
        if not row:
            raise ResourceUnavailableError("Candidate profile could not be found.")
        candidate = self._candidate_from_row(row)
        extra_json = row if include_raw_fields else {}
        return CandidateProfile(
            candidate=candidate,
            birthday=self._as_str(first_of(row, "birthday", "birthDay", "birth")),
            age=self._as_int(first_of(row, "age", "ageNum")),
            gender=self._as_str(first_of(row, "gender", "sex")),
            job=self._as_str(first_of(row, "job", "jobName")),
            education=self._as_str(first_of(row, "education", "edu")),
            career1=self._as_str(first_of(row, "career1", "careerOne", "career")),
            career2=self._as_str(first_of(row, "career2", "careerTwo")),
            address=self._as_str(first_of(row, "address", "addr")),
            status_code=self._as_str(first_of(row, "status", "status_code")),
            status_label=self._as_str(first_of(row, "statusName", "status_label")),
            extra_json=extra_json,
            provenance=[
                self._provenance(
                    "nec_openapi",
                    "candidate_profile",
                    candidate_ref.huboid or candidate_ref.candidacy_uid or candidate_ref.candidate_name,
                )
            ],
        )

    def get_candidate_policies(self, candidate_ref: CandidateRef) -> tuple[list[CandidatePolicy], AvailabilityState]:
        """Fetch candidate policy rows and report whether NEC exposes them."""
        rows = self._fetch_candidate_policy_rows(candidate_ref)
        if not rows:
            return [], AvailabilityState.UNAVAILABLE
        items: list[CandidatePolicy] = []
        wide_items = self._expand_policy_rows(rows, candidate_ref)
        if wide_items is not None:
            return (wide_items, AvailabilityState.AVAILABLE) if wide_items else ([], AvailabilityState.UNAVAILABLE)
        for index, row in enumerate(rows, start=1):
            policy_source = self._as_str(first_of(row, "policy_source", "plcySe", "policyType")) or "manifesto"
            if policy_source not in {"manifesto", "party_policy"}:
                policy_source = "manifesto"
            items.append(
                CandidatePolicy(
                    policy_id=str(first_of(row, "policyId", "policy_id") or f"{candidate_ref.huboid or candidate_ref.candidate_name}:{index}"),
                    candidate_ref=candidate_ref,
                    policy_source=policy_source,
                    title=self._as_str(first_of(row, "title", "plcyTitle", "pledgeTitle")),
                    content=self._as_str(first_of(row, "content", "plcyCn", "pledgeContent")),
                    budget_text=self._as_str(first_of(row, "budget", "budgetText")),
                    order_no=self._as_int(first_of(row, "orderNo", "order_no")),
                    provenance=[
                        self._provenance(
                            "nec_openapi",
                            "candidate_policy",
                            str(first_of(row, "policyId", "policy_id") or index),
                        )
                    ],
                    raw_fields=row,
                )
            )
        return items, AvailabilityState.AVAILABLE

    def _expand_policy_rows(
        self, rows: list[dict[str, Any]], candidate_ref: CandidateRef
    ) -> list[CandidatePolicy] | None:
        """Expand NEC's wide pledge rows (prmsTitleN / prmmContN); None when rows are not wide."""
        if not any("prmsTitle1" in row or "prmsCnt" in row for row in rows):
            return None
        items: list[CandidatePolicy] = []
        for row in rows:
            count = self._as_int(row.get("prmsCnt")) or 0
            highest = max(
                [count]
                + [
                    int(key[len("prmsTitle"):])
                    for key in row
                    if key.startswith("prmsTitle") and key[len("prmsTitle"):].isdigit()
                ]
            )
            owner = self._as_str(first_of(row, "cnddtId", "huboid")) or candidate_ref.huboid or candidate_ref.candidate_name
            for index in range(1, highest + 1):
                title = self._as_str(row.get(f"prmsTitle{index}"))
                content = self._as_str(first_of(row, f"prmmCont{index}", f"prmsCont{index}"))
                if title is None and content is None:
                    continue
                order_no = self._as_int(row.get(f"prmsOrd{index}")) or index
                policy_id = f"{owner}:{order_no}"
                items.append(
                    CandidatePolicy(
                        policy_id=policy_id,
                        candidate_ref=candidate_ref,
                        policy_source="manifesto",
                        title=title,
                        content=content,
                        order_no=order_no,
                        realm=self._as_str(row.get(f"prmsRealmName{index}")),
                        provenance=[self._provenance("nec_openapi", "candidate_policy", policy_id)],
                        raw_fields={
                            key: row.get(key)
                            for key in (
                                f"prmsOrd{index}",
                                f"prmsRealmName{index}",
                                f"prmsTitle{index}",
                                f"prmmCont{index}",
                            )
                            if key in row
                        },
                    )
                )
        items.sort(key=lambda item: item.order_no or 0)
        return items

    def fetch_winner_rows(self, *, sg_id: str, sg_typecode: str, sd_name: str | None = None) -> list[dict[str, Any]]:
        """Fetch winner-only result rows for an election or province scope."""
        return self._request_paginated_rows(
            "winner_results",
            {"sgId": sg_id, "sgTypecode": sg_typecode, "sdName": sd_name},
        )

    def fetch_tally_rows(self, *, sg_id: str, sg_typecode: str, sd_name: str | None = None) -> list[dict[str, Any]]:
        """Fetch full district tally rows for an election or province scope."""
        return self._request_paginated_rows(
            "district_tally",
            {"sgId": sg_id, "sgTypecode": sg_typecode, "sdName": sd_name},
        )

    def fetch_turnout_rows(self, *, sg_id: str, sg_typecode: str, sd_name: str | None = None) -> list[dict[str, Any]]:
        """Fetch turnout rows for an election or province scope."""
        return self._request_paginated_rows(
            "turnout",
            {"sgId": sg_id, "sgTypecode": sg_typecode, "sdName": sd_name},
        )

    def _fetch_election_rows(self, *, include_history: bool = True) -> list[dict[str, Any]]:
        rows = self._request_paginated_rows("elections", {}, page_size=100, max_pages=100)
        if include_history:
            return rows

        latest_by_type: dict[str, dict[str, Any]] = {}
        for row in rows:
            type_code = self._as_str(first_of(row, "sgTypecode", "sg_typecode", "sgtypecode")) or ""
            if not type_code:
                continue
            existing = latest_by_type.get(type_code)
            if existing is None or self._election_row_sort_key(row) > self._election_row_sort_key(existing):
                latest_by_type[type_code] = row

        if latest_by_type:
            return sorted(latest_by_type.values(), key=self._election_row_sort_key, reverse=True)
        return rows[:1] if rows else []

    def _fetch_district_rows(self, *, sg_id: str, sg_typecode: str, sd_name: str | None = None) -> list[dict[str, Any]]:
        return self._request_paginated_rows(
            "districts",
            {"sgId": sg_id, "sgTypecode": sg_typecode, "sdName": sd_name},
        )

    def _fetch_party_rows(self, *, sg_id: str, sg_typecode: str) -> list[dict[str, Any]]:
        return self._request_paginated_rows("parties", {"sgId": sg_id, "sgTypecode": sg_typecode})

    def _fetch_candidate_search_rows(
        self,
        *,
        candidate_name: str,
        sg_id: str | None = None,
        sg_typecode: str | None = None,
        sd_name: str | None = None,
    ) -> list[dict[str, Any]]:
        if sg_id and sg_typecode:
            name_rows = self._request_paginated_rows(
                "candidate_search_name",
                {
                    "name": candidate_name,
                },
                max_pages=20,
            )
            if any(
                self._row_matches_search_scope(
                    row,
                    sg_id=sg_id,
                    sg_typecode=sg_typecode,
                    sd_name=sd_name,
                )
                for row in name_rows
            ):
                return name_rows

            scoped_rows = self._fetch_candidate_scope_rows(
                sg_id=sg_id,
                sg_typecode=sg_typecode,
                sd_name=sd_name,
            )
            if scoped_rows:
                return scoped_rows
            result_rows = self._fetch_candidate_result_fallback_rows(
                sg_id=sg_id,
                sg_typecode=sg_typecode,
                sd_name=sd_name,
            )
            return result_rows or name_rows
        return self._request_paginated_rows(
            "candidate_search_name",
            {
                "name": candidate_name,
            },
            max_pages=20,
        )

    def _fetch_candidate_scope_rows(
        self,
        *,
        sg_id: str,
        sg_typecode: str,
        sd_name: str | None = None,
        sgg_name: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._request_paginated_rows(
            "candidate_search",
            {
                "sgId": sg_id,
                "sgTypecode": sg_typecode,
                "sdName": sd_name,
                "sggName": sgg_name,
            },
            max_pages=20,
        )

    def _fetch_candidate_profile_row(self, candidate_ref: CandidateRef) -> dict[str, Any] | None:
        if candidate_ref.candidate_name:
            rows = self._request_paginated_rows(
                "candidate_search_name",
                {
                    "name": candidate_ref.candidate_name,
                },
                max_pages=20,
            )
            selected = self._select_candidate_row(rows, candidate_ref)
            if selected:
                return selected

        rows = self._fetch_candidate_scope_rows(
            sg_id=candidate_ref.sg_id,
            sg_typecode=candidate_ref.sg_typecode,
            sd_name=candidate_ref.sd_name,
            sgg_name=candidate_ref.sgg_name,
        )
        selected = self._select_candidate_row(rows, candidate_ref)
        if selected:
            return selected

        if candidate_ref.sd_name or candidate_ref.sgg_name:
            # Retry once without district filters because official NEC rows are not always complete for historical elections.
            rows = self._fetch_candidate_scope_rows(
                sg_id=candidate_ref.sg_id,
                sg_typecode=candidate_ref.sg_typecode,
            )
            selected = self._select_candidate_row(rows, candidate_ref)
            if selected:
                return selected

        if candidate_ref.candidate_name:
            fallback_rows = self._fetch_candidate_result_fallback_rows(
                sg_id=candidate_ref.sg_id,
                sg_typecode=candidate_ref.sg_typecode,
                sd_name=candidate_ref.sd_name,
            )
            return self._select_candidate_row(fallback_rows, candidate_ref)
        return None

    def _fetch_candidate_result_fallback_rows(
        self,
        *,
        sg_id: str,
        sg_typecode: str,
        sd_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Build candidate-like rows from result APIs: one row per candidate per district (합계 row only)."""
        election, _ = self.try_get_election(sg_id, sg_typecode)
        winner_rows = self.fetch_winner_rows(sg_id=sg_id, sg_typecode=sg_typecode, sd_name=sd_name)
        tally_rows = self.fetch_tally_rows(sg_id=sg_id, sg_typecode=sg_typecode, sd_name=sd_name)
        election_fields = {
            "sgName": election.sg_name if election else None,
            "elctNm": election.sg_name if election else None,
            "sgVotedate": (election.election_date if election else None) or sg_id,
        }

        rows: list[dict[str, Any]] = []
        seen: set[tuple[str, ...]] = set()

        def add(row: dict[str, Any]) -> None:
            marker = self._candidate_row_marker(row)
            if marker not in seen:
                seen.add(marker)
                rows.append(row)

        for row in winner_rows:
            add(
                {
                    **row,
                    "sgName": first_of(row, "sgName", "elctNm") or election_fields["sgName"],
                    "elctNm": first_of(row, "elctNm", "sgName") or election_fields["elctNm"],
                    "sgVotedate": first_of(row, "sgVotedate", "voteDate") or election_fields["sgVotedate"],
                    "winnerYn": first_of(row, "winnerYn", "elcoYn") or "Y",
                }
            )

        rule = scope_rule(sg_typecode)
        tallies = build_district_tallies(row for row in tally_rows if is_wide_tally_row(row))
        for tally in tallies.values():
            area = tally.rollup
            row_sd_name, row_sgg_name = tally.sd_name, tally.sgg_name
            if row_sd_name == TOTAL_WIW_NAME:
                row_sd_name, row_sgg_name = "\uc804\uad6d", None
            if rule.level == "national":
                local_winners = winner_rows
            else:
                local_winners = [
                    row
                    for row in winner_rows
                    if district_key(self._as_str(first_of(row, "sdName")), self._as_str(first_of(row, "sggName")))
                    == tally.key
                ]
            matched = match_winners(area.slots, local_winners, has_party=rule.has_party)
            for slot in area.slots:
                if not slot.name:
                    continue
                winner = matched.get(slot.ballot_position)
                is_winner = "Y" if winner else "N"
                add(
                    {
                        "sgId": sg_id,
                        "sgTypecode": sg_typecode,
                        **election_fields,
                        "name": slot.name,
                        "huboNm": slot.name,
                        "huboid": self._as_str(first_of(winner, "huboid")) if winner else None,
                        "jdName": slot.party,
                        "dugsu": str(slot.votes) if slot.votes is not None else None,
                        # The slot number is not the official ballot number; only winner rows carry giho.
                        "giho": self._as_str(first_of(winner, "giho")) if winner else None,
                        "ballotPosition": str(slot.ballot_position),
                        "sdName": row_sd_name,
                        "sggName": row_sgg_name,
                        "wiwName": None,
                        "winnerYn": is_winner,
                        "elcoYn": is_winner,
                    }
                )
        return rows

    def _row_matches_search_scope(
        self,
        row: dict[str, Any],
        *,
        sg_id: str,
        sg_typecode: str,
        sd_name: str | None = None,
    ) -> bool:
        if self._as_str(first_of(row, "sgId", "sg_id", "sgid")) != sg_id:
            return False
        if self._as_str(first_of(row, "sgTypecode", "sg_typecode", "sgtypecode")) != sg_typecode:
            return False
        if sd_name:
            row_sd_name = self._as_str(first_of(row, "sdName", "sd_name", "sidoName"))
            if row_sd_name and sido_key(row_sd_name) != sido_key(sd_name):
                return False
        return True

    @staticmethod
    def _scope_dedupe_location(
        sg_typecode: str | None,
        sd_name: str | None,
        sgg_name: str | None,
        wiw_name: str | None,
    ) -> tuple[str, str, str]:
        type_code = str(sg_typecode or "").strip()
        sd_value = sd_name or ""
        sgg_value = sgg_name or ""
        wiw_value = wiw_name or ""
        if type_code in {"1", "7"}:
            return "", "", ""
        if type_code in {"3", "8", "9", "11"}:
            return sd_value, "", ""
        return sd_value, sgg_value, wiw_value

    def _candidate_row_marker(self, row: dict[str, Any]) -> tuple[str, str, str, str, str, str, str, str]:
        sg_typecode = self._as_str(first_of(row, "sgTypecode", "sg_typecode", "sgtypecode")) or ""
        marker_sd_name, marker_sgg_name, marker_wiw_name = self._scope_dedupe_location(
            sg_typecode,
            self._as_str(first_of(row, "sdName", "sd_name", "sidoName")),
            self._as_str(first_of(row, "sggName", "sgg_name")),
            self._as_str(first_of(row, "wiwName", "wiw_name")),
        )
        return (
            self._as_str(first_of(row, "sgId", "sg_id", "sgid")) or "",
            sg_typecode,
            normalize_candidate_name(self._as_str(first_of(row, "name", "huboNm")) or ""),
            map_party_name(self._as_str(first_of(row, "jdName", "party_name", "partyNm")) or ""),
            marker_sd_name,
            marker_sgg_name,
            marker_wiw_name,
            self._as_str(first_of(row, "giho")) or "",
        )

    def _select_candidate_row(
        self,
        rows: list[dict[str, Any]],
        candidate_ref: CandidateRef,
    ) -> dict[str, Any] | None:
        if candidate_ref.huboid:
            for row in rows:
                row_huboid = self._as_str(first_of(row, "huboid", "huboId", "cnddtId"))
                if row_huboid == candidate_ref.huboid:
                    return row
        for row in rows:
            if self._row_matches_candidate_ref(row, candidate_ref):
                return row
        if rows and not candidate_ref.huboid and not candidate_ref.candidate_name:
            return rows[0]
        return None

    def _row_matches_candidate_ref(self, row: dict[str, Any], candidate_ref: CandidateRef) -> bool:
        row_sg_id = self._as_str(first_of(row, "sgId", "sg_id", "sgid"))
        if candidate_ref.sg_id and row_sg_id and row_sg_id != candidate_ref.sg_id:
            return False

        row_sg_typecode = self._as_str(first_of(row, "sgTypecode", "sg_typecode", "sgtypecode"))
        if candidate_ref.sg_typecode and row_sg_typecode and row_sg_typecode != candidate_ref.sg_typecode:
            return False

        row_name = self._as_str(first_of(row, "name", "huboNm", "candidate_name", "krName"))
        if candidate_ref.candidate_name and row_name:
            if normalize_candidate_name(row_name) != normalize_candidate_name(candidate_ref.candidate_name):
                return False

        row_sd_name = self._as_str(first_of(row, "sdName", "sd_name", "sidoName"))
        if candidate_ref.sd_name and row_sd_name and sido_key(row_sd_name) != sido_key(candidate_ref.sd_name):
            return False

        row_sgg_name = self._as_str(first_of(row, "sggName", "sgg_name"))
        if (
            candidate_ref.sgg_name
            and row_sgg_name
            and normalize_district_name(row_sgg_name) != normalize_district_name(candidate_ref.sgg_name)
        ):
            return False

        return True

    def _fetch_candidate_policy_rows(self, candidate_ref: CandidateRef) -> list[dict[str, Any]]:
        return self._request_paginated_rows(
            "candidate_policies",
            {
                "sgId": candidate_ref.sg_id,
                "sgTypecode": candidate_ref.sg_typecode,
                "cnddtId": candidate_ref.huboid,
            },
            max_pages=20,
        )

    def _candidate_from_profile_or_ref(self, candidate_ref: CandidateRef) -> Candidate:
        profile_row = self._fetch_candidate_profile_row(candidate_ref)
        if profile_row:
            return self._candidate_from_row(profile_row)
        district = canonicalize_district(
            sg_id=candidate_ref.sg_id,
            sg_typecode=candidate_ref.sg_typecode,
            sd_name=candidate_ref.sd_name,
            sgg_name=candidate_ref.sgg_name,
            wiw_name=candidate_ref.wiw_name,
        )
        return Candidate(
            candidate_ref=candidate_ref,
            district=district,
            party_name=candidate_ref.party_name,
            giho=candidate_ref.giho,
            provenance=[self._provenance("candidate_ref", "candidate", candidate_ref.huboid or candidate_ref.candidacy_uid)],
        )

    def _candidate_from_row(self, row: dict[str, Any]) -> Candidate:
        sg_id = self._as_str(first_of(row, "sgId", "sg_id", "sgid")) or ""
        sg_typecode = self._as_str(first_of(row, "sgTypecode", "sg_typecode", "sgtypecode")) or ""
        district = canonicalize_district(
            sg_id=sg_id,
            sg_typecode=sg_typecode,
            sd_name=self._as_str(first_of(row, "sdName", "sd_name", "sidoName")),
            sgg_name=self._as_str(first_of(row, "sggName", "sgg_name")),
            wiw_name=self._as_str(first_of(row, "wiwName", "wiw_name")),
        )
        name = self._as_str(first_of(row, "huboNm", "candidate_name", "name", "krName"))
        party_name = self._as_str(first_of(row, "jdName", "party_name", "partyNm", "partyName"))
        giho = self._as_str(first_of(row, "giho"))
        huboid = self._as_str(first_of(row, "huboid", "huboId", "cnddtId"))
        ref = CandidateRef(
            candidacy_uid=self._build_candidacy_uid(
                sg_id,
                sg_typecode,
                huboid,
                name,
                party_name,
                district.sd_name,
                district.sgg_name,
                district.wiw_name,
                giho,
            ),
            huboid=huboid,
            sg_id=sg_id,
            sg_typecode=sg_typecode,
            candidate_name=name,
            sd_name=district.sd_name,
            sgg_name=district.sgg_name,
            wiw_name=district.wiw_name,
            district_label=district.district_label,
            party_name=party_name,
            giho=giho,
        )
        return Candidate(
            candidate_ref=ref,
            sg_name=self._as_str(first_of(row, "sgName", "sg_name", "elctNm")),
            election_date=self._as_str(first_of(row, "sgVotedate", "voteDate", "election_date", "sgId", "sg_id")),
            district=district,
            party_name=party_name,
            giho=giho,
            is_winner=self._as_bool(first_of(row, "winnerYn", "is_winner", "dangseonYn", "elcoYn")),
            provenance=[self._provenance("nec_openapi", "candidate", ref.huboid or ref.candidacy_uid)],
            raw_fields=row,
        )

    def _candidate_matches(
        self,
        candidate: Candidate,
        district_name: str | None,
        party_name: str | None,
        giho: str | None,
    ) -> bool:
        if district_name and not self._district_query_matches(candidate.candidate_ref, district_name):
            return False
        if party_name and normalize_party_name(candidate.party_name) != normalize_party_name(party_name):
            return False
        if giho and str(candidate.giho) != str(giho):
            return False
        return True

    def _request_paginated_rows(
        self,
        service_key: str,
        params: dict[str, Any],
        *,
        page_size: int = 100,
        max_pages: int = 100,
    ) -> list[dict[str, Any]]:
        base_params = {
            key: value
            for key, value in params.items()
            if key not in {"pageNo", "numOfRows"} and value not in (None, "")
        }
        rows: list[dict[str, Any]] = []
        seen_batch_signatures: set[bytes] = set()
        for page_no in range(1, max_pages + 1):
            batch = self._request_rows(
                service_key,
                {**base_params, "pageNo": page_no, "numOfRows": page_size},
            )
            if not batch:
                break
            batch_signature = hashlib.blake2b(
                json.dumps(batch, ensure_ascii=False, sort_keys=True).encode("utf-8"), digest_size=16
            ).digest()
            if batch_signature in seen_batch_signatures:
                # Some NEC services ignore pageNo and repeat the last page.
                break
            seen_batch_signatures.add(batch_signature)
            rows.extend(batch)
            if len(batch) < page_size:
                break
        else:
            logger.warning(
                "%s: stopped after %d pages of %d rows; the result may be truncated.",
                service_key,
                max_pages,
                page_size,
            )
        return rows

    def _request_rows(self, service_key: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        service_name, operation_name = SERVICE_SPECS[service_key]
        clean_params = {key: value for key, value in params.items() if value not in (None, "")}
        cache_key = json.dumps(
            [CACHE_KEY_VERSION, self.settings.nec_result_format, service_key, clean_params],
            ensure_ascii=False,
            sort_keys=True,
        )
        default_ttl = self.settings.cache_ttl_seconds
        if default_ttl <= 0:
            return self._perform_request(service_name, operation_name, clean_params)
        getter = getattr(self.cache, "get", None)
        setter = getattr(self.cache, "set", None)
        if not (callable(getter) and callable(setter)):
            return self.cache.remember(
                cache_key,
                lambda: self._perform_request(service_name, operation_name, clean_params),
                ttl_seconds=self._ttl_for(service_key, clean_params, None),
            )
        cached = getter(cache_key)
        if cached is not None:
            return cached
        rows = self._perform_request(service_name, operation_name, clean_params)
        return setter(cache_key, rows, ttl_seconds=self._ttl_for(service_key, clean_params, rows))

    def _ttl_for(
        self,
        service_key: str,
        params: dict[str, Any] | None = None,
        rows: list[dict[str, Any]] | None = None,
        *,
        today: date | None = None,
    ) -> int:
        """Cache lifetime by data volatility: old results never change, fresh ones and empty answers might."""
        default = self.settings.cache_ttl_seconds
        if default <= 0:
            return default
        if service_key in LONG_LIVED_SERVICES:
            return max(default, 24 * 3600)
        election_day = self._date_of((params or {}).get("sgId"))
        if election_day is None:
            return default
        age_days = ((today or date.today()) - election_day).days
        if age_days < 0:
            return min(default, 600)  # before election day: registrations and withdrawals still change
        if age_days <= 90:
            return default if rows or rows is None else min(default, 600)
        if rows is not None and not rows:
            return min(default, 3600)
        return max(default, 30 * 24 * 3600)

    @staticmethod
    def _date_of(value: Any) -> date | None:
        digits = "".join(character for character in str(value or "") if character.isdigit())
        if len(digits) < 8:
            return None
        try:
            return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
        except ValueError:
            return None

    @staticmethod
    def _distinct_wire_keys(key_candidates: list[Any]) -> list[Any]:
        """Drop key variants that would be sent as the same serviceKey string."""
        distinct: list[Any] = []
        seen: set[str] = set()
        for candidate in key_candidates:
            wire = candidate.value if candidate.key_format == "encoded" else quote(str(candidate.value), safe="")
            if wire in seen:
                continue
            seen.add(wire)
            distinct.append(candidate)
        return distinct

    def _perform_request(
        self,
        service_name: str,
        operation_name: str,
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        all_key_candidates = self.settings.require_api_keys()
        key_candidates = self._distinct_wire_keys(all_key_candidates)
        known_values = [candidate.value for candidate in all_key_candidates]
        url = f"{self.settings.nec_api_base_url.rstrip('/')}/{service_name}/{operation_name}"
        label = f"{service_name}/{operation_name}"

        last_error: Exception | None = None
        last_key_error: ApiRequestError | None = None
        for attempt in range(1, self.settings.retry_attempts + 1):
            retry_after: float | None = None
            should_retry = False
            for key_candidate in key_candidates:
                try:
                    return self._perform_request_with_key(
                        url=url,
                        params=params,
                        key_value=key_candidate.value,
                        key_format=key_candidate.key_format,
                    )
                except (ApiAuthorizationError, ApiNotAppliedError) as exc:
                    # Another key variant may be the registered one; never sleep on auth errors.
                    last_key_error = exc
                    continue
                except ApiTransientError as exc:
                    last_error = exc
                    retry_after = exc.retry_after
                    should_retry = True
                    break
                except ApiRequestError as exc:
                    # Quota and other 4xx/contract errors do not improve with retries.
                    raise type(exc)(redact_api_key(f"{label}: {exc}", known_values=known_values)) from None
                except requests.RequestException as exc:
                    last_error = exc
                    should_retry = True
                    break
            if should_retry and attempt < self.settings.retry_attempts:
                delay = self.settings.retry_backoff_seconds * (2 ** (attempt - 1))
                delay += random.uniform(0, delay * 0.25)  # nosec B311 - jitter, not security
                if retry_after is not None:
                    delay = max(delay, min(retry_after, 30.0))
                time.sleep(delay)
                continue
            break
        if last_error is None and last_key_error is not None:
            raise type(last_key_error)(
                redact_api_key(f"{label}: {last_key_error}", known_values=known_values)
            ) from None
        error_type = ApiTransientError if isinstance(last_error, ApiTransientError) else ApiRequestError
        raise error_type(
            redact_api_key(
                f"Request failed for {label}: {self._describe_transport_error(last_error)}",
                known_values=known_values,
            )
        )

    @staticmethod
    def _describe_transport_error(error: Exception | None) -> str:
        if error is None:
            return "no response"
        if isinstance(error, requests.RequestException):
            # requests messages embed the full URL (and so the serviceKey); keep only the type.
            response = getattr(error, "response", None)
            status = getattr(response, "status_code", None)
            return type(error).__name__ + (f" (HTTP {status})" if status else "")
        return str(error)

    def _perform_request_with_key(
        self,
        *,
        url: str,
        params: dict[str, Any],
        key_value: str,
        key_format: str,
    ) -> list[dict[str, Any]]:
        result_type = self.settings.nec_result_format
        response = self.session.get(
            self._build_request_url(url, params, key_value=key_value, key_format=key_format, result_type=result_type),
            headers=self.settings.request_headers(),
            timeout=self._timeouts(),
        )
        self._raise_for_http_status(response)
        return self._unwrap_rows(self._parse_response_body(response, result_type))

    def _timeouts(self) -> tuple[float, float]:
        read_timeout = float(self.settings.request_timeout_seconds)
        return min(5.0, read_timeout), read_timeout

    @staticmethod
    def _build_request_url(
        base_url: str,
        params: dict[str, Any],
        *,
        key_value: str,
        key_format: str,
        result_type: str,
    ) -> str:
        query_parts = []
        for name, value in {**params, "resultType": result_type}.items():
            query_parts.append(f"{quote(str(name), safe='')}={quote(str(value), safe='')}")
        service_key = key_value if key_format == "encoded" else quote(str(key_value), safe="")
        query_parts.append(f"serviceKey={service_key}")
        return f"{base_url}?{'&'.join(query_parts)}"

    @staticmethod
    def _raise_for_http_status(response: Any) -> None:
        status = getattr(response, "status_code", None)
        if isinstance(status, int):
            if status in {401, 403}:
                raise ApiAuthorizationError(f"HTTP {status}: the service key was rejected.")
            if status == 429 or status >= 500:
                headers = getattr(response, "headers", None) or {}
                try:
                    retry_after = float(headers.get("Retry-After")) if headers.get("Retry-After") else None
                except (TypeError, ValueError):
                    retry_after = None
                raise ApiTransientError(f"HTTP {status} from upstream.", retry_after=retry_after)
            if status >= 400:
                raise ApiRequestError(f"HTTP {status} from upstream.")
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            raise ApiRequestError(f"HTTP {status or 'error'} from upstream.") from None

    def _parse_response_body(self, response: Any, result_type: str) -> dict[str, Any]:
        """Parse one response body as the requested format, then as the other one. Never re-requests."""
        parsers = [self._parse_json_body, self._parse_xml_body]
        if result_type == "xml":
            parsers.reverse()
        for parser in parsers:
            try:
                payload = parser(response)
            except (ValueError, ParseError, TypeError, AttributeError):
                continue
            if isinstance(payload, dict):
                return payload
        raise ApiRequestError("Upstream response body could not be parsed as JSON or XML.")

    @staticmethod
    def _parse_json_body(response: Any) -> Any:
        return response.json()

    def _parse_xml_body(self, response: Any) -> dict[str, Any]:
        text = getattr(response, "text", None)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("empty body")
        return self._parse_xml_payload(text)

    def _unwrap_rows(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        gateway = payload.get("OpenAPI_ServiceResponse")
        if gateway is not None:
            # data.go.kr gateway envelope: always an error, never data.
            header = gateway.get("cmmMsgHeader", gateway) if isinstance(gateway, dict) else {}
            code = self._normalize_result_code(first_of(header, "returnReasonCode", "resultCode"))
            detail = self._as_str(first_of(header, "returnAuthMsg", "errMsg"))
            self._raise_for_result_code("99" if code == "00" else code, detail)

        if "response" in payload:
            response = payload.get("response", payload)
            header = response.get("header", {})
            result_code = self._normalize_result_code(first_of(header, "resultCode", "code"))
            self._raise_for_result_code(result_code, self._as_str(first_of(header, "resultMsg")))
            body = response.get("body", response)
            return self._coerce_rows(body)

        operation_payload = None
        if len(payload) == 1:
            only_value = next(iter(payload.values()))
            if isinstance(only_value, dict):
                operation_payload = only_value
        if operation_payload is None:
            operation_payload = payload

        raw_code = first_of(operation_payload, "resultCode", "code")
        result_code = self._normalize_result_code(raw_code)
        self._raise_for_result_code(result_code, self._as_str(first_of(operation_payload, "resultMsg")))
        rows = self._coerce_rows(operation_payload)
        if raw_code is None and not rows and not any(
            key in operation_payload for key in ("items", "item", "totalCount", "body")
        ):
            # Neither a result code nor an items container: not an NEC payload, so it must not be cached as [].
            raise ApiRequestError("Upstream response did not contain an NEC result.")
        return rows

    @staticmethod
    def _raise_for_result_code(result_code: str, detail: str | None = None) -> None:
        if result_code in {"00", "03", "None", ""}:
            return
        message = ERROR_MESSAGES.get(result_code) or f"Upstream error {result_code}"
        if detail and detail not in message:
            message = f"{message} ({detail})"
        if result_code in AUTHORIZATION_CODES:
            raise ApiAuthorizationError(message)
        if result_code in NOT_APPLIED_CODES:
            raise ApiNotAppliedError(message)
        if result_code in QUOTA_CODES:
            raise ApiQuotaError(message)
        if result_code in TRANSIENT_CODES:
            raise ApiTransientError(message)
        raise ApiRequestError(message)

    def _coerce_rows(self, body: Any) -> list[dict[str, Any]]:
        items = None
        if isinstance(body, dict):
            items = body.get("items")
            if isinstance(items, dict) and "item" in items:
                items = items.get("item")
            elif items is None and "item" in body:
                items = body.get("item")
        if isinstance(items, list):
            return [row for row in items if isinstance(row, dict)]
        if isinstance(items, dict):
            return [items]
        if isinstance(body, list):
            return [row for row in body if isinstance(row, dict)]
        if isinstance(body, dict) and any(key in body for key in {"sgId", "huboid", "huboNm", "name", "sggName", "jdName"}):
            return [body]
        return []

    @staticmethod
    def _normalize_result_code(value: Any) -> str:
        if value in (None, ""):
            return "00"
        normalized = str(value).strip()
        for prefix in ("INFO-", "ERROR-"):
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):]
        if normalized.isdigit():
            normalized = f"{int(normalized):02d}"
        return normalized

    def _parse_xml_payload(self, xml_text: str) -> dict[str, Any]:
        root = fromstring(xml_text)

        def convert(node: Element) -> Any:
            children = list(node)
            if not children:
                return (node.text or "").strip()
            grouped: dict[str, Any] = {}
            for child in children:
                value = convert(child)
                if child.tag in grouped:
                    existing = grouped[child.tag]
                    if not isinstance(existing, list):
                        grouped[child.tag] = [existing]
                    grouped[child.tag].append(value)
                else:
                    grouped[child.tag] = value
            return grouped

        return {root.tag: convert(root)}

    @staticmethod
    def _build_candidacy_uid(
        sg_id: str,
        sg_typecode: str,
        huboid: str | None,
        candidate_name: str | None,
        party_name: str | None = None,
        sd_name: str | None = None,
        sgg_name: str | None = None,
        wiw_name: str | None = None,
        giho: str | None = None,
    ) -> str:
        if huboid:
            return ":".join([sg_id, sg_typecode, huboid])
        marker_sd_name, marker_sgg_name, marker_wiw_name = NecApiClient._scope_dedupe_location(
            sg_typecode,
            sd_name,
            sgg_name,
            wiw_name,
        )
        return ":".join(
            [
                sg_id,
                sg_typecode,
                normalize_candidate_name(candidate_name),
                map_party_name(party_name or ""),
                normalize_district_name(marker_sd_name),
                normalize_district_name(marker_sgg_name),
                normalize_district_name(marker_wiw_name),
                str(giho or "").strip(),
            ]
        )

    @staticmethod
    def _extract_year(value: str | None) -> int | None:
        if not value:
            return None
        digits = "".join(character for character in value if character.isdigit())
        if len(digits) >= 4:
            return int(digits[:4])
        return None

    @staticmethod
    def _election_row_sort_key(row: dict[str, Any]) -> tuple[str, str, str]:
        election_date = "".join(
            character for character in str(first_of(row, "sgVotedate", "election_date", "voteDate") or "") if character.isdigit()
        )
        sg_id = "".join(character for character in str(first_of(row, "sgId", "sg_id", "sgid") or "") if character.isdigit())
        sg_typecode = str(first_of(row, "sgTypecode", "sg_typecode", "sgtypecode") or "")
        return election_date or sg_id, sg_id, sg_typecode

    @staticmethod
    def _as_bool(value: Any) -> bool | None:
        return as_bool(value)

    @staticmethod
    def _as_int(value: Any) -> int | None:
        return as_int(value)

    @staticmethod
    def _as_str(value: Any) -> str | None:
        return as_str(value)

    @staticmethod
    def _provenance(source_name: str, entity_type: str, source_ref: str | None) -> ProvenanceRecord:
        return ProvenanceRecord(
            source_name=source_name,
            entity_type=entity_type,
            source_ref=source_ref,
            access_method="api",
        )













