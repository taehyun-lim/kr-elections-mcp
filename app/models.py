from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AvailabilityState(str, Enum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class DiagnosticStatus(str, Enum):
    OK = "ok"
    NOT_APPLIED = "not_applied"
    UNAUTHORIZED = "unauthorized"
    EMPTY = "empty"
    ERROR = "error"





class ResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"


class ProvenanceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_name: str
    entity_type: str
    source_ref: str | None = None
    access_method: str | None = None
    notes: str | None = None


class MatchMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    match_method: str | None = None
    match_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    warnings: list[str] = Field(default_factory=list)


class CandidateRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidacy_uid: str | None = None
    huboid: str | None = None
    sg_id: str
    sg_typecode: str
    candidate_name: str | None = None
    sd_name: str | None = None
    sgg_name: str | None = None
    wiw_name: str | None = None
    district_label: str | None = None
    party_name: str | None = None
    giho: str | None = None


class Election(BaseModel):
    model_config = ConfigDict(extra="allow")

    election_uid: str
    sg_id: str
    sg_typecode: str
    sg_name: str | None = None
    election_date: str | None = None
    provenance: list[ProvenanceRecord] = Field(default_factory=list)


class District(BaseModel):
    model_config = ConfigDict(extra="allow")

    district_uid: str
    sg_id: str
    sg_typecode: str
    sd_name: str | None = None
    sgg_name: str | None = None
    wiw_name: str | None = None
    district_label: str
    canonical_name: str | None = None
    match_mode: str = "strict"
    aliases: list[str] = Field(default_factory=list)
    provenance: list[ProvenanceRecord] = Field(default_factory=list)


class Party(BaseModel):
    model_config = ConfigDict(extra="allow")

    party_uid: str
    sg_id: str
    sg_typecode: str
    party_code: str | None = None
    party_name: str
    normalized_party_name: str | None = None
    provenance: list[ProvenanceRecord] = Field(default_factory=list)


class Candidate(BaseModel):
    model_config = ConfigDict(extra="allow")

    candidate_ref: CandidateRef
    sg_name: str | None = None
    election_date: str | None = None
    district: District | None = None
    party_name: str | None = None
    giho: str | None = None
    is_winner: bool | None = None
    ambiguity_score: float | None = Field(default=None, ge=0.0, le=1.0)
    provenance: list[ProvenanceRecord] = Field(default_factory=list)
    raw_fields: dict[str, Any] = Field(default_factory=dict)


class CandidateResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ResolutionStatus
    candidate: Candidate | None = None
    candidates: list[Candidate] = Field(default_factory=list)
    message: str | None = None
    warnings: list[str] = Field(default_factory=list)


class CandidateProfile(BaseModel):
    model_config = ConfigDict(extra="allow")

    candidate: Candidate
    birthday: str | None = None
    age: int | None = None
    gender: str | None = None
    job: str | None = None
    education: str | None = None
    career1: str | None = None
    career2: str | None = None
    address: str | None = None
    status_code: str | None = None
    status_label: str | None = None
    extra_json: dict[str, Any] = Field(default_factory=dict)
    provenance: list[ProvenanceRecord] = Field(default_factory=list)


class CandidatePolicy(BaseModel):
    model_config = ConfigDict(extra="allow")

    policy_id: str
    candidate_ref: CandidateRef
    policy_source: Literal["manifesto", "party_policy"]
    title: str | None = None
    content: str | None = None
    budget_text: str | None = None
    order_no: int | None = None
    availability: AvailabilityState = AvailabilityState.AVAILABLE
    provenance: list[ProvenanceRecord] = Field(default_factory=list)
    raw_fields: dict[str, Any] = Field(default_factory=dict)


class CandidateResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    candidate_ref: CandidateRef
    candidate_name: str | None = None
    party_name: str | None = None
    giho: str | None = None
    district_label: str | None = None
    vote_count: int | None = None
    vote_share: float | None = None
    rank_in_district: int | None = None
    is_winner: bool | None = None
    result_source: Literal["winner_api", "tally_api", "file_data"]
    coverage_scope: Literal["winner_only", "all_candidates", "district_rollup"]
    match_method: str | None = None
    match_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    provenance: list[ProvenanceRecord] = Field(default_factory=list)
    raw_fields: dict[str, Any] = Field(default_factory=dict)


class DistrictSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    election: Election | None = None
    district: District
    candidate_count: int = 0
    electorate_count: int | None = None
    turnout_count: int | None = None
    valid_vote_count: int | None = None
    invalid_vote_count: int | None = None
    abstention_count: int | None = None
    turnout_rate: float | None = None
    result_source: str | None = None
    coverage_scope: str | None = None
    provenance: list[ProvenanceRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PartyVoteSharePoint(BaseModel):
    model_config = ConfigDict(extra="allow")

    election: Election
    district_label: str | None = None
    party_name: str
    vote_count: int | None = None
    vote_share: float | None = None
    result_source: str | None = None
    match_method: str | None = None
    match_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    provenance: list[ProvenanceRecord] = Field(default_factory=list)





class KrPolTextRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    record_id: str
    code: str | None = None
    candidate_name: str | None = None
    huboid: str | None = None
    sg_id: str | None = None
    sg_typecode: str | None = None
    office_name: str | None = None
    election_year: int | None = None
    district_name: str | None = None
    party_name: str | None = None
    page_count: int | None = None
    dataset_version: str | None = None
    source: str = "krpoltext"
    source_url: str | None = None
    text: str | None = None
    time_range: str | None = None
    availability: AvailabilityState = AvailabilityState.UNKNOWN
    match_method: str | None = None
    match_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    provenance: list[ProvenanceRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class KrPolTextMetaRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    record_id: str
    code: str | None = None
    candidate_name: str | None = None
    huboid: str | None = None
    sg_id: str | None = None
    sg_typecode: str | None = None
    office_id: int | None = None
    office_name: str | None = None
    election_year: int | None = None
    region_name: str | None = None
    district_raw: str | None = None
    district_name: str | None = None
    giho: str | None = None
    party_name: str | None = None
    party_name_eng: str | None = None
    result: str | None = None
    result_code: int | None = None
    sex: str | None = None
    sex_code: int | None = None
    birthday: str | None = None
    age: int | None = None
    job_id: str | None = None
    job: str | None = None
    job_name: str | None = None
    job_name_eng: str | None = None
    job_code: int | None = None
    edu_id: str | None = None
    edu: str | None = None
    edu_name: str | None = None
    edu_name_eng: str | None = None
    edu_code: int | None = None
    career1: str | None = None
    career2: str | None = None
    page_count: int | None = None
    has_text: bool | None = None
    dataset_version: str | None = None
    source: str = "krpoltext"
    source_url: str | None = None
    time_range: str | None = None
    availability: AvailabilityState = AvailabilityState.UNKNOWN
    match_method: str | None = None
    match_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    provenance: list[ProvenanceRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    raw_fields: dict[str, Any] = Field(default_factory=dict)


class ElectionOverview(BaseModel):
    model_config = ConfigDict(extra="allow")

    election: Election
    district_count: int = 0
    party_count: int = 0
    winner_count: int = 0
    electorate_count: int | None = None
    turnout_count: int | None = None
    turnout_rate: float | None = None
    winners: list[CandidateResult] = Field(default_factory=list)
    districts: list[District] = Field(default_factory=list)
    parties: list[Party] = Field(default_factory=list)
    provenance: list[ProvenanceRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CandidatePacket(BaseModel):
    model_config = ConfigDict(extra="allow")

    resolution: CandidateResolution
    profile: CandidateProfile | None = None
    policies: list[CandidatePolicy] = Field(default_factory=list)
    policy_availability: AvailabilityState = AvailabilityState.UNKNOWN
    krpoltext: list[KrPolTextRecord] = Field(default_factory=list)
    result: CandidateResult | None = None
    provenance: list[ProvenanceRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class DiagnosticCheck(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    status: DiagnosticStatus
    message: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    provenance: list[ProvenanceRecord] = Field(default_factory=list)


class DiagnosticsReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    checks: list[DiagnosticCheck]
    warnings: list[str] = Field(default_factory=list)


class ListElectionsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sg_typecode: str | None = None
    year_from: int | None = None
    year_to: int | None = None
    include_history: bool = True


class ListElectionsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[Election]
    provenance: list[ProvenanceRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ListDistrictsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sg_id: str
    sg_typecode: str
    sd_name: str | None = None
    match_mode: str = "strict"


class ListDistrictsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[District]
    provenance: list[ProvenanceRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ListPartiesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sg_id: str
    sg_typecode: str


class ListPartiesOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[Party]
    provenance: list[ProvenanceRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SearchCandidatesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_name: str
    sg_id: str | None = None
    sg_typecode: str | None = None
    sd_name: str | None = None
    district_name: str | None = None
    limit: int = Field(default=10, ge=1, le=50)


class SearchCandidatesOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[Candidate]
    warnings: list[str] = Field(default_factory=list)


class CandidateLookupInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_ref: CandidateRef | None = None
    candidate_name: str | None = None
    sg_id: str | None = None
    sg_typecode: str | None = None
    sd_name: str | None = None
    district_name: str | None = None
    party_name: str | None = None
    giho: str | None = None
    include_raw_fields: bool = False


class CandidateProfileOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolution: CandidateResolution
    profile: CandidateProfile | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class CandidatePoliciesOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolution: CandidateResolution
    availability: AvailabilityState = AvailabilityState.UNKNOWN
    items: list[CandidatePolicy] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class DistrictResultsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sg_id: str
    sg_typecode: str
    sd_name: str
    sgg_name: str | None = None
    wiw_name: str | None = None


class DistrictResultsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    district: District
    items: list[CandidateResult]
    warnings: list[str] = Field(default_factory=list)


class DistrictSummaryOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: DistrictSummary
    warnings: list[str] = Field(default_factory=list)


class PartyVoteShareHistoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    party_name: str
    district_name: str
    sd_name: str | None = None
    sg_typecode: str | None = None
    year_from: int | None = None
    year_to: int | None = None


class PartyVoteShareHistoryOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PartyVoteSharePoint]
    warnings: list[str] = Field(default_factory=list)


class ElectionOverviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sg_id: str
    sg_typecode: str


class ElectionOverviewOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overview: ElectionOverview
    warnings: list[str] = Field(default_factory=list)


class AssembleCandidatePacketInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_ref: CandidateRef | None = None
    candidate_name: str | None = None
    sg_id: str | None = None
    sg_typecode: str | None = None
    sd_name: str | None = None
    district_name: str | None = None
    party_name: str | None = None
    giho: str | None = None


class DiagnoseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    include_optional: bool = False





class KrPolTextInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_name: str | None = None
    code: str | None = None
    election_year: int | None = None
    office_name: str | None = None
    district_name: str | None = None
    party_name: str | None = None
    limit: int = Field(default=10, ge=1, le=100)


class KrPolTextOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[KrPolTextRecord]
    warnings: list[str] = Field(default_factory=list)


class KrPolTextMetaOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[KrPolTextMetaRecord]
    warnings: list[str] = Field(default_factory=list)


class KrPolTextCandidateMatchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_ref: CandidateRef | None = None
    candidate_name: str | None = None
    sg_id: str | None = None
    sg_typecode: str | None = None
    sd_name: str | None = None
    district_name: str | None = None
    party_name: str | None = None
    giho: str | None = None
    limit: int = Field(default=10, ge=1, le=100)


class KrPolTextCandidateMatchOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolution: CandidateResolution
    profile: CandidateProfile | None = None
    status: ResolutionStatus
    item: KrPolTextMetaRecord | None = None
    items: list[KrPolTextMetaRecord] = Field(default_factory=list)
    message: str | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)



