"""Per election-type scope rules (NEC sgTypecode 0-11)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ScopeLevel = Literal["national", "sido", "sgg", "wiw"]


@dataclass(frozen=True)
class ScopeRule:
    label: str
    # Level at which one contest (one ranking of candidates) happens.
    level: ScopeLevel
    # Seats per contest; >1 means several winners per district.
    seats: int
    has_party: bool
    # True when the turnout API reports rows at the same level as the contest.
    turnout_aligned: bool
    # True when the contest ranks parties (proportional lists), not people.
    party_list: bool = False


SCOPE_RULES: dict[str, ScopeRule] = {
    "1": ScopeRule("대통령선거", "national", 1, True, True),
    "2": ScopeRule("국회의원선거", "sgg", 1, True, False),
    "3": ScopeRule("시·도지사선거", "sido", 1, True, True),
    "4": ScopeRule("구·시·군의 장선거", "sgg", 1, True, True),
    "5": ScopeRule("시·도의회의원선거", "sgg", 1, True, False),
    "6": ScopeRule("구·시·군의회의원선거", "sgg", 2, True, False),
    "7": ScopeRule("국회의원 비례대표", "national", 1, True, False, party_list=True),
    "8": ScopeRule("광역의원 비례대표", "sido", 1, True, False, party_list=True),
    "9": ScopeRule("기초의원 비례대표", "wiw", 1, True, False, party_list=True),
    "10": ScopeRule("교육의원선거", "sgg", 1, False, False),
    "11": ScopeRule("교육감선거", "sido", 1, False, True),
}

DEFAULT_RULE = ScopeRule("알 수 없는 선거", "sgg", 1, True, False)


def scope_rule(sg_typecode: str | None) -> ScopeRule:
    return SCOPE_RULES.get(str(sg_typecode or "").strip(), DEFAULT_RULE)


def requires_sgg_name(sg_typecode: str | None) -> bool:
    """True when a province holds several contests, so a district must be named."""
    return scope_rule(sg_typecode).level in {"sgg", "wiw"}
