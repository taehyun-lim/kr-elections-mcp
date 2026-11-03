from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar

from .coerce import as_float, as_int, as_str
from .config import Settings
from .district_resolver import DistrictMatch, DistrictResolution, resolve_district_name
from .errors import ApiAuthorizationError, ApiQuotaError, ApiRequestError, ConfigurationError
from .geo import resolve_sido, sido_key, sido_request_names, split_sido_prefix
from .models import (
    Candidate,
    CandidateRef,
    CandidateResult,
    District,
    DistrictSummary,
    Election,
    ElectionOverview,
    Party,
    PartyVoteSharePoint,
    ProvenanceRecord,
)
from .nec_api import NecApiClient
from .normalize import (
    build_district_label,
    canonicalize_district,
    first_of,
    map_party_name,
    normalize_candidate_name,
    normalize_party_name,
    normalize_text,
    party_match_keys,
)
from .scope import requires_sgg_name, scope_rule
from .tally import (
    TOTAL_WIW_NAME,
    AreaRow,
    DistrictTally,
    build_district_tallies,
    district_key,
    expand_tally_row,
    is_wide_tally_row,
    match_winners,
    nec_share,
    ranked,
    turnout_rate,
)

T = TypeVar("T")

NATIONAL_SD_NAMES = {normalize_text(name) for name in ("전국", "합계", "대한민국")}
MAX_HISTORY_ELECTIONS = 12
SHARE_TOLERANCE = 0.005


@dataclass
class DistrictSelection:
    """One resolved contest: the rows that belong to it and nothing else."""

    sg_id: str
    sg_typecode: str
    sd_name: str | None
    requested_sgg_name: str | None
    tally: DistrictTally | None = None
    area: AreaRow | None = None
    coverage_scope: str = "district_rollup"
    winner_rows: list[dict[str, Any]] = field(default_factory=list)
    winners_available: bool = False
    winner_rows_in_scope: int = 0
    resolution: DistrictResolution | None = None
    available_districts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def confidence(self) -> float:
        if self.resolution and self.resolution.confidence is not None:
            return self.resolution.confidence
        return 1.0

    @property
    def method(self) -> str:
        if self.resolution and self.resolution.method:
            return f"district:{self.resolution.method}"
        return "district:exact"


class ResultsApiClient:
    def __init__(
        self,
        settings: Settings,
        nec_client: NecApiClient,
        *,
        file_result_provider: Callable[[str, str, str | None], list[dict[str, Any]]] | None = None,
    ) -> None:
        self.settings = settings
        self.nec_client = nec_client
        self.file_result_provider = file_result_provider

    # ------------------------------------------------------------------ raw rows

    def fetch_result_rows(
        self,
        *,
        sg_id: str,
        sg_typecode: str,
        sd_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Collect winner, tally, and optional file-backed result rows for one election scope (unfiltered)."""
        rows: list[dict[str, Any]] = []
        for row in self.nec_client.fetch_winner_rows(sg_id=sg_id, sg_typecode=sg_typecode, sd_name=sd_name):
            rows.append({**row, "_result_source": "winner_api", "_coverage_scope": "winner_only"})
        for row in self.nec_client.fetch_tally_rows(sg_id=sg_id, sg_typecode=sg_typecode, sd_name=sd_name):
            rows.append({**row, "_result_source": "tally_api", "_coverage_scope": "all_candidates"})
        if self.file_result_provider:
            for row in self.file_result_provider(sg_id, sg_typecode, sd_name):
                rows.append({**row, "_result_source": "file_data", "_coverage_scope": "all_candidates"})
        return rows

    # ---------------------------------------------------------------- selection

    def select_district(
        self,
        *,
        sg_id: str,
        sg_typecode: str,
        sd_name: str | None,
        sgg_name: str | None = None,
        wiw_name: str | None = None,
        strict: bool = False,
    ) -> DistrictSelection:
        """Resolve one contest and keep only the tally and winner rows that belong to it."""
        sd_input = as_str(sd_name)
        sgg_input = as_str(sgg_name)
        if sgg_input:
            prefix, rest = split_sido_prefix(sgg_input)
            if prefix and rest:
                sd_input = sd_input or prefix
                sgg_input = rest
        elif sd_input:
            prefix, rest = split_sido_prefix(sd_input)
            if prefix and rest:
                sd_input, sgg_input = prefix, rest

        national = sd_input is None or normalize_text(sd_input) in NATIONAL_SD_NAMES
        nec_sd_name = None if national else resolve_sido(sd_input, sg_id)
        selection = DistrictSelection(
            sg_id=sg_id,
            sg_typecode=sg_typecode,
            sd_name=nec_sd_name,
            requested_sgg_name=sgg_input,
        )
        rule = scope_rule(sg_typecode)

        request_names: list[str | None] = [None] if national else sido_request_names(sd_input, sg_id)
        tally_rows, tally_error = self._fetch_first_nonempty(
            lambda name: self.nec_client.fetch_tally_rows(sg_id=sg_id, sg_typecode=sg_typecode, sd_name=name),
            request_names,
        )
        winner_names = [None] if national or rule.level == "national" else request_names
        winner_rows, winner_error = self._fetch_first_nonempty(
            lambda name: self.nec_client.fetch_winner_rows(sg_id=sg_id, sg_typecode=sg_typecode, sd_name=name),
            winner_names,
        )
        if tally_error and winner_error:
            raise tally_error
        if tally_error:
            selection.warnings.append(f"Tally API failed ({self._short(tally_error)}); only winners are available.")
        if winner_error:
            selection.warnings.append(f"Winner API failed ({self._short(winner_error)}); winners are not marked.")
        selection.winners_available = winner_error is None
        selection.winner_rows_in_scope = len(winner_rows)

        wanted_sido = None if national else sido_key(sd_input)
        tally_rows = [
            row
            for row in tally_rows
            if is_wide_tally_row(row)
            and (wanted_sido is None or sido_key(as_str(first_of(row, "sdName", "sd_name"))) == wanted_sido)
        ]
        tallies = build_district_tallies(tally_rows)
        selection.available_districts = [tally.sgg_name for tally in tallies.values() if tally.sgg_name]

        tally = self._choose_tally(selection, tallies, sgg_input, wiw_name, rule_level=rule.level, strict=strict)
        if tally is None:
            if not tallies and not tally_error:
                selection.warnings.append(
                    f"No tally rows were returned for {sg_id}/{sg_typecode}"
                    + (f" in {nec_sd_name}." if nec_sd_name else ".")
                )
            return selection

        selection.tally = tally
        selection.sd_name = tally.sd_name or nec_sd_name
        selection.warnings.extend(tally.warnings)
        self._choose_area(selection, tally, wiw_name)
        if rule.level == "national":
            selection.winner_rows = list(winner_rows)
        else:
            selection.winner_rows = [
                row
                for row in winner_rows
                if district_key(as_str(first_of(row, "sdName", "sd_name")), as_str(first_of(row, "sggName", "sgg_name")))
                == tally.key
            ]
        return selection

    def _choose_tally(
        self,
        selection: DistrictSelection,
        tallies: dict[tuple[str, str], DistrictTally],
        sgg_input: str | None,
        wiw_name: str | None,
        *,
        rule_level: str,
        strict: bool,
    ) -> DistrictTally | None:
        by_name = {normalize_text(tally.sgg_name): tally for tally in tallies.values()}
        query = sgg_input
        if not query and wiw_name and len(tallies) > 1 and rule_level in {"sgg", "wiw"}:
            query = wiw_name
        if query:
            resolution = resolve_district_name(query, [tally.sgg_name for tally in tallies.values()], strict=strict)
            selection.resolution = resolution
            selection.warnings.extend(resolution.warnings)
            if resolution.status != DistrictMatch.RESOLVED:
                return None
            return by_name.get(normalize_text(resolution.name))
        if len(tallies) == 1:
            return next(iter(tallies.values()))
        if not tallies:
            return None
        if rule_level in {"national", "sido"}:
            sido_level = [
                tally
                for tally in tallies.values()
                if sido_key(tally.sgg_name) == sido_key(tally.sd_name) or self._is_national_tally(tally)
            ]
            if len(sido_level) == 1:
                return sido_level[0]
        names = selection.available_districts
        preview = ", ".join(names[:10]) + (" ..." if len(names) > 10 else "")
        selection.warnings.append(
            f"{len(tallies)} districts exist in this province; pass sgg_name to choose one ({preview})."
        )
        return None

    @staticmethod
    def _is_national_tally(tally: DistrictTally) -> bool:
        return normalize_text(tally.sgg_name) in NATIONAL_SD_NAMES or normalize_text(tally.sd_name) in NATIONAL_SD_NAMES

    @staticmethod
    def _choose_area(selection: DistrictSelection, tally: DistrictTally, wiw_name: str | None) -> None:
        wanted = normalize_text(wiw_name)
        if not wanted or wanted in {normalize_text(TOTAL_WIW_NAME), normalize_text(tally.sgg_name)}:
            selection.area = tally.rollup
            selection.coverage_scope = "district_rollup"
            return
        sub = tally.find_sub(wiw_name)
        if sub is None:
            selection.area = tally.rollup
            selection.coverage_scope = "district_rollup"
            options = ", ".join(sub.wiw_name for sub in tally.subs if sub.wiw_name)
            selection.warnings.append(
                f"Sub-area '{wiw_name}' was not found in {tally.sgg_name}; district totals are shown"
                + (f" (sub-areas: {options})." if options else ".")
            )
            return
        selection.area = sub
        selection.coverage_scope = "sub_area"
        rollup = tally.rollup
        if len(tally.subs) == 1 and sub.valid == rollup.valid and normalize_text(sub.wiw_name) != normalize_text(tally.sgg_name):
            selection.warnings.append(
                f"NEC reports all of {tally.sgg_name} under {sub.wiw_name} "
                "(관할 구시군 기준); the figures cover the whole district, not only that area."
            )

    def _fetch_first_nonempty(
        self,
        fetch: Callable[[str | None], list[dict[str, Any]]],
        names: list[str | None],
    ) -> tuple[list[dict[str, Any]], ApiRequestError | ConfigurationError | None]:
        error: ApiRequestError | ConfigurationError | None = None
        for name in names:
            try:
                rows = fetch(name)
            except (ApiRequestError, ConfigurationError) as exc:
                error = exc
                if isinstance(exc, (ApiAuthorizationError, ApiQuotaError, ConfigurationError)):
                    break
                continue
            if rows:
                return rows, None
            error = None
        return [], error

    # ------------------------------------------------------------------ results

    def _build_results(self, selection: DistrictSelection) -> tuple[list[CandidateResult], list[str]]:
        if selection.tally is None or selection.area is None:
            return [], []
        warnings: list[str] = []
        tally = selection.tally
        area = selection.area
        rule = scope_rule(selection.sg_typecode)
        matched = match_winners(area.slots, selection.winner_rows, has_party=rule.has_party)
        unplaced = len(selection.winner_rows) - len(matched)
        if unplaced > 0 and rule.level != "national":
            warnings.append(f"{unplaced} winner row(s) could not be matched to a tally slot.")
        winners_known = selection.winners_available
        if winners_known and not matched and selection.winner_rows_in_scope and rule.level != "national":
            # Winners exist in the province but none belongs to this district: do not claim everyone lost.
            winners_known = False
            warnings.append("No winner row matched this district; is_winner is left unknown.")
        wiw_label = area.wiw_name if selection.coverage_scope == "sub_area" else None
        district_label = build_district_label(tally.sd_name, tally.sgg_name, wiw_label)
        results: list[CandidateResult] = []
        for rank, slot in ranked(area.slots):
            winner = matched.get(slot.ballot_position)
            huboid = as_str(first_of(winner, "huboid", "huboId")) if winner else None
            giho = as_str(first_of(winner, "giho")) if winner else None
            share = nec_share(slot.votes, area.valid)
            if winner and selection.coverage_scope == "district_rollup":
                published = as_float(first_of(winner, "dugyul"))
                if published is not None:
                    if share is not None and abs(published - share) >= SHARE_TOLERANCE:
                        warnings.append(
                            f"{slot.name}: NEC published share {published} differs from computed {share}."
                        )
                    share = published
            if winners_known:
                is_winner: bool | None = winner is not None
            else:
                is_winner = None
            ref = CandidateRef(
                candidacy_uid=NecApiClient._build_candidacy_uid(
                    selection.sg_id,
                    selection.sg_typecode,
                    huboid,
                    slot.name,
                    slot.party,
                    tally.sd_name,
                    tally.sgg_name,
                    None,
                    giho,
                ),
                huboid=huboid,
                sg_id=selection.sg_id,
                sg_typecode=selection.sg_typecode,
                candidate_name=slot.name,
                sd_name=tally.sd_name,
                sgg_name=tally.sgg_name,
                wiw_name=wiw_label,
                district_label=district_label,
                party_name=slot.party,
                giho=giho,
            )
            raw = {
                "sdName": area.sd_name,
                "sggName": area.sgg_name,
                "wiwName": area.wiw_name,
                "slot": f"{slot.ballot_position:02d}",
                "hbj": slot.name,
                "jd": slot.party,
                "dugsu": slot.votes,
                "yutusu": area.valid,
            }
            if winner:
                raw["winner"] = {
                    key: winner.get(key)
                    for key in ("huboid", "giho", "gihoSangse", "name", "jdName", "dugsu", "dugyul")
                    if key in winner
                }
            results.append(
                CandidateResult(
                    candidate_ref=ref,
                    candidate_name=slot.name,
                    party_name=slot.party,
                    giho=giho,
                    giho_detail=as_str(first_of(winner, "gihoSangse")) if winner else None,
                    ballot_position=slot.ballot_position,
                    district_label=district_label,
                    vote_count=slot.votes,
                    vote_share=share,
                    valid_vote_count=area.valid,
                    rank_in_district=rank,
                    is_winner=is_winner,
                    result_source="tally_api",
                    coverage_scope=selection.coverage_scope,
                    match_method=selection.method,
                    match_confidence=round(selection.confidence, 3),
                    provenance=[self._provenance("nec_results", "candidate_result", ref.candidacy_uid)],
                    raw_fields=raw,
                )
            )
        return results, warnings

    def _selection_district(self, selection: DistrictSelection, *, sd_name: str | None, sgg_name: str | None, wiw_name: str | None) -> District:
        if selection.tally is None:
            return canonicalize_district(
                sg_id=selection.sg_id,
                sg_typecode=selection.sg_typecode,
                sd_name=selection.sd_name or sd_name,
                sgg_name=selection.requested_sgg_name or sgg_name,
                wiw_name=wiw_name,
            )
        wiw = selection.area.wiw_name if selection.coverage_scope == "sub_area" and selection.area else None
        return canonicalize_district(
            sg_id=selection.sg_id,
            sg_typecode=selection.sg_typecode,
            sd_name=selection.tally.sd_name,
            sgg_name=selection.tally.sgg_name,
            wiw_name=wiw,
        )

    def get_district_results_with_warnings(
        self,
        *,
        sg_id: str,
        sg_typecode: str,
        sd_name: str,
        sgg_name: str | None = None,
        wiw_name: str | None = None,
    ) -> tuple[District, list[CandidateResult], list[str]]:
        selection = self.select_district(
            sg_id=sg_id, sg_typecode=sg_typecode, sd_name=sd_name, sgg_name=sgg_name, wiw_name=wiw_name
        )
        results, result_warnings = self._build_results(selection)
        district = self._selection_district(selection, sd_name=sd_name, sgg_name=sgg_name, wiw_name=wiw_name)
        return district, results, _dedupe(selection.warnings + result_warnings)

    def get_district_results(
        self,
        *,
        sg_id: str,
        sg_typecode: str,
        sd_name: str,
        sgg_name: str | None = None,
        wiw_name: str | None = None,
    ) -> tuple[District, list[CandidateResult]]:
        """Return ranked candidate results for one normalized district."""
        district, results, _ = self.get_district_results_with_warnings(
            sg_id=sg_id, sg_typecode=sg_typecode, sd_name=sd_name, sgg_name=sgg_name, wiw_name=wiw_name
        )
        return district, results

    # ------------------------------------------------------------------ summary

    def get_district_summary(
        self,
        *,
        sg_id: str,
        sg_typecode: str,
        sd_name: str,
        sgg_name: str | None = None,
        wiw_name: str | None = None,
    ) -> DistrictSummary:
        """Return turnout and vote summary metrics for one district, all from one NEC row."""
        selection = self.select_district(
            sg_id=sg_id, sg_typecode=sg_typecode, sd_name=sd_name, sgg_name=sgg_name, wiw_name=wiw_name
        )
        results, result_warnings = self._build_results(selection)
        district = self._selection_district(selection, sd_name=sd_name, sgg_name=sgg_name, wiw_name=wiw_name)
        warnings = list(selection.warnings) + result_warnings
        area = selection.area

        electorate = area.electorate if area else None
        turnout = area.turnout if area else None
        valid = area.valid if area else None
        invalid = area.invalid if area else None
        abstention = area.abstention if area else None
        metric_source = "tally" if area else None

        rule = scope_rule(sg_typecode)
        if area is not None and electorate is None and rule.turnout_aligned:
            turnout_row = self._exact_turnout_row(selection)
            if turnout_row:
                electorate = as_int(first_of(turnout_row, "sunsu", "totSunsu", "electorate_count"))
                turnout = as_int(first_of(turnout_row, "tusu", "totTusu", "turnout_count"))
                metric_source = "turnout"
        if abstention is None and electorate is not None and turnout is not None:
            abstention = max(electorate - turnout, 0)
        if area is None:
            warnings.append("No district was selected, so no summary metrics are available.")

        election, election_warnings = self._try_get_election(sg_id, sg_typecode)
        warnings.extend(election_warnings)
        return DistrictSummary(
            election=election,
            district=district,
            candidate_count=len(area.slots) if area else 0,
            electorate_count=electorate,
            turnout_count=turnout,
            valid_vote_count=valid,
            invalid_vote_count=invalid,
            abstention_count=abstention,
            turnout_rate=turnout_rate(turnout, electorate),
            result_source="tally_api" if area else None,
            coverage_scope=selection.coverage_scope if area else None,
            metric_source=metric_source,
            provenance=[self._provenance("nec_results", "district_summary", district.district_uid)],
            warnings=_dedupe(warnings),
        )

    def _exact_turnout_row(self, selection: DistrictSelection) -> dict[str, Any] | None:
        if selection.tally is None:
            return None
        try:
            rows = self.nec_client.fetch_turnout_rows(
                sg_id=selection.sg_id, sg_typecode=selection.sg_typecode, sd_name=selection.sd_name
            )
        except (ApiRequestError, ConfigurationError) as exc:
            selection.warnings.append(f"Turnout API failed ({self._short(exc)}).")
            return None
        for row in rows:
            key = district_key(as_str(first_of(row, "sdName", "sd_name")), as_str(first_of(row, "sggName", "sgg_name")))
            wiw = normalize_text(as_str(first_of(row, "wiwName", "wiw_name")))
            if key == selection.tally.key and wiw in {"", normalize_text(TOTAL_WIW_NAME)}:
                return row
        return None

    # --------------------------------------------------------- candidate result

    def get_candidate_result_with_warnings(self, candidate: Candidate) -> tuple[CandidateResult | None, list[str]]:
        ref = candidate.candidate_ref
        rule = scope_rule(ref.sg_typecode)
        if not ref.sd_name and rule.level != "national":
            return None, ["Candidate has no province (sd_name); its result cannot be looked up safely."]
        sgg_query = ref.sgg_name if rule.level in {"sgg", "wiw"} else None
        selection = self.select_district(
            sg_id=ref.sg_id,
            sg_typecode=ref.sg_typecode,
            sd_name=ref.sd_name if rule.level != "national" else None,
            sgg_name=sgg_query,
            strict=True,
        )
        results, result_warnings = self._build_results(selection)
        warnings = list(selection.warnings) + result_warnings
        if not results:
            return None, _dedupe(warnings + ["No tally result was found for the candidate's district."])

        method = None
        match: list[CandidateResult] = []
        if ref.huboid:
            match = [result for result in results if result.candidate_ref.huboid == ref.huboid]
            method = "huboid"
        if not match and ref.candidate_name:
            wanted = normalize_candidate_name(ref.candidate_name)
            match = [result for result in results if normalize_candidate_name(result.candidate_name) == wanted]
            method = "name"
            party = candidate.party_name or ref.party_name
            if len(match) > 1 and party:
                match = [
                    result for result in match if normalize_party_name(result.party_name) == normalize_party_name(party)
                ]
                method = "name+party"
        if len(match) != 1:
            reason = "several candidates share that name" if match else "the candidate is not in the district tally"
            return None, _dedupe(warnings + [f"Result not matched: {reason}."])
        result = match[0]
        result.match_method = f"{method}+{selection.method}"
        confidence = {"huboid": 1.0, "name": 0.9, "name+party": 0.85}[method or "name"]
        result.match_confidence = round(min(confidence, selection.confidence), 3)
        if ref.huboid and not result.candidate_ref.huboid:
            result.candidate_ref = result.candidate_ref.model_copy(update={"huboid": ref.huboid})
        return result, _dedupe(warnings)

    def get_candidate_result(self, candidate: Candidate) -> CandidateResult | None:
        """Return the candidate's own tally result, or None when it cannot be matched with certainty."""
        result, _ = self.get_candidate_result_with_warnings(candidate)
        return result

    # ------------------------------------------------------------------ history

    def get_party_vote_share_history_with_warnings(
        self,
        *,
        party_name: str,
        district_name: str,
        sd_name: str | None = None,
        sg_typecode: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        follow_lineage: bool = False,
    ) -> tuple[list[PartyVoteSharePoint], list[str]]:
        warnings: list[str] = []
        if not sg_typecode:
            sg_typecode = "2"
            warnings.append("sg_typecode was not given; National Assembly elections (2) were used.")
        party_keys = party_match_keys(party_name, follow_lineage=follow_lineage)
        elections, election_warnings = self._list_elections(sg_typecode=sg_typecode, year_from=year_from, year_to=year_to)
        warnings.extend(election_warnings)
        elections = sorted(elections, key=lambda item: item.sg_id)
        if len(elections) > MAX_HISTORY_ELECTIONS:
            warnings.append(
                f"{len(elections)} elections matched; only the latest {MAX_HISTORY_ELECTIONS} were queried. "
                "Narrow year_from/year_to for older ones."
            )
            elections = elections[-MAX_HISTORY_ELECTIONS:]

        history: list[PartyVoteSharePoint] = []
        for election in elections:
            try:
                selection = self.select_district(
                    sg_id=election.sg_id,
                    sg_typecode=election.sg_typecode,
                    sd_name=sd_name,
                    sgg_name=district_name,
                    strict=True,
                )
            except (ApiAuthorizationError, ApiQuotaError, ConfigurationError) as exc:
                warnings.append(f"Stopped at {election.sg_id}: {self._short(exc)}")
                break
            except ApiRequestError as exc:
                warnings.append(f"{election.sg_id}: {self._short(exc)}")
                continue
            if selection.tally is None or selection.area is None:
                warnings.append(f"{election.sg_id}: district '{district_name}' was not found.")
                continue
            results, _ = self._build_results(selection)
            party_results = [
                result
                for result in results
                if normalize_party_name(map_party_name(result.party_name)) in party_keys
            ]
            if not party_results:
                continue
            votes = sum(result.vote_count or 0 for result in party_results)
            share = (
                party_results[0].vote_share
                if len(party_results) == 1
                else nec_share(votes, selection.area.valid)
            )
            history.append(
                PartyVoteSharePoint(
                    election=election,
                    district_label=party_results[0].district_label,
                    party_name=party_results[0].party_name or party_name,
                    vote_count=votes,
                    vote_share=share,
                    result_source="tally_api",
                    match_method=selection.method,
                    match_confidence=round(selection.confidence, 3),
                    provenance=party_results[0].provenance,
                )
            )
        history.sort(key=lambda point: point.election.election_date or point.election.sg_id)
        return history, _dedupe(warnings)

    def get_party_vote_share_history(
        self,
        *,
        party_name: str,
        district_name: str,
        sd_name: str | None = None,
        sg_typecode: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        follow_lineage: bool = False,
    ) -> list[PartyVoteSharePoint]:
        """Return one district-level vote share point per election for a party (winning or not)."""
        history, _ = self.get_party_vote_share_history_with_warnings(
            party_name=party_name,
            district_name=district_name,
            sd_name=sd_name,
            sg_typecode=sg_typecode,
            year_from=year_from,
            year_to=year_to,
            follow_lineage=follow_lineage,
        )
        return history

    # ----------------------------------------------------------------- overview

    def get_election_overview(self, *, sg_id: str, sg_typecode: str) -> ElectionOverview:
        """Return election-wide district, party, winner, and turnout aggregates."""
        warnings: list[str] = []
        election, election_warnings = self._try_get_election(sg_id, sg_typecode)
        warnings.extend(election_warnings)
        election = election or Election(election_uid=f"{sg_id}:{sg_typecode}", sg_id=sg_id, sg_typecode=sg_typecode)

        districts, district_error = self._guarded(
            lambda: self.nec_client.list_districts(sg_id=sg_id, sg_typecode=sg_typecode)
        )
        parties, party_error = self._guarded(lambda: self.nec_client.list_parties(sg_id=sg_id, sg_typecode=sg_typecode))
        winner_rows, winner_error = self._guarded(
            lambda: self.nec_client.fetch_winner_rows(sg_id=sg_id, sg_typecode=sg_typecode)
        )
        tally_rows, tally_error = self._guarded(
            lambda: self.nec_client.fetch_tally_rows(sg_id=sg_id, sg_typecode=sg_typecode)
        )
        if winner_error and tally_error:
            raise tally_error
        if winner_error:
            warnings.append(f"Winner API failed ({self._short(winner_error)}).")
        if tally_error:
            warnings.append(f"Tally API failed ({self._short(tally_error)}); turnout is unavailable.")

        tallies = build_district_tallies(row for row in (tally_rows or []) if is_wide_tally_row(row))
        national = [tally for tally in tallies.values() if self._is_national_tally(tally)]
        contests = [tally for tally in tallies.values() if not self._is_national_tally(tally)]

        metric_area: AreaRow | None = None
        if len(national) == 1:
            metric_area = national[0].rollup
        elif contests:
            rollups = [tally.rollup for tally in contests]
            metric_area = AreaRow(
                sd_name=None,
                sgg_name=None,
                wiw_name=TOTAL_WIW_NAME,
                electorate=_sum_or_none(area.electorate for area in rollups),
                turnout=_sum_or_none(area.turnout for area in rollups),
                valid=_sum_or_none(area.valid for area in rollups),
                invalid=_sum_or_none(area.invalid for area in rollups),
                abstention=_sum_or_none(area.abstention for area in rollups),
                slots=(),
                synthetic=True,
            )
            warnings.append(
                f"No nationwide total row was returned; totals were summed from {len(contests)} district total rows."
            )
        elif not tally_error:
            warnings.append("Turnout rows unavailable for election overview.")

        if district_error is not None:
            districts = [
                canonicalize_district(sg_id=sg_id, sg_typecode=sg_typecode, sd_name=tally.sd_name, sgg_name=tally.sgg_name)
                for tally in contests
            ]
            warnings.append(
                f"District code list unavailable ({self._short(district_error)}); districts were derived from tally rows."
            )
        if party_error is not None:
            parties = self._parties_from_rows(sg_id, sg_typecode, tally_rows or [], winner_rows or [])
            warnings.append(
                f"Party code list unavailable ({self._short(party_error)}); parties were derived from result rows."
            )

        winners = [self._winner_result(row, sg_id=sg_id, sg_typecode=sg_typecode) for row in (winner_rows or [])]
        return ElectionOverview(
            election=election,
            district_count=len(districts or []),
            party_count=len(parties or []),
            winner_count=len(winners),
            electorate_count=metric_area.electorate if metric_area else None,
            turnout_count=metric_area.turnout if metric_area else None,
            turnout_rate=turnout_rate(metric_area.turnout, metric_area.electorate) if metric_area else None,
            winners=winners,
            districts=districts or [],
            parties=parties or [],
            provenance=[self._provenance("nec_results", "election_overview", election.election_uid)],
            warnings=_dedupe(warnings),
        )

    def _winner_result(self, row: dict[str, Any], *, sg_id: str, sg_typecode: str) -> CandidateResult:
        name = as_str(first_of(row, "name", "huboNm"))
        party = as_str(first_of(row, "jdName"))
        sd = as_str(first_of(row, "sdName"))
        sgg = as_str(first_of(row, "sggName"))
        wiw = as_str(first_of(row, "wiwName"))
        huboid = as_str(first_of(row, "huboid", "huboId"))
        giho = as_str(first_of(row, "giho"))
        label = build_district_label(sd, sgg, wiw if normalize_text(wiw) != normalize_text(sgg) else None)
        ref = CandidateRef(
            candidacy_uid=NecApiClient._build_candidacy_uid(sg_id, sg_typecode, huboid, name, party, sd, sgg, None, giho),
            huboid=huboid,
            sg_id=sg_id,
            sg_typecode=sg_typecode,
            candidate_name=name,
            sd_name=sd,
            sgg_name=sgg,
            wiw_name=wiw,
            district_label=label,
            party_name=party,
            giho=giho,
        )
        return CandidateResult(
            candidate_ref=ref,
            candidate_name=name,
            party_name=party,
            giho=giho,
            giho_detail=as_str(first_of(row, "gihoSangse")),
            district_label=label,
            vote_count=as_int(first_of(row, "dugsu")),
            vote_share=as_float(first_of(row, "dugyul")),
            is_winner=True,
            result_source="winner_api",
            coverage_scope="winner_only",
            match_method="winner_row",
            match_confidence=1.0,
            provenance=[self._provenance("nec_results", "candidate_result", ref.candidacy_uid)],
        )

    @staticmethod
    def _parties_from_rows(
        sg_id: str,
        sg_typecode: str,
        tally_rows: list[dict[str, Any]],
        winner_rows: list[dict[str, Any]],
    ) -> list[Party]:
        names: list[str] = []
        for row in tally_rows:
            for slot in expand_tally_row(row):
                if slot.party and slot.party not in names:
                    names.append(slot.party)
        for row in winner_rows:
            party = as_str(first_of(row, "jdName"))
            if party and party not in names:
                names.append(party)
        return [
            Party(
                party_uid=f"{sg_id}:{sg_typecode}:{name}",
                sg_id=sg_id,
                sg_typecode=sg_typecode,
                party_name=name,
                normalized_party_name=map_party_name(name),
                provenance=[ProvenanceRecord(source_name="nec_results", entity_type="party", source_ref=name, access_method="derived")],
            )
            for name in names
        ]

    # ------------------------------------------------------- list fallbacks

    def list_districts_from_results(
        self, *, sg_id: str, sg_typecode: str, sd_name: str | None = None
    ) -> list[District]:
        """Derive the district list from tally rows (used when the code API is unavailable)."""
        names: list[str | None] = [None] if not sd_name else sido_request_names(sd_name, sg_id)
        rows, error = self._fetch_first_nonempty(
            lambda name: self.nec_client.fetch_tally_rows(sg_id=sg_id, sg_typecode=sg_typecode, sd_name=name), names
        )
        if error and not rows:
            raise error
        wanted = sido_key(sd_name) if sd_name else None
        tallies = build_district_tallies(
            row
            for row in rows
            if is_wide_tally_row(row)
            and (wanted is None or sido_key(as_str(first_of(row, "sdName", "sd_name"))) == wanted)
        )
        return [
            canonicalize_district(sg_id=sg_id, sg_typecode=sg_typecode, sd_name=tally.sd_name, sgg_name=tally.sgg_name)
            for tally in tallies.values()
            if not self._is_national_tally(tally)
        ]

    def list_parties_from_results(self, *, sg_id: str, sg_typecode: str) -> list[Party]:
        tally_rows, tally_error = self._guarded(
            lambda: self.nec_client.fetch_tally_rows(sg_id=sg_id, sg_typecode=sg_typecode)
        )
        winner_rows, winner_error = self._guarded(
            lambda: self.nec_client.fetch_winner_rows(sg_id=sg_id, sg_typecode=sg_typecode)
        )
        if tally_error and winner_error:
            raise tally_error
        return self._parties_from_rows(sg_id, sg_typecode, tally_rows or [], winner_rows or [])

    # ------------------------------------------------------------------ helpers

    def _try_get_election(self, sg_id: str, sg_typecode: str) -> tuple[Election | None, list[str]]:
        getter = getattr(self.nec_client, "try_get_election", None)
        if callable(getter):
            return getter(sg_id, sg_typecode)
        try:
            return self.nec_client.get_election(sg_id, sg_typecode), []
        except (ApiRequestError, ConfigurationError) as exc:
            return None, [f"Election metadata unavailable ({self._short(exc)}); results are still shown."]

    def _list_elections(self, **kwargs: Any) -> tuple[list[Election], list[str]]:
        getter = getattr(self.nec_client, "list_elections_with_warnings", None)
        if callable(getter):
            return getter(include_history=True, **kwargs)
        return self.nec_client.list_elections(include_history=True, **kwargs), []

    @staticmethod
    def _guarded(fn: Callable[[], T]) -> tuple[T | None, ApiRequestError | ConfigurationError | None]:
        try:
            return fn(), None
        except (ApiRequestError, ConfigurationError) as exc:
            return None, exc

    @staticmethod
    def _short(exc: Exception) -> str:
        text = str(exc).strip() or type(exc).__name__
        return text if len(text) <= 160 else text[:157] + "..."

    @staticmethod
    def _provenance(source_name: str, entity_type: str, source_ref: str | None) -> ProvenanceRecord:
        return ProvenanceRecord(
            source_name=source_name,
            entity_type=entity_type,
            source_ref=source_ref,
            access_method="api",
        )


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return ordered


def _sum_or_none(values: Any) -> int | None:
    total = 0
    for value in values:
        if value is None:
            return None
        total += value
    return total
