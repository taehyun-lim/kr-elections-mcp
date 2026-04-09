from __future__ import annotations

from typing import Any

from .diagnostics import DiagnosticsService
from .krpoltext_api import KrPolTextClient
from .models import (
    AssembleCandidatePacketInput,
    AvailabilityState,
    CandidateLookupInput,
    CandidatePoliciesOutput,
    CandidateProfileOutput,
    CandidateRef,
    CandidateResolution,
    CandidateResult,
    ResolutionStatus,
    CandidatePacket,
    DiagnoseInput,
    DiagnosticsReport,
    DistrictResultsInput,
    DistrictResultsOutput,
    DistrictSummaryOutput,
    ElectionOverviewInput,
    ElectionOverviewOutput,
    KrPolTextInput,
    KrPolTextOutput,
    ListDistrictsInput,
    ListDistrictsOutput,
    ListElectionsInput,
    ListElectionsOutput,
    ListPartiesInput,
    ListPartiesOutput,
    PartyVoteShareHistoryInput,
    PartyVoteShareHistoryOutput,
    SearchCandidatesInput,
    SearchCandidatesOutput,
)
from .nec_api import NecApiClient
from .normalize import canonicalize_district
from .results_api import ResultsApiClient


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
        items = self.nec_client.list_elections(
            sg_typecode=payload.sg_typecode,
            year_from=payload.year_from,
            year_to=payload.year_to,
            include_history=payload.include_history,
        )
        return ListElectionsOutput(items=items)

    def list_districts(self, payload: ListDistrictsInput) -> ListDistrictsOutput:
        """Return normalized districts for a specific election."""
        items = self.nec_client.list_districts(
            sg_id=payload.sg_id,
            sg_typecode=payload.sg_typecode,
            sd_name=payload.sd_name,
            match_mode=payload.match_mode,
        )
        return ListDistrictsOutput(items=items)

    def list_parties(self, payload: ListPartiesInput) -> ListPartiesOutput:
        """Return parties registered for a specific election."""
        items = self.nec_client.list_parties(sg_id=payload.sg_id, sg_typecode=payload.sg_typecode)
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

    def resolve_candidate(self, payload: CandidateLookupInput | AssembleCandidatePacketInput) -> CandidateResolution:
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
        profile = self.nec_client.get_candidate_profile(
            resolution.candidate.candidate_ref,
            include_raw_fields=payload.include_raw_fields,
        )
        return CandidateProfileOutput(resolution=resolution, profile=profile, warnings=resolution.warnings)

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
        items, availability = self.nec_client.get_candidate_policies(resolution.candidate.candidate_ref)
        return CandidatePoliciesOutput(
            resolution=resolution,
            availability=availability,
            items=items,
            warnings=resolution.warnings,
        )

    def get_district_results(self, payload: DistrictResultsInput) -> DistrictResultsOutput:
        """Return ranked candidate results for the requested district."""
        district, items = self.results_client.get_district_results(
            sg_id=payload.sg_id,
            sg_typecode=payload.sg_typecode,
            sd_name=payload.sd_name,
            sgg_name=payload.sgg_name,
            wiw_name=payload.wiw_name,
        )
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
        items = self.results_client.get_party_vote_share_history(
            party_name=payload.party_name,
            district_name=payload.district_name,
            sd_name=payload.sd_name,
            sg_typecode=payload.sg_typecode,
            year_from=payload.year_from,
            year_to=payload.year_to,
        )
        return PartyVoteShareHistoryOutput(items=items)

    def get_election_overview(self, payload: ElectionOverviewInput) -> ElectionOverviewOutput:
        """Return aggregate district, party, winner, and turnout data for an election."""
        overview = self.results_client.get_election_overview(sg_id=payload.sg_id, sg_typecode=payload.sg_typecode)
        return ElectionOverviewOutput(overview=overview, warnings=overview.warnings)



    def get_krpoltext_text(self, payload: KrPolTextInput) -> KrPolTextOutput:
        """Fetch krpoltext records for a candidate or code query."""
        items = self.krpoltext_client.get_text(payload)
        warnings = [] if items else ["No krpoltext records matched the supplied query."]
        return KrPolTextOutput(items=items, warnings=warnings)

    def assemble_candidate_packet(self, payload: AssembleCandidatePacketInput) -> CandidatePacket:
        """Bundle profile, policies, results, and krpoltext into one response."""
        resolution = self.resolve_candidate(payload)
        if resolution.status != ResolutionStatus.RESOLVED or not resolution.candidate:
            return CandidatePacket(
                resolution=resolution,
                warnings=resolution.warnings,
                errors=[resolution.message] if resolution.message else [],
            )

        lookup = CandidateLookupInput(candidate_ref=resolution.candidate.candidate_ref)
        profile_output = self.get_candidate_profile(lookup)
        policy_output = self.get_candidate_policies(lookup)
        profile = profile_output.profile
        result = self.results_client.get_candidate_result(resolution.candidate)

        election_year = self._extract_year(profile.candidate.election_date if profile else resolution.candidate.election_date)
        krpoltext_output = self.get_krpoltext_text(
            KrPolTextInput(
                candidate_name=resolution.candidate.candidate_ref.candidate_name,
                election_year=election_year,
                office_name=resolution.candidate.sg_name,
                district_name=resolution.candidate.candidate_ref.district_label,
            )
        )

        return CandidatePacket(
            resolution=resolution,
            profile=profile,
            policies=policy_output.items,
            policy_availability=policy_output.availability,
            krpoltext=krpoltext_output.items,
            result=result,
            provenance=(profile.provenance if profile else []) + ([result.provenance[0]] if result and result.provenance else []),
            warnings=resolution.warnings + policy_output.warnings + krpoltext_output.warnings,
            errors=profile_output.errors + policy_output.errors,
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


def register_tools(mcp, handlers: ToolHandlers) -> None:
    @mcp.tool
    def list_elections(
        sg_typecode: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        include_history: bool = True,
    ) -> dict[str, Any]:
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
        sg_id: str,
        sg_typecode: str,
        sd_name: str | None = None,
        match_mode: str = "strict",
    ) -> dict[str, Any]:
        return handlers.list_districts(
            ListDistrictsInput(sg_id=sg_id, sg_typecode=sg_typecode, sd_name=sd_name, match_mode=match_mode)
        ).model_dump()

    @mcp.tool
    def list_parties(sg_id: str, sg_typecode: str) -> dict[str, Any]:
        return handlers.list_parties(ListPartiesInput(sg_id=sg_id, sg_typecode=sg_typecode)).model_dump()

    @mcp.tool
    def search_candidates(
        candidate_name: str,
        sg_id: str | None = None,
        sg_typecode: str | None = None,
        sd_name: str | None = None,
        district_name: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
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
        sg_id: str | None = None,
        sg_typecode: str | None = None,
        sd_name: str | None = None,
        district_name: str | None = None,
        party_name: str | None = None,
        giho: str | None = None,
        include_raw_fields: bool = False,
    ) -> dict[str, Any]:
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
        sg_id: str | None = None,
        sg_typecode: str | None = None,
        sd_name: str | None = None,
        district_name: str | None = None,
        party_name: str | None = None,
        giho: str | None = None,
    ) -> dict[str, Any]:
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
        sg_id: str,
        sg_typecode: str,
        sd_name: str,
        sgg_name: str | None = None,
        wiw_name: str | None = None,
    ) -> dict[str, Any]:
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
        sg_id: str,
        sg_typecode: str,
        sd_name: str,
        sgg_name: str | None = None,
        wiw_name: str | None = None,
    ) -> dict[str, Any]:
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
        sd_name: str | None = None,
        sg_typecode: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> dict[str, Any]:
        return handlers.get_party_vote_share_history(
            PartyVoteShareHistoryInput(
                party_name=party_name,
                district_name=district_name,
                sd_name=sd_name,
                sg_typecode=sg_typecode,
                year_from=year_from,
                year_to=year_to,
            )
        ).model_dump()

    @mcp.tool
    def get_election_overview(sg_id: str, sg_typecode: str) -> dict[str, Any]:
        return handlers.get_election_overview(ElectionOverviewInput(sg_id=sg_id, sg_typecode=sg_typecode)).model_dump()

    @mcp.tool
    def assemble_candidate_packet(
        candidate_ref: dict[str, Any] | None = None,
        candidate_name: str | None = None,
        sg_id: str | None = None,
        sg_typecode: str | None = None,
        sd_name: str | None = None,
        district_name: str | None = None,
        party_name: str | None = None,
        giho: str | None = None,
    ) -> dict[str, Any]:
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
        return handlers.diagnose_core_api_access(DiagnoseInput()).model_dump()

    @mcp.tool
    def diagnose_full_api_access(include_optional: bool = True) -> dict[str, Any]:
        return handlers.diagnose_full_api_access(DiagnoseInput(include_optional=include_optional)).model_dump()



    @mcp.tool
    def get_krpoltext_text(
        candidate_name: str | None = None,
        code: str | None = None,
        election_year: int | None = None,
        office_name: str | None = None,
        district_name: str | None = None,
    ) -> dict[str, Any]:
        return handlers.get_krpoltext_text(
            KrPolTextInput(
                candidate_name=candidate_name,
                code=code,
                election_year=election_year,
                office_name=office_name,
                district_name=district_name,
            )
        ).model_dump()





