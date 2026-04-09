from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any

from .models import Candidate, District, MatchMetadata

PARTY_ALIASES = {
    "더불어민주당": {"민주당", "더민주"},
    "국민의힘": {"국힘", "국민의 힘"},
    "정의당": {"정의"},
}


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKC", value)
    normalized = normalized.casefold()
    normalized = re.sub(r"[\s\-_/.,()]+", "", normalized)
    return normalized


def normalize_candidate_name(value: str | None) -> str:
    return normalize_text(value)


def normalize_party_name(value: str | None) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    for canonical, aliases in PARTY_ALIASES.items():
        if text == normalize_text(canonical):
            return normalize_text(canonical)
        if text in {normalize_text(alias) for alias in aliases}:
            return normalize_text(canonical)
    return text


def map_party_name(value: str | None) -> str:
    if not value:
        return ""
    normalized = normalize_party_name(value)
    for canonical, aliases in PARTY_ALIASES.items():
        if normalized == normalize_text(canonical):
            return canonical
        if normalized in {normalize_text(alias) for alias in aliases}:
            return canonical
    return value.strip()


def normalize_district_name(value: str | None) -> str:
    return normalize_text(value)


def build_district_label(
    sd_name: str | None,
    sgg_name: str | None = None,
    wiw_name: str | None = None,
) -> str:
    return " ".join(part for part in [sd_name, sgg_name, wiw_name] if part).strip()


def canonicalize_district(
    sg_id: str,
    sg_typecode: str,
    sd_name: str | None,
    sgg_name: str | None = None,
    wiw_name: str | None = None,
    *,
    match_mode: str = "strict",
) -> District:
    label = build_district_label(sd_name, sgg_name, wiw_name)
    normalized_label = normalize_district_name(label)
    district_uid = ":".join(
        [
            sg_id,
            sg_typecode,
            normalize_district_name(sd_name),
            normalize_district_name(sgg_name),
            normalize_district_name(wiw_name),
            match_mode,
        ]
    )
    aliases = [alias for alias in {label, normalized_label} if alias]
    return District(
        district_uid=district_uid,
        sg_id=sg_id,
        sg_typecode=sg_typecode,
        sd_name=sd_name,
        sgg_name=sgg_name,
        wiw_name=wiw_name,
        district_label=label,
        canonical_name=normalized_label or label,
        match_mode=match_mode,
        aliases=aliases,
    )


def similarity(left: str | None, right: str | None) -> float:
    a = normalize_text(left)
    b = normalize_text(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(a=a, b=b).ratio()


def candidate_name_similarity(left: str | None, right: str | None) -> float:
    return similarity(left, right)


def score_candidate_match(
    candidate: Candidate | dict[str, Any],
    result_row: dict[str, Any],
    *,
    district_label: str | None = None,
) -> MatchMetadata:
    candidate_ref = candidate.candidate_ref.model_dump() if isinstance(candidate, Candidate) else candidate
    method_parts: list[str] = []
    confidence = 0.0
    warnings: list[str] = []

    row_huboid = first_of(result_row, "huboid", "huboId")
    if row_huboid and row_huboid == candidate_ref.get("huboid"):
        confidence += 0.55
        method_parts.append("huboid")

    name_score = candidate_name_similarity(
        candidate_ref.get("candidate_name"),
        first_of(result_row, "huboNm", "name", "candidate_name"),
    )
    if name_score >= 0.99:
        confidence += 0.2
        method_parts.append("name")
    elif name_score >= 0.8:
        confidence += 0.12
        method_parts.append("name_fuzzy")
    elif candidate_ref.get("candidate_name"):
        warnings.append("Candidate name match is weak.")

    candidate_party = candidate.party_name if isinstance(candidate, Candidate) else candidate.get("party_name")
    party_score = similarity(candidate_party, first_of(result_row, "jdName", "party_name"))
    if party_score >= 0.99:
        confidence += 0.1
        method_parts.append("party")
    elif party_score >= 0.8:
        confidence += 0.05
        method_parts.append("party_fuzzy")

    giho = candidate.giho if isinstance(candidate, Candidate) else candidate.get("giho")
    if giho and str(giho) == str(first_of(result_row, "giho", "num")):
        confidence += 0.1
        method_parts.append("giho")

    row_district = build_district_label(
        first_of(result_row, "sdName", "sd_name"),
        first_of(result_row, "sggName", "sgg_name"),
        first_of(result_row, "wiwName", "wiw_name"),
    )
    district_score = similarity(
        district_label or candidate_ref.get("district_label"),
        row_district,
    )
    if district_score >= 0.99:
        confidence += 0.15
        method_parts.append("district")
    elif district_score >= 0.8:
        confidence += 0.08
        method_parts.append("district_fuzzy")
    elif district_label:
        warnings.append("District match is weak.")

    confidence = round(min(confidence, 1.0), 3)
    if confidence < 0.45:
        warnings.append("Low confidence result match.")

    return MatchMetadata(
        match_method="+".join(method_parts) or "name_only",
        match_confidence=confidence,
        warnings=warnings,
    )


def first_of(payload: dict[str, Any], *keys: str) -> Any | None:
    for key in keys:
        value = payload.get(key)
        if value not in (None, "", []):
            return value
    return None
