from __future__ import annotations

from dataclasses import dataclass, field

from .campaign_booklet_corpus import office_similarity
from .models import Candidate, CandidateProfile, KrPolTextMetaRecord, MatchMetadata, ResolutionStatus
from .normalize import candidate_name_similarity, map_party_name, similarity


@dataclass
class RankedKrPolTextMatch:
    item: KrPolTextMetaRecord
    metadata: MatchMetadata
    strong_signal_count: int = 0
    strong_signals: list[str] = field(default_factory=list)
    base_exact: bool = False
    identity_verified: bool = False


def rank_krpoltext_candidate_matches(
    candidate: Candidate,
    profile: CandidateProfile | None,
    items: list[KrPolTextMetaRecord],
) -> list[RankedKrPolTextMatch]:
    ranked = [_score_item(candidate, profile, item) for item in items]
    ranked.sort(
        key=lambda detail: (
            detail.metadata.match_confidence or 0.0,
            detail.strong_signal_count,
            1 if detail.identity_verified else 0,
        ),
        reverse=True,
    )
    return ranked


def decorate_krpoltext_candidate_match(detail: RankedKrPolTextMatch) -> KrPolTextMetaRecord:
    merged_warnings = list(detail.item.warnings)
    for warning in detail.metadata.warnings:
        if warning not in merged_warnings:
            merged_warnings.append(warning)
    return detail.item.model_copy(
        update={
            "match_method": detail.metadata.match_method,
            "match_confidence": detail.metadata.match_confidence,
            "warnings": merged_warnings,
        }
    )


def decorate_krpoltext_candidate_matches(ranked: list[RankedKrPolTextMatch]) -> list[KrPolTextMetaRecord]:
    return [decorate_krpoltext_candidate_match(detail) for detail in ranked]


def resolve_krpoltext_candidate_match(
    ranked: list[RankedKrPolTextMatch],
) -> tuple[ResolutionStatus, KrPolTextMetaRecord | None, str | None, list[str]]:
    if not ranked:
        return (
            ResolutionStatus.NOT_FOUND,
            None,
            "No krpoltext metadata rows matched the resolved NEC candidate.",
            [],
        )

    top = ranked[0]
    runner_up = ranked[1] if len(ranked) > 1 else None
    top_score = top.metadata.match_confidence or 0.0
    runner_score = runner_up.metadata.match_confidence or 0.0 if runner_up else 0.0
    gap = round(top_score - runner_score, 3)

    if top_score < 0.55:
        return (
            ResolutionStatus.NOT_FOUND,
            None,
            "No krpoltext metadata row matched the resolved NEC candidate strongly enough.",
            [],
        )

    if len(ranked) == 1 and top.base_exact:
        return (
            ResolutionStatus.RESOLVED,
            decorate_krpoltext_candidate_match(top),
            "Resolved krpoltext metadata row from NEC election, office, district, and name context.",
            [],
        )

    if top.identity_verified and (runner_up is None or top.strong_signal_count > runner_up.strong_signal_count or gap >= 0.08):
        return (
            ResolutionStatus.RESOLVED,
            decorate_krpoltext_candidate_match(top),
            "Resolved krpoltext metadata row using stronger personal identifiers.",
            [],
        )

    if top.strong_signal_count >= 2 and gap >= 0.08:
        return (
            ResolutionStatus.RESOLVED,
            decorate_krpoltext_candidate_match(top),
            "Resolved krpoltext metadata row using multiple corroborating metadata fields.",
            [],
        )

    warnings = [
        "Multiple krpoltext rows remain plausible for the resolved NEC candidate; review giho, birthday, education, and career fields before choosing one.",
    ]
    if top.base_exact:
        warnings.append(
            "Same-election same-district same-name collisions stay ambiguous unless a stronger personal identifier uniquely matches."
        )
    return (
        ResolutionStatus.AMBIGUOUS,
        None,
        "Multiple krpoltext metadata rows matched the resolved NEC candidate.",
        warnings,
    )


def _score_item(
    candidate: Candidate,
    profile: CandidateProfile | None,
    item: KrPolTextMetaRecord,
) -> RankedKrPolTextMatch:
    methods: list[str] = []
    warnings: list[str] = []
    strong_signals: list[str] = []
    score = 0.0

    candidate_name = candidate.candidate_ref.candidate_name or candidate.party_name
    name_score = candidate_name_similarity(item.candidate_name, candidate_name)
    score += name_score * 0.28
    if name_score >= 0.99:
        methods.append("name")

    candidate_year = _extract_year(candidate.election_date)
    year_exact = False
    if candidate_year is not None and item.election_year is not None:
        if candidate_year == item.election_year:
            year_exact = True
            methods.append("year")
            score += 0.14
        else:
            score -= 0.18
            warnings.append("krpoltext election year differs from the resolved NEC candidate.")

    office_score = office_similarity(
        candidate.sg_name,
        item.office_name,
        str(item.office_id) if item.office_id is not None else None,
    )
    score += office_score * 0.12
    if office_score >= 0.95:
        methods.append("office")

    district_label = candidate.candidate_ref.district_label or ""
    district_score = max(
        similarity(item.district_name, district_label),
        similarity(item.district_raw, district_label),
    )
    score += district_score * 0.12
    if district_score >= 0.95:
        methods.append("district")

    candidate_party = candidate.party_name or candidate.candidate_ref.party_name
    if candidate_party and item.party_name:
        party_score = similarity(map_party_name(item.party_name), candidate_party)
        score += party_score * 0.08
        if party_score >= 0.95:
            methods.append("party")

    giho_exact = False
    candidate_giho = _normalize_giho(candidate.giho or candidate.candidate_ref.giho)
    item_giho = _normalize_giho(item.giho)
    if candidate_giho and item_giho:
        if candidate_giho == item_giho:
            giho_exact = True
            strong_signals.append("giho")
            methods.append("giho")
            score += 0.18
        else:
            score -= 0.1
            warnings.append("krpoltext giho differs from the resolved NEC candidate.")

    birthday_exact = False
    profile_birthday = _normalize_digits(profile.birthday if profile else None)
    item_birthday = _normalize_digits(item.birthday)
    if profile_birthday and item_birthday:
        if profile_birthday == item_birthday:
            birthday_exact = True
            strong_signals.append("birthday")
            methods.append("birthday")
            score += 0.22
        else:
            score -= 0.14
            warnings.append("krpoltext birthday differs from the resolved NEC profile.")

    age_exact = False
    if profile and profile.age is not None and item.age is not None:
        if profile.age == item.age:
            age_exact = True
            methods.append("age")
            score += 0.05
        else:
            score -= 0.05

    sex_score = similarity(item.sex, profile.gender if profile else None)
    score += sex_score * 0.03
    if sex_score >= 0.95:
        methods.append("sex")

    education_score = _best_similarity(
        profile.education if profile else None,
        item.edu,
        item.edu_name,
        item.edu_name_eng,
    )
    score += education_score * 0.05
    if education_score >= 0.95:
        strong_signals.append("education")
        methods.append("education")

    job_score = _best_similarity(
        profile.job if profile else None,
        item.job,
        item.job_name,
        item.job_name_eng,
    )
    score += job_score * 0.04
    if job_score >= 0.95:
        methods.append("job")

    career_score = max(
        _best_similarity(profile.career1 if profile else None, item.career1, item.career2),
        _best_similarity(profile.career2 if profile else None, item.career1, item.career2),
    )
    score += career_score * 0.05
    if career_score >= 0.95:
        methods.append("career")

    base_exact = (
        name_score >= 0.99
        and year_exact
        and office_score >= 0.95
        and district_score >= 0.95
    )
    identity_verified = (
        birthday_exact
        or giho_exact
        or ((education_score >= 0.95 or job_score >= 0.95) and career_score >= 0.9)
        or (age_exact and education_score >= 0.95 and career_score >= 0.9)
    )

    method = "+".join(dict.fromkeys(methods)) or "candidate_context"
    confidence = round(max(0.0, min(1.0, score)), 3)

    return RankedKrPolTextMatch(
        item=item,
        metadata=MatchMetadata(
            match_method=method,
            match_confidence=confidence,
            warnings=warnings,
        ),
        strong_signal_count=len(set(strong_signals)),
        strong_signals=list(dict.fromkeys(strong_signals)),
        base_exact=base_exact,
        identity_verified=identity_verified,
    )


def _best_similarity(value: str | None, *candidates: str | None) -> float:
    return max((similarity(value, candidate) for candidate in candidates), default=0.0)


def _extract_year(value: str | None) -> int | None:
    digits = _normalize_digits(value)
    if len(digits) < 4:
        return None
    return int(digits[:4])


def _normalize_digits(value: str | None) -> str:
    return "".join(character for character in str(value or "") if character.isdigit())


def _normalize_giho(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.isdigit():
        return str(int(text))
    return text
