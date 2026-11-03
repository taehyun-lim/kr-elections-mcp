"""Resolve user-typed district names onto the exact names NEC returned.

This is the only module in the results path that is allowed to be fuzzy, and it
never filters API rows: it maps one query onto one of the district names that
actually exist in the fetched rows, or reports why it could not.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

from .normalize import normalize_text, similarity

DIVISION_SUFFIXES = ("갑", "을", "병", "정", "무")  # 갑 을 병 정 무
ADMIN_SUFFIXES = ("구", "시", "군")  # 구 시 군
_COMPONENT_PATTERN = re.compile(r".+?[구시군]")


class DistrictMatch(str, Enum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    NOT_FOUND = "not_found"


@dataclass
class DistrictResolution:
    status: DistrictMatch
    name: str | None = None
    method: str | None = None
    confidence: float | None = None
    options: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _split_division(normalized: str) -> tuple[str, str]:
    if len(normalized) > 1 and normalized[-1] in DIVISION_SUFFIXES:
        return normalized[:-1], normalized[-1]
    return normalized, ""


def _base_variants(base: str) -> set[str]:
    variants = {base}
    if base and base[-1] not in ADMIN_SUFFIXES:
        variants.update(base + suffix for suffix in ADMIN_SUFFIXES)
    return variants


def district_components(name: str | None) -> list[str]:
    """Split a district name into its 구·시·군 parts ("중구영도구" -> ["중구", "영도구"])."""
    base, _ = _split_division(normalize_text(name))
    if not base:
        return []
    parts = _COMPONENT_PATTERN.findall(base)
    if not parts or "".join(parts) != base:
        return [base]
    return parts


def resolve_district_name(
    query: str | None,
    available: Iterable[str | None],
    *,
    strict: bool = False,
) -> DistrictResolution:
    names: list[str] = []
    for name in available:
        if name and name not in names:
            names.append(name)
    wanted = normalize_text(query)
    if not wanted:
        return DistrictResolution(DistrictMatch.NOT_FOUND, options=names[:5])
    normalized = {name: normalize_text(name) for name in names}

    exact = [name for name, value in normalized.items() if value == wanted]
    if len(exact) == 1:
        return DistrictResolution(DistrictMatch.RESOLVED, exact[0], "exact", 1.0)

    wanted_base, wanted_division = _split_division(wanted)
    wanted_variants = _base_variants(wanted_base)

    # "종로" -> "종로구", "사하갑" -> "사하구갑"
    suffix = []
    for name, value in normalized.items():
        base, division = _split_division(value)
        if division == wanted_division and base in wanted_variants:
            suffix.append(name)
    if len(suffix) == 1:
        return DistrictResolution(DistrictMatch.RESOLVED, suffix[0], "suffix", 0.95)
    if len(suffix) > 1:
        return _ambiguous(query, suffix)

    # "구로구" -> "구로구갑" / "구로구을"
    if not wanted_division:
        split = [
            name
            for name, value in normalized.items()
            if _split_division(value)[1] and _split_division(value)[0] in wanted_variants
        ]
        if len(split) == 1:
            return DistrictResolution(DistrictMatch.RESOLVED, split[0], "division", 0.9)
        if len(split) > 1:
            return _ambiguous(query, split)

    # "영도구" -> "중구영도구" (a district spanning several 구·시·군)
    if not strict:
        component = [
            name
            for name, value in normalized.items()
            if (not wanted_division or _split_division(value)[1] == wanted_division)
            and wanted_variants.intersection(district_components(value))
        ]
        if len(component) == 1:
            return DistrictResolution(
                DistrictMatch.RESOLVED,
                component[0],
                "component",
                0.7,
                warnings=[
                    f"'{query}' was matched to district '{component[0]}', which contains it as one of several areas."
                ],
            )
        if len(component) > 1:
            return _ambiguous(query, component)

    prefix = [name for name, value in normalized.items() if value.startswith(wanted)]
    if len(prefix) == 1:
        return DistrictResolution(DistrictMatch.RESOLVED, prefix[0], "prefix", 0.8)
    if len(prefix) > 1:
        return _ambiguous(query, prefix)

    suggestions = sorted(names, key=lambda name: similarity(name, query), reverse=True)[:5]
    return DistrictResolution(
        DistrictMatch.NOT_FOUND,
        options=suggestions,
        warnings=[
            f"District '{query}' was not found."
            + (f" Closest names: {', '.join(suggestions)}." if suggestions else "")
        ],
    )


def _ambiguous(query: str | None, options: list[str]) -> DistrictResolution:
    return DistrictResolution(
        DistrictMatch.AMBIGUOUS,
        options=options,
        warnings=[f"'{query}' matches several districts; specify one of: {', '.join(options)}."],
    )
