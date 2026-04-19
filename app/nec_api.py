from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import quote
from xml.etree.ElementTree import Element, ParseError

from defusedxml.ElementTree import fromstring

import requests

from .cache import SimpleFileCache
from .coerce import as_bool, as_int, as_str
from .config import Settings
from .errors import (
    ApiAuthorizationError,
    ApiNotAppliedError,
    ApiRequestError,
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
    similarity,
)
from .redact import redact_api_key

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

ERROR_MESSAGES = {
    "00": None,
    "03": "No data returned.",
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
        matches = [
            item
            for item in self.list_elections(include_history=True)
            if item.sg_id == sg_id and item.sg_typecode == sg_typecode
        ]
        return matches[0] if matches else None

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
            if sd_name and row_sd_name and similarity(row_sd_name, sd_name) < 0.8:
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
        parsed = [self._candidate_from_row(row) for row in rows]
        query_norm = normalize_candidate_name(candidate_name)
        same_name_count = sum(
            1 for item in parsed if normalize_candidate_name(item.candidate_ref.candidate_name) == query_norm
        )
        items: list[Candidate] = []
        for item in parsed:
            if sg_id and item.candidate_ref.sg_id != sg_id:
                continue
            if sg_typecode and item.candidate_ref.sg_typecode != sg_typecode:
                continue
            if sd_name and similarity(item.candidate_ref.sd_name, sd_name) < 0.8:
                continue

            score = candidate_name_similarity(item.candidate_ref.candidate_name, candidate_name)
            if district_name:
                item_district_norm = normalize_district_name(item.candidate_ref.district_label)
                query_district_norm = normalize_district_name(district_name)
                district_score = similarity(item.candidate_ref.district_label, district_name)
                if (
                    query_district_norm != item_district_norm
                    and query_district_norm not in item_district_norm
                    and item_district_norm not in query_district_norm
                    and district_score < 0.9
                ):
                    continue
            if score < 0.55:
                continue
            item.ambiguity_score = 1.0 if same_name_count > 1 else 0.0
            items.append(item)
        items.sort(
            key=lambda candidate: (
                candidate_name_similarity(candidate.candidate_ref.candidate_name, candidate_name),
                1 if candidate.is_winner else 0,
            ),
            reverse=True,
        )
        return items[:limit]

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
            scoped_rows = self._fetch_candidate_scope_rows(
                sg_id=sg_id,
                sg_typecode=sg_typecode,
                sd_name=sd_name,
            )
            if scoped_rows:
                return scoped_rows
            name_rows = self._request_paginated_rows(
                "candidate_search_name",
                {
                    "name": candidate_name,
                },
                max_pages=20,
            )
            if any(self._row_matches_search_scope(row, sg_id=sg_id, sg_typecode=sg_typecode, sd_name=sd_name) for row in name_rows):
                return name_rows
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
        election = self.get_election(sg_id, sg_typecode)
        winner_rows = self.fetch_winner_rows(sg_id=sg_id, sg_typecode=sg_typecode, sd_name=sd_name)
        tally_rows = self.fetch_tally_rows(sg_id=sg_id, sg_typecode=sg_typecode, sd_name=sd_name)

        rows: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()

        for row in winner_rows:
            enriched = {
                **row,
                "sgName": first_of(row, "sgName", "elctNm") or (election.sg_name if election else None),
                "elctNm": first_of(row, "elctNm", "sgName") or (election.sg_name if election else None),
                "sgVotedate": first_of(row, "sgVotedate", "voteDate") or (election.election_date if election else sg_id),
                "winnerYn": first_of(row, "winnerYn", "elcoYn") or "Y",
            }
            marker = self._candidate_row_marker(enriched)
            if marker not in seen:
                seen.add(marker)
                rows.append(enriched)

        if not tally_rows:
            return rows

        winner_names = {
            normalize_candidate_name(self._as_str(first_of(row, "name", "huboNm")) or "")
            for row in winner_rows
            if self._as_str(first_of(row, "name", "huboNm"))
        }
        for tally_row in tally_rows:
            for candidate_row in self._expand_candidate_slot_rows(
                tally_row,
                sg_id=sg_id,
                sg_typecode=sg_typecode,
                election_name=election.sg_name if election else None,
                election_date=election.election_date if election else None,
                winner_names=winner_names,
            ):
                marker = self._candidate_row_marker(candidate_row)
                if marker not in seen:
                    seen.add(marker)
                    rows.append(candidate_row)
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
            if row_sd_name and similarity(row_sd_name, sd_name) < 0.8:
                return False
        return True

    def _select_candidate_slot_row(
        self,
        rows: list[dict[str, Any]],
        *,
        sd_name: str | None = None,
    ) -> dict[str, Any] | None:
        if not rows:
            return None
        if sd_name:
            for row in rows:
                row_sd_name = self._as_str(first_of(row, "sdName", "sd_name"))
                if row_sd_name and similarity(row_sd_name, sd_name) >= 0.8:
                    return row
        for row in rows:
            if any(self._as_str(row.get(f"hbj{index:02d}")) for index in range(1, 51)):
                return row
        return rows[0]

    def _expand_candidate_slot_rows(
        self,
        row: dict[str, Any],
        *,
        sg_id: str,
        sg_typecode: str,
        election_name: str | None,
        election_date: str | None,
        winner_names: set[str],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        sd_name = self._as_str(first_of(row, "sdName", "sd_name"))
        sgg_name = self._as_str(first_of(row, "sggName", "sgg_name"))
        wiw_name = self._as_str(first_of(row, "wiwName", "wiw_name"))
        if sd_name == "합계" and sgg_name == "비례대표":
            sd_name = "전국"
            sgg_name = None
            wiw_name = None
        for index in range(1, 51):
            slot = f"{index:02d}"
            candidate_name = self._as_str(row.get(f"hbj{slot}"))
            party_name = self._as_str(row.get(f"jd{slot}"))
            vote_count = self._as_str(row.get(f"dugsu{slot}"))
            if not candidate_name:
                continue
            normalized_name = normalize_candidate_name(candidate_name)
            rows.append(
                {
                    "sgId": sg_id,
                    "sgTypecode": sg_typecode,
                    "sgName": election_name,
                    "elctNm": election_name,
                    "sgVotedate": election_date or sg_id,
                    "name": candidate_name,
                    "huboNm": candidate_name,
                    "jdName": party_name,
                    "dugsu": vote_count,
                    "giho": str(index),
                    "sdName": sd_name,
                    "sggName": sgg_name,
                    "wiwName": wiw_name,
                    "winnerYn": "Y" if normalized_name in winner_names else "N",
                    "elcoYn": "Y" if normalized_name in winner_names else "N",
                }
            )
        return rows

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
            self._as_str(first_of(row, "giho", "num")) or "",
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
        if candidate_ref.sd_name and row_sd_name and similarity(row_sd_name, candidate_ref.sd_name) < 0.8:
            return False

        row_sgg_name = self._as_str(first_of(row, "sggName", "sgg_name"))
        if candidate_ref.sgg_name and row_sgg_name and similarity(row_sgg_name, candidate_ref.sgg_name) < 0.8:
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
        giho = self._as_str(first_of(row, "giho", "num"))
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
        if district_name and similarity(candidate.candidate_ref.district_label, district_name) < 0.7:
            return False
        if party_name and similarity(candidate.party_name, party_name) < 0.9:
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
        seen_batch_signatures: set[str] = set()
        for page_no in range(1, max_pages + 1):
            batch = self._request_rows(
                service_key,
                {**base_params, "pageNo": page_no, "numOfRows": page_size},
            )
            if not batch:
                break
            batch_signature = json.dumps(batch, ensure_ascii=False, sort_keys=True)
            if batch_signature in seen_batch_signatures:
                break
            seen_batch_signatures.add(batch_signature)
            rows.extend(batch)
            if len(batch) < page_size:
                break
        return rows

    def _request_rows(self, service_key: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        service_name, operation_name = SERVICE_SPECS[service_key]
        clean_params = {key: value for key, value in params.items() if value not in (None, "")}
        cache_key = json.dumps([service_key, clean_params], ensure_ascii=False, sort_keys=True)
        return self.cache.remember(cache_key, lambda: self._perform_request(service_name, operation_name, clean_params), ttl_seconds=self.settings.cache_ttl_seconds)

    def _perform_request(
        self,
        service_name: str,
        operation_name: str,
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        key_candidates = self.settings.require_api_keys()
        url = f"{self.settings.nec_api_base_url.rstrip('/')}/{service_name}/{operation_name}"

        last_error: Exception | None = None
        last_key_error: Exception | None = None
        for attempt in range(1, self.settings.retry_attempts + 1):
            saw_transport_error = False
            for key_candidate in key_candidates:
                try:
                    return self._perform_request_with_key(
                        url=url,
                        params=params,
                        key_value=key_candidate.value,
                        key_format=key_candidate.key_format,
                    )
                except (ApiAuthorizationError, ApiNotAppliedError) as exc:
                    last_key_error = exc
                    continue
                except requests.RequestException as exc:
                    last_error = exc
                    saw_transport_error = True
                    break
            if saw_transport_error and attempt < self.settings.retry_attempts:
                time.sleep(self.settings.retry_backoff_seconds * attempt)
                continue
            break
        if last_key_error is not None:
            raise last_key_error
        raise ApiRequestError(
            redact_api_key(
                f"Request failed for {service_name}/{operation_name}: {last_error}",
                known_values=[candidate.value for candidate in key_candidates],
            )
        )

    def _perform_request_with_key(
        self,
        *,
        url: str,
        params: dict[str, Any],
        key_value: str,
        key_format: str,
    ) -> list[dict[str, Any]]:
        preferred_format = self.settings.nec_result_format
        fallback_format = "xml" if preferred_format == "json" else "json"
        for index, result_type in enumerate((preferred_format, fallback_format)):
            response = self.session.get(
                self._build_request_url(url, params, key_value=key_value, key_format=key_format, result_type=result_type),
                headers=self.settings.request_headers(),
                timeout=self.settings.request_timeout_seconds,
            )
            response.raise_for_status()
            try:
                if result_type == "json":
                    return self._unwrap_rows(response.json())
                return self._unwrap_rows(self._parse_xml_payload(response.text))
            except (ValueError, ParseError):
                if index == 1:
                    raise
        return []

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

    def _unwrap_rows(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        if "response" in payload:
            response = payload.get("response", payload)
            header = response.get("header", {})
            result_code = self._normalize_result_code(first_of(header, "resultCode", "code"))
            message = ERROR_MESSAGES.get(result_code)
            if result_code in {"20", "30", "31", "32"}:
                raise ApiAuthorizationError(message or "Unauthorized API access.")
            if result_code == "12":
                raise ApiNotAppliedError(message or "The requested API is not available to this key.")
            if result_code not in {"00", "03", "None", ""}:
                raise ApiRequestError(message or f"Upstream error {result_code}")
            body = response.get("body", response)
            return self._coerce_rows(body)

        operation_payload = None
        if len(payload) == 1:
            only_value = next(iter(payload.values()))
            if isinstance(only_value, dict):
                operation_payload = only_value
        if operation_payload is None:
            operation_payload = payload

        result_code = self._normalize_result_code(first_of(operation_payload, "resultCode", "code"))
        message = ERROR_MESSAGES.get(result_code)
        if result_code in {"20", "30", "31", "32"}:
            raise ApiAuthorizationError(message or "Unauthorized API access.")
        if result_code == "12":
            raise ApiNotAppliedError(message or "The requested API is not available to this key.")
        if result_code not in {"00", "03", "None", ""}:
            raise ApiRequestError(message or f"Upstream error {result_code}")
        return self._coerce_rows(operation_payload)

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
        if normalized.startswith("INFO-"):
            return normalized.split("-", 1)[1]
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













