from __future__ import annotations

from typing import Annotated, Any, Callable, TypeVar

import requests
from pydantic import BeforeValidator, Field

from .campaign_booklet_corpus import canonical_office_name
from .diagnostics import DiagnosticsService
from .errors import ApiRequestError, KrElectionError
from .krpoltext_api import KrPolTextClient
from .krpoltext_matching import (
    decorate_krpoltext_candidate_matches,
    rank_krpoltext_candidate_matches,
    resolve_krpoltext_candidate_match,
)
from .models import (
    AssembleCandidatePacketInput,
    AvailabilityState,
    CandidateLookupInput,
    CandidatePacket,
    CandidatePoliciesOutput,
    CandidateProfileOutput,
    CandidateRef,
    CandidateResolution,
    CandidateResult,
    DiagnoseInput,
    DiagnosticsReport,
    DistrictResultsInput,
    DistrictResultsOutput,
    DistrictSummaryOutput,
    ElectionOverviewInput,
    ElectionOverviewOutput,
    KrPolTextCandidateMatchInput,
    KrPolTextCandidateMatchOutput,
    KrPolTextInput,
    KrPolTextMetaOutput,
    KrPolTextOutput,
    ListDistrictsInput,
    ListDistrictsOutput,
    ListElectionsInput,
    ListElectionsOutput,
    ListPartiesInput,
    ListPartiesOutput,
    PartyVoteShareHistoryInput,
    PartyVoteShareHistoryOutput,
    ResolutionStatus,
    SearchCandidatesInput,
    SearchCandidatesOutput,
)
from .nec_api import NecApiClient
from .normalize import canonicalize_district
from .results_api import ResultsApiClient

T = TypeVar("T")

# krpoltext office keys by NEC election type.
KRPOLTEXT_OFFICE_BY_TYPECODE = {
    "1": "president",
    "2": "national_assembly",
    "3": "regional_head",
    "4": "basic_head",
    "5": "regional_council",
    "6": "basic_council",
    "11": "superintendent",
}


class ToolHandlers:
    def __init__(
        self,
        nec_client: NecApiClient,
        results_client: ResultsApiClient,
        krpoltext_client: KrPolTextClient,
        diagnostics_service: DiagnosticsService,
    ) -> None:
        self.nec_client = nec_client
        self.results_client = results_client
        self.krpoltext_client = krpoltext_client
        self.diagnostics_service = diagnostics_service

    def list_elections(self, payload: ListElectionsInput) -> ListElectionsOutput:
        """Return elections filtered by type and year range."""
        kwargs = {
            "sg_typecode": payload.sg_typecode,
            "year_from": payload.year_from,
            "year_to": payload.year_to,
            "include_history": payload.include_history,
        }
        getter = getattr(self.nec_client, "list_elections_with_warnings", None)
        if callable(getter):
            items, warnings = getter(**kwargs)
            return ListElectionsOutput(items=items, warnings=warnings)
        return ListElectionsOutput(items=self.nec_client.list_elections(**kwargs))

    def list_districts(self, payload: ListDistrictsInput) -> ListDistrictsOutput:
        """Return normalized districts for a specific election."""
        try:
            items = self.nec_client.list_districts(
                sg_id=payload.sg_id,
                sg_typecode=payload.sg_typecode,
                sd_name=payload.sd_name,
                match_mode=payload.match_mode,
            )
        except ApiRequestError as exc:
            fallback = getattr(self.results_client, "list_districts_from_results", None)
            if not callable(fallback):
                raise
            items = fallback(sg_id=payload.sg_id, sg_typecode=payload.sg_typecode, sd_name=payload.sd_name)
            return ListDistrictsOutput(
                items=items,
                warnings=[f"District code list unavailable ({exc}); districts were derived from tally rows."],
            )
        return ListDistrictsOutput(items=items)

    def list_parties(self, payload: ListPartiesInput) -> ListPartiesOutput:
        """Return parties registered for a specific election."""
        try:
            items = self.nec_client.list_parties(sg_id=payload.sg_id, sg_typecode=payload.sg_typecode)
        except ApiRequestError as exc:
            fallback = getattr(self.results_client, "list_parties_from_results", None)
            if not callable(fallback):
                raise
            items = fallback(sg_id=payload.sg_id, sg_typecode=payload.sg_typecode)
            return ListPartiesOutput(
                items=items,
                warnings=[
                    f"Party code list unavailable ({exc}); parties were derived from result rows "
                    "(parties that won no votes are missing)."
                ],
            )
        return ListPartiesOutput(items=items)

    def search_candidates(self, payload: SearchCandidatesInput) -> SearchCandidatesOutput:
        """Search candidates and surface ambiguity warnings when matches cluster."""
        items = self.nec_client.search_candidates(
            candidate_name=payload.candidate_name,
            sg_id=payload.sg_id,
            sg_typecode=payload.sg_typecode,
            sd_name=payload.sd_name,
            district_name=payload.district_name,
            limit=payload.limit,
        )
        warnings = []
        if sum(1 for item in items if item.ambiguity_score) > 1:
            warnings.append("Multiple plausible candidates were found. Resolve with huboid, district, or party.")
        return SearchCandidatesOutput(items=items, warnings=warnings)

    def resolve_candidate(self, payload: CandidateLookupInput | AssembleCandidatePacketInput | KrPolTextCandidateMatchInput) -> CandidateResolution:
        """Resolve a candidate reference or search query into one candidate when possible."""
        candidate_ref = self._coerce_candidate_ref(getattr(payload, "candidate_ref", None))
        return self.nec_client.resolve_candidate(
            candidate_ref=candidate_ref,
            candidate_name=getattr(payload, "candidate_name", None),
            sg_id=getattr(payload, "sg_id", None),
            sg_typecode=getattr(payload, "sg_typecode", None),
            sd_name=getattr(payload, "sd_name", None),
            district_name=getattr(payload, "district_name", None),
            party_name=getattr(payload, "party_name", None),
            giho=getattr(payload, "giho", None),
        )

    def get_candidate_profile(self, payload: CandidateLookupInput) -> CandidateProfileOutput:
        """Resolve a candidate and return the normalized profile payload."""
        resolution = self.resolve_candidate(payload)
        if resolution.status != ResolutionStatus.RESOLVED or not resolution.candidate:
            return CandidateProfileOutput(
                resolution=resolution,
                warnings=resolution.warnings,
                errors=[resolution.message] if resolution.message else [],
            )
        profile, error = self._guard(
            lambda: self.nec_client.get_candidate_profile(
                resolution.candidate.candidate_ref,
                include_raw_fields=payload.include_raw_fields,
            )
        )
        return CandidateProfileOutput(
            resolution=resolution,
            profile=profile,
            warnings=resolution.warnings,
            errors=[error] if error else [],
        )

    def get_candidate_policies(self, payload: CandidateLookupInput) -> CandidatePoliciesOutput:
        """Resolve a candidate and return manifesto entries plus availability metadata."""
        resolution = self.resolve_candidate(payload)
        if resolution.status != ResolutionStatus.RESOLVED or not resolution.candidate:
            return CandidatePoliciesOutput(
                resolution=resolution,
                availability=AvailabilityState.UNKNOWN,
                warnings=resolution.warnings,
                errors=[resolution.message] if resolution.message else [],
            )
        value, error = self._guard(lambda: self.nec_client.get_candidate_policies(resolution.candidate.candidate_ref))
        items, availability = value if value else ([], AvailabilityState.UNKNOWN)
        return CandidatePoliciesOutput(
            resolution=resolution,
            availability=availability,
            items=items,
            warnings=resolution.warnings,
            errors=[error] if error else [],
        )

    def get_district_results(self, payload: DistrictResultsInput) -> DistrictResultsOutput:
        """Return ranked candidate results for the requested district."""
        kwargs = {
            "sg_id": payload.sg_id,
            "sg_typecode": payload.sg_typecode,
            "sd_name": payload.sd_name,
            "sgg_name": payload.sgg_name,
            "wiw_name": payload.wiw_name,
        }
        getter = getattr(self.results_client, "get_district_results_with_warnings", None)
        if callable(getter):
            district, items, warnings = getter(**kwargs)
            return DistrictResultsOutput(district=district, items=items, warnings=warnings)
        district, items = self.results_client.get_district_results(**kwargs)
        return DistrictResultsOutput(district=district, items=items)

    def get_district_summary(self, payload: DistrictResultsInput) -> DistrictSummaryOutput:
        """Return turnout and vote summary metrics for a district."""
        summary = self.results_client.get_district_summary(
            sg_id=payload.sg_id,
            sg_typecode=payload.sg_typecode,
            sd_name=payload.sd_name,
            sgg_name=payload.sgg_name,
            wiw_name=payload.wiw_name,
        )
        return DistrictSummaryOutput(summary=summary, warnings=summary.warnings)

    def get_party_vote_share_history(self, payload: PartyVoteShareHistoryInput) -> PartyVoteShareHistoryOutput:
        """Return district-level vote share history for a party across elections."""
        kwargs = {
            "party_name": payload.party_name,
            "district_name": payload.district_name,
            "sd_name": payload.sd_name,
            "sg_typecode": payload.sg_typecode,
            "year_from": payload.year_from,
            "year_to": payload.year_to,
        }
        if payload.follow_lineage:
            kwargs["follow_lineage"] = True
        getter = getattr(self.results_client, "get_party_vote_share_history_with_warnings", None)
        if callable(getter):
            items, warnings = getter(**kwargs)
            return PartyVoteShareHistoryOutput(items=items, warnings=warnings)
        return PartyVoteShareHistoryOutput(items=self.results_client.get_party_vote_share_history(**kwargs))

    def get_election_overview(self, payload: ElectionOverviewInput) -> ElectionOverviewOutput:
        """Return aggregate district, party, winner, and turnout data for an election."""
        overview = self.results_client.get_election_overview(sg_id=payload.sg_id, sg_typecode=payload.sg_typecode)
        return ElectionOverviewOutput(overview=overview, warnings=overview.warnings)



    def get_krpoltext_text(self, payload: KrPolTextInput) -> KrPolTextOutput:
        """Fetch krpoltext campaign booklet rows by candidate filters or booklet code.

        The managed `campaign_booklet` corpus follows the year coverage advertised by the
        upstream krpoltext manifest. When a direct person query misses, retry once with
        NEC-resolved election scope so candidate queries can use canonical year, office,
        and district labels without the caller orchestrating multiple tools.
        """
        items = self.krpoltext_client.get_text(payload)
        if not items:
            items = self._retry_krpoltext_text_with_resolved_candidate(payload)
        warnings = self._build_krpoltext_warnings(payload, has_items=bool(items))
        return KrPolTextOutput(items=items, warnings=warnings)

    def get_krpoltext_meta(self, payload: KrPolTextInput) -> KrPolTextMetaOutput:
        """Fetch structured krpoltext metadata rows without returning long text bodies."""
        items = self.krpoltext_client.get_metadata(payload)
        if not items:
            items = self._retry_krpoltext_meta_with_resolved_candidate(payload)
        warnings = self._build_krpoltext_warnings(payload, has_items=bool(items))
        return KrPolTextMetaOutput(items=items, warnings=warnings)

    def match_krpoltext_candidate(self, payload: KrPolTextCandidateMatchInput) -> KrPolTextCandidateMatchOutput:
        """Resolve one NEC candidate and conservatively match it against krpoltext metadata."""
        resolution = self.resolve_candidate(payload)
        if resolution.status != ResolutionStatus.RESOLVED or not resolution.candidate:
            return KrPolTextCandidateMatchOutput(
                resolution=resolution,
                status=resolution.status,
                warnings=resolution.warnings,
                errors=[resolution.message] if resolution.message else [],
                message=resolution.message,
            )

        profile = self.nec_client.get_candidate_profile(resolution.candidate.candidate_ref)
        election_year = self._extract_year(profile.candidate.election_date if profile else resolution.candidate.election_date)
        meta_output = self.get_krpoltext_meta(
            KrPolTextInput(
                candidate_name=resolution.candidate.candidate_ref.candidate_name,
                huboid=resolution.candidate.candidate_ref.huboid,
                sg_id=resolution.candidate.candidate_ref.sg_id,
                sg_typecode=resolution.candidate.candidate_ref.sg_typecode,
                election_year=election_year,
                office_name=self._krpoltext_office_name(resolution.candidate),
                district_name=resolution.candidate.candidate_ref.district_label,
                party_name=payload.party_name or resolution.candidate.party_name or resolution.candidate.candidate_ref.party_name,
                limit=payload.limit,
            )
        )
        ranked = rank_krpoltext_candidate_matches(resolution.candidate, profile, meta_output.items)
        status, item, message, match_warnings = resolve_krpoltext_candidate_match(ranked)
        return KrPolTextCandidateMatchOutput(
            resolution=resolution,
            profile=profile,
            status=status,
            item=item,
            items=decorate_krpoltext_candidate_matches(ranked),
            message=message,
            warnings=resolution.warnings + meta_output.warnings + match_warnings,
            errors=[message] if status == ResolutionStatus.NOT_FOUND and message else [],
        )

    def assemble_candidate_packet(self, payload: AssembleCandidatePacketInput) -> CandidatePacket:
        """Bundle profile, policies, results, and krpoltext into one response."""
        resolution = self.resolve_candidate(payload)
        if resolution.status != ResolutionStatus.RESOLVED or not resolution.candidate:
            return CandidatePacket(
                resolution=resolution,
                warnings=resolution.warnings,
                errors=[resolution.message] if resolution.message else [],
            )

        # Each section is fetched for the already-resolved candidate and fails on its own:
        # one broken upstream API must not discard the sections that did work.
        candidate = resolution.candidate
        ref = candidate.candidate_ref
        errors: list[str] = []
        warnings: list[str] = list(resolution.warnings)

        profile, error = self._guard(lambda: self.nec_client.get_candidate_profile(ref))
        if error:
            errors.append(f"profile: {error}")

        policy_value, error = self._guard(lambda: self.nec_client.get_candidate_policies(ref))
        policies, policy_availability = policy_value if policy_value else ([], AvailabilityState.UNKNOWN)
        if error:
            errors.append(f"policies: {error}")

        result = None
        result_getter = getattr(self.results_client, "get_candidate_result_with_warnings", None)
        if callable(result_getter):
            result_value, error = self._guard(lambda: result_getter(candidate))
            if result_value:
                result, result_warnings = result_value
                warnings.extend(f"result: {warning}" for warning in result_warnings)
        else:
            result, error = self._guard(lambda: self.results_client.get_candidate_result(candidate))
        if error:
            errors.append(f"result: {error}")

        election_year = self._extract_year(profile.candidate.election_date if profile else candidate.election_date)
        krpoltext_output, error = self._guard(
            lambda: self.get_krpoltext_text(
                KrPolTextInput(
                    candidate_name=ref.candidate_name,
                    huboid=ref.huboid,
                    sg_id=ref.sg_id,
                    sg_typecode=ref.sg_typecode,
                    election_year=election_year,
                    office_name=self._krpoltext_office_name(candidate),
                    district_name=ref.district_label,
                    party_name=candidate.party_name or ref.party_name,
                )
            )
        )
        if error:
            errors.append(f"krpoltext: {error}")
        if krpoltext_output:
            warnings.extend(krpoltext_output.warnings)

        return CandidatePacket(
            resolution=resolution,
            profile=profile,
            policies=policies,
            policy_availability=policy_availability,
            krpoltext=krpoltext_output.items if krpoltext_output else [],
            result=result,
            provenance=(profile.provenance if profile else []) + ([result.provenance[0]] if result and result.provenance else []),
            warnings=warnings,
            errors=errors,
        )

    def diagnose_core_api_access(self, payload: DiagnoseInput | None = None) -> DiagnosticsReport:
        """Run the core NEC and results access diagnostic checks."""
        return self.diagnostics_service.diagnose_core_api_access()

    def diagnose_full_api_access(self, payload: DiagnoseInput | None = None) -> DiagnosticsReport:
        """Run the full diagnostics suite, including optional integrations."""
        return self.diagnostics_service.diagnose_full_api_access()

    def normalize_district(
        self,
        *,
        sg_id: str,
        sg_typecode: str,
        sd_name: str,
        sgg_name: str | None = None,
        wiw_name: str | None = None,
    ):
        """Normalize district components into the shared District model."""
        return canonicalize_district(sg_id=sg_id, sg_typecode=sg_typecode, sd_name=sd_name, sgg_name=sgg_name, wiw_name=wiw_name)

    def fetch_result_rows(self, *, sg_id: str, sg_typecode: str, sd_name: str | None = None) -> list[dict[str, Any]]:
        """Return raw winner, tally, and file-backed result rows before filtering."""
        return self.results_client.fetch_result_rows(sg_id=sg_id, sg_typecode=sg_typecode, sd_name=sd_name)



    @staticmethod
    def _guard(fn: Callable[[], T]) -> tuple[T | None, str | None]:
        try:
            return fn(), None
        except (KrElectionError, requests.RequestException) as exc:
            return None, str(exc) or type(exc).__name__

    @staticmethod
    def _coerce_candidate_ref(candidate_ref: Any) -> CandidateRef | None:
        if candidate_ref is None:
            return None
        if isinstance(candidate_ref, CandidateRef):
            return candidate_ref
        if isinstance(candidate_ref, dict):
            return CandidateRef(**candidate_ref)
        return None

    @staticmethod
    def _extract_year(value: str | None) -> int | None:
        if not value:
            return None
        digits = "".join(character for character in value if character.isdigit())
        if len(digits) >= 4:
            return int(digits[:4])
        return None

    def _retry_krpoltext_text_with_resolved_candidate(self, payload: KrPolTextInput):
        retry_payload = self._build_krpoltext_retry_payload(payload)
        if retry_payload is None:
            return []
        return self.krpoltext_client.get_text(retry_payload)

    def _retry_krpoltext_meta_with_resolved_candidate(self, payload: KrPolTextInput):
        retry_payload = self._build_krpoltext_retry_payload(payload)
        if retry_payload is None:
            return []
        return self.krpoltext_client.get_metadata(retry_payload)

    def _build_krpoltext_retry_payload(self, payload: KrPolTextInput) -> KrPolTextInput | None:
        if payload.code or not payload.candidate_name:
            return None

        candidate_lookup = self._candidate_lookup_from_krpoltext_input(payload)
        if candidate_lookup is None:
            return None

        resolution = self.resolve_candidate(candidate_lookup)
        if resolution.status != ResolutionStatus.RESOLVED or not resolution.candidate:
            return None

        resolved = resolution.candidate
        return KrPolTextInput(
            candidate_name=resolved.candidate_ref.candidate_name or payload.candidate_name,
            huboid=resolved.candidate_ref.huboid or payload.huboid,
            sg_id=resolved.candidate_ref.sg_id or payload.sg_id,
            sg_typecode=resolved.candidate_ref.sg_typecode or payload.sg_typecode,
            election_year=payload.election_year or self._extract_year(resolved.election_date),
            office_name=self._krpoltext_office_name(resolved) or payload.office_name,
            district_name=resolved.candidate_ref.district_label or payload.district_name,
            party_name=resolved.party_name or resolved.candidate_ref.party_name or payload.party_name,
            limit=payload.limit,
        )

    def _candidate_lookup_from_krpoltext_input(self, payload: KrPolTextInput) -> CandidateLookupInput | None:
        if not payload.candidate_name:
            return None

        sg_typecode = self._infer_sg_typecode_from_office_name(payload.office_name)
        sg_id = self._infer_election_id(payload.election_year, sg_typecode)
        if payload.election_year is not None and sg_typecode and sg_id is None:
            return None

        if not any([sg_id, sg_typecode, payload.district_name, payload.party_name]):
            return None

        return CandidateLookupInput(
            candidate_name=payload.candidate_name,
            sg_id=sg_id,
            sg_typecode=sg_typecode,
            district_name=payload.district_name,
            party_name=payload.party_name,
        )

    def _infer_election_id(self, election_year: int | None, sg_typecode: str | None) -> str | None:
        if election_year is None or not sg_typecode:
            return None
        kwargs = {"sg_typecode": sg_typecode, "year_from": election_year, "year_to": election_year, "include_history": True}
        # Prefer the variant with the built-in calendar fallback: the code API is often unauthorized.
        getter = getattr(self.nec_client, "list_elections_with_warnings", None)
        if callable(getter):
            elections, _ = getter(**kwargs)
        else:
            elections = self.nec_client.list_elections(**kwargs)
        matches = [item for item in elections if self._extract_year(item.election_date) == election_year]
        unique_ids = {item.sg_id for item in matches if item.sg_id}
        if len(unique_ids) == 1:
            return next(iter(unique_ids))
        return None

    @staticmethod
    def _infer_sg_typecode_from_office_name(office_name: str | None) -> str | None:
        office_key = canonical_office_name(office_name)
        if not office_key:
            return None
        return {office: typecode for typecode, office in KRPOLTEXT_OFFICE_BY_TYPECODE.items()}.get(office_key)

    @staticmethod
    def _krpoltext_office_name(candidate) -> str | None:
        # sg_name is the election name; local elections share one ("제8회 전국동시지방선거") that names no office.
        office = KRPOLTEXT_OFFICE_BY_TYPECODE.get(candidate.candidate_ref.sg_typecode or "")
        if office:
            return office
        return candidate.sg_name if canonical_office_name(candidate.sg_name) else None

    def _build_krpoltext_warnings(self, payload: KrPolTextInput, *, has_items: bool) -> list[str]:
        warnings: list[str] = []
        year_from, year_to = self._krpoltext_supported_year_range()
        coverage_label = self._krpoltext_time_coverage()

        if (
            payload.election_year is not None
            and year_from is not None
            and year_to is not None
            and not (year_from <= payload.election_year <= year_to)
        ):
            label = coverage_label or f"{year_from}-{year_to}"
            warnings.append(
                f"The managed krpoltext campaign_booklet corpus currently covers {label}, "
                f"so election_year={payload.election_year} will not match."
            )

        if has_items:
            return warnings

        warnings.append("No krpoltext records matched the supplied query.")
        if not payload.code:
            warnings.append(
                "For candidate queries, use search_candidates or assemble_candidate_packet first "
                "to confirm the election year, office, and district label before retrying."
            )
        return warnings

    def _krpoltext_supported_year_range(self) -> tuple[int | None, int | None]:
        getter = getattr(self.krpoltext_client, "supported_year_range", None)
        if callable(getter):
            return getter()
        return None, None

    def _krpoltext_time_coverage(self) -> str | None:
        getter = getattr(self.krpoltext_client, "time_coverage", None)
        if callable(getter):
            return getter()
        return None


TYPE_CODES_TEXT = (
    "NEC election type code: 1 president, 2 National Assembly (district), 3 metropolitan mayor/governor, "
    "4 local mayor/county head, 5 metropolitan council, 6 local council, 7 National Assembly (proportional), "
    "8 metropolitan council (proportional), 9 local council (proportional), 10 education council, "
    "11 superintendent of education."
)


def _number_to_str(value: Any) -> Any:
    # Clients that drop `anyOf` from optional params send numeric-looking codes as numbers.
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return value


NumericStr = BeforeValidator(_number_to_str)
SgId = Annotated[str, NumericStr, Field(description="NEC election id: the election date as YYYYMMDD, e.g. '20240410'.")]
OptSgId = Annotated[str | None, NumericStr, Field(description="NEC election id (YYYYMMDD), e.g. '20240410'.")]
SgTypecode = Annotated[str, NumericStr, Field(description=TYPE_CODES_TEXT)]
OptSgTypecode = Annotated[str | None, NumericStr, Field(description=TYPE_CODES_TEXT)]
SdName = Annotated[
    str,
    Field(
        description="Province (시·도). Official or short names work: '서울특별시' or '서울', '전북' "
        "(the name valid on election day, e.g. 전라북도 vs 전북특별자치도, is chosen automatically). "
        "Use '전국' for nationwide presidential totals."
    ),
]
OptSdName = Annotated[str | None, Field(description="Province (시·도), e.g. '서울특별시' or '서울'.")]
SggName = Annotated[
    str | None,
    Field(
        description="District (선거구) exactly as NEC names it, e.g. '종로구', '구로구갑', '중구영도구'. "
        "Short forms like '종로' or '사하갑' are resolved; a split district such as '구로구' returns a warning "
        "listing '구로구갑'/'구로구을'. Required for types 2, 4, 5, 6, 10 when the province has several districts."
    ),
]
WiwName = Annotated[
    str | None,
    Field(
        description="Optional sub-area (구·시·군) inside a district that spans several, e.g. '영도구' in '중구영도구'. "
        "Omit it (or pass '합계') for district totals."
    ),
]


def register_tools(mcp, handlers: ToolHandlers) -> None:
    @mcp.tool
    def list_elections(
        sg_typecode: OptSgTypecode = None,
        year_from: int | None = None,
        year_to: int | None = None,
        include_history: bool = True,
    ) -> dict[str, Any]:
        """List NEC elections (sg_id + sg_typecode pairs) filtered by type and year. Falls back to a built-in calendar of regular elections when the NEC code API is unavailable."""
        return handlers.list_elections(
            ListElectionsInput(
                sg_typecode=sg_typecode,
                year_from=year_from,
                year_to=year_to,
                include_history=include_history,
            )
        ).model_dump()

    @mcp.tool
    def list_districts(
        sg_id: SgId,
        sg_typecode: SgTypecode,
        sd_name: OptSdName = None,
        match_mode: str = "strict",
    ) -> dict[str, Any]:
        """List the districts of one election, optionally within a province. Derived from tally rows when the NEC code API is unavailable."""
        return handlers.list_districts(
            ListDistrictsInput(sg_id=sg_id, sg_typecode=sg_typecode, sd_name=sd_name, match_mode=match_mode)
        ).model_dump()

    @mcp.tool
    def list_parties(sg_id: SgId, sg_typecode: SgTypecode) -> dict[str, Any]:
        """List parties of one election. Derived from result rows when the NEC code API is unavailable."""
        return handlers.list_parties(ListPartiesInput(sg_id=sg_id, sg_typecode=sg_typecode)).model_dump()

    @mcp.tool
    def search_candidates(
        candidate_name: str,
        sg_id: OptSgId = None,
        sg_typecode: OptSgTypecode = None,
        sd_name: OptSdName = None,
        district_name: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Search candidates by name, optionally scoped by election, province and district."""
        return handlers.search_candidates(
            SearchCandidatesInput(
                candidate_name=candidate_name,
                sg_id=sg_id,
                sg_typecode=sg_typecode,
                sd_name=sd_name,
                district_name=district_name,
                limit=limit,
            )
        ).model_dump()

    @mcp.tool
    def get_candidate_profile(
        candidate_ref: dict[str, Any] | None = None,
        candidate_name: str | None = None,
        sg_id: OptSgId = None,
        sg_typecode: OptSgTypecode = None,
        sd_name: OptSdName = None,
        district_name: str | None = None,
        party_name: str | None = None,
        giho: Annotated[str | None, NumericStr] = None,
        include_raw_fields: bool = False,
    ) -> dict[str, Any]:
        """Resolve one candidate and return the NEC profile (birthday, job, education, career)."""
        return handlers.get_candidate_profile(
            CandidateLookupInput(
                candidate_ref=handlers._coerce_candidate_ref(candidate_ref),
                candidate_name=candidate_name,
                sg_id=sg_id,
                sg_typecode=sg_typecode,
                sd_name=sd_name,
                district_name=district_name,
                party_name=party_name,
                giho=giho,
                include_raw_fields=include_raw_fields,
            )
        ).model_dump()

    @mcp.tool
    def get_candidate_policies(
        candidate_ref: dict[str, Any] | None = None,
        candidate_name: str | None = None,
        sg_id: OptSgId = None,
        sg_typecode: OptSgTypecode = None,
        sd_name: OptSdName = None,
        district_name: str | None = None,
        party_name: str | None = None,
        giho: Annotated[str | None, NumericStr] = None,
    ) -> dict[str, Any]:
        """Resolve one candidate and return the pledges registered with NEC (up to 10, with title, field and content)."""
        return handlers.get_candidate_policies(
            CandidateLookupInput(
                candidate_ref=handlers._coerce_candidate_ref(candidate_ref),
                candidate_name=candidate_name,
                sg_id=sg_id,
                sg_typecode=sg_typecode,
                sd_name=sd_name,
                district_name=district_name,
                party_name=party_name,
                giho=giho,
            )
        ).model_dump()

    @mcp.tool
    def get_district_results(
        sg_id: SgId,
        sg_typecode: SgTypecode,
        sd_name: SdName,
        sgg_name: SggName = None,
        wiw_name: WiwName = None,
    ) -> dict[str, Any]:
        """Return every candidate of one district with votes, NEC-style vote share (truncated to 2 decimals), rank and winner flag. All numbers come from the NEC district total (합계) row. Check `warnings` when `items` is empty: it explains which district name to pass."""
        return handlers.get_district_results(
            DistrictResultsInput(
                sg_id=sg_id,
                sg_typecode=sg_typecode,
                sd_name=sd_name,
                sgg_name=sgg_name,
                wiw_name=wiw_name,
            )
        ).model_dump()

    @mcp.tool
    def get_district_summary(
        sg_id: SgId,
        sg_typecode: SgTypecode,
        sd_name: SdName,
        sgg_name: SggName = None,
        wiw_name: WiwName = None,
    ) -> dict[str, Any]:
        """Return electorate, turnout, valid/invalid votes, abstentions and turnout rate for one district, all taken from the same NEC total row as get_district_results."""
        return handlers.get_district_summary(
            DistrictResultsInput(
                sg_id=sg_id,
                sg_typecode=sg_typecode,
                sd_name=sd_name,
                sgg_name=sgg_name,
                wiw_name=wiw_name,
            )
        ).model_dump()

    @mcp.tool
    def get_party_vote_share_history(
        party_name: str,
        district_name: str,
        sd_name: OptSdName = None,
        sg_typecode: OptSgTypecode = None,
        year_from: int | None = None,
        year_to: int | None = None,
        follow_lineage: Annotated[
            bool,
            Field(
                description="Also match predecessor/successor parties (e.g. 국민의힘 ← 미래통합당 ← 자유한국당 ← 새누리당 ← 한나라당). "
                "Each point keeps the party name used in that election."
            ),
        ] = False,
    ) -> dict[str, Any]:
        """Return one point per election with a party's votes and share in one district, including elections the party lost. Party names are matched as written at the time (no automatic lineage between renamed parties)."""
        return handlers.get_party_vote_share_history(
            PartyVoteShareHistoryInput(
                party_name=party_name,
                district_name=district_name,
                sd_name=sd_name,
                sg_typecode=sg_typecode,
                year_from=year_from,
                year_to=year_to,
                follow_lineage=follow_lineage,
            )
        ).model_dump()

    @mcp.tool
    def get_election_overview(sg_id: SgId, sg_typecode: SgTypecode) -> dict[str, Any]:
        """Return nationwide aggregates for one election: winners, districts, parties and turnout. When NEC has no nationwide row, totals are summed from district total rows and a warning says so."""
        return handlers.get_election_overview(ElectionOverviewInput(sg_id=sg_id, sg_typecode=sg_typecode)).model_dump()

    @mcp.tool
    def assemble_candidate_packet(
        candidate_ref: dict[str, Any] | None = None,
        candidate_name: str | None = None,
        sg_id: OptSgId = None,
        sg_typecode: OptSgTypecode = None,
        sd_name: OptSdName = None,
        district_name: str | None = None,
        party_name: str | None = None,
        giho: Annotated[str | None, NumericStr] = None,
    ) -> dict[str, Any]:
        """Resolve one candidate and bundle profile, pledges, own district result and krpoltext booklet text. Sections fail independently; failures are listed in `errors`."""
        return handlers.assemble_candidate_packet(
            AssembleCandidatePacketInput(
                candidate_ref=handlers._coerce_candidate_ref(candidate_ref),
                candidate_name=candidate_name,
                sg_id=sg_id,
                sg_typecode=sg_typecode,
                sd_name=sd_name,
                district_name=district_name,
                party_name=party_name,
                giho=giho,
            )
        ).model_dump()

    @mcp.tool
    def diagnose_core_api_access() -> dict[str, Any]:
        """Check which NEC APIs the configured key can reach (code, candidate, winner and tally APIs)."""
        return handlers.diagnose_core_api_access(DiagnoseInput()).model_dump()

    @mcp.tool
    def diagnose_full_api_access(include_optional: bool = True) -> dict[str, Any]:
        """Run diagnose_core_api_access plus the turnout API check."""
        return handlers.diagnose_full_api_access(DiagnoseInput(include_optional=include_optional)).model_dump()



    @mcp.tool
    def get_krpoltext_text(
        candidate_name: str | None = None,
        code: str | None = None,
        huboid: Annotated[str | None, NumericStr] = None,
        sg_id: OptSgId = None,
        sg_typecode: OptSgTypecode = None,
        election_year: int | None = None,
        office_name: str | None = None,
        district_name: str | None = None,
        party_name: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Fetch krpoltext campaign booklet text by booklet code or candidate filters."""
        return handlers.get_krpoltext_text(
            KrPolTextInput(
                candidate_name=candidate_name,
                code=code,
                huboid=huboid,
                sg_id=sg_id,
                sg_typecode=sg_typecode,
                election_year=election_year,
                office_name=office_name,
                district_name=district_name,
                party_name=party_name,
                limit=limit,
            )
        ).model_dump()

    @mcp.tool
    def get_krpoltext_meta(
        candidate_name: str | None = None,
        code: str | None = None,
        huboid: Annotated[str | None, NumericStr] = None,
        sg_id: OptSgId = None,
        sg_typecode: OptSgTypecode = None,
        election_year: int | None = None,
        office_name: str | None = None,
        district_name: str | None = None,
        party_name: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Fetch krpoltext campaign booklet metadata (no long text bodies)."""
        return handlers.get_krpoltext_meta(
            KrPolTextInput(
                candidate_name=candidate_name,
                code=code,
                huboid=huboid,
                sg_id=sg_id,
                sg_typecode=sg_typecode,
                election_year=election_year,
                office_name=office_name,
                district_name=district_name,
                party_name=party_name,
                limit=limit,
            )
        ).model_dump()

    @mcp.tool
    def match_krpoltext_candidate(
        candidate_ref: dict[str, Any] | None = None,
        candidate_name: str | None = None,
        sg_id: OptSgId = None,
        sg_typecode: OptSgTypecode = None,
        sd_name: OptSdName = None,
        district_name: str | None = None,
        party_name: str | None = None,
        giho: Annotated[str | None, NumericStr] = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Resolve one NEC candidate and conservatively match it to krpoltext metadata."""
        return handlers.match_krpoltext_candidate(
            KrPolTextCandidateMatchInput(
                candidate_ref=handlers._coerce_candidate_ref(candidate_ref),
                candidate_name=candidate_name,
                sg_id=sg_id,
                sg_typecode=sg_typecode,
                sd_name=sd_name,
                district_name=district_name,
                party_name=party_name,
                giho=giho,
                limit=limit,
            )
        ).model_dump()

