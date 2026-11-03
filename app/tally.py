"""Pure parsing of NEC tally (개표) rows. No I/O, no election-type logic.

The tally API returns *wide* rows: one row per area with up to 50 candidate slots
(`hbjNN` name, `jdNN` party, `dugsuNN` votes) plus area metrics
(`sunsu`/`tusu`/`yutusu`/`mutusu`/`gigwonsu`). Each district appears once as a
`wiwName == "합계"` total row and once per 구·시·군 sub-area. Metrics must come
from exactly one of those rows; summing them double counts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator

from .coerce import as_int, as_str
from .geo import sido_key
from .normalize import first_of, normalize_candidate_name, normalize_party_name, normalize_text

TOTAL_WIW_NAME = "합계"  # 합계
MAX_SLOTS = 50


@dataclass(frozen=True)
class Slot:
    ballot_position: int
    name: str | None
    party: str | None
    votes: int | None


@dataclass
class AreaRow:
    sd_name: str | None
    sgg_name: str | None
    wiw_name: str | None
    electorate: int | None
    turnout: int | None
    valid: int | None
    invalid: int | None
    abstention: int | None
    slots: tuple[Slot, ...]
    raw: dict[str, Any] = field(default_factory=dict)
    synthetic: bool = False

    @property
    def is_total(self) -> bool:
        return (self.wiw_name or "") == TOTAL_WIW_NAME


@dataclass
class DistrictTally:
    key: tuple[str, str]
    sd_name: str | None
    sgg_name: str | None
    total: AreaRow | None = None
    subs: list[AreaRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def rollup(self) -> AreaRow:
        """The district-level row: the NEC 합계 row, or a derived one."""
        if self.total is not None:
            return self.total
        return _synthesize_total(self)

    def find_sub(self, wiw_name: str | None) -> AreaRow | None:
        target = normalize_text(wiw_name)
        if not target:
            return None
        for sub in self.subs:
            if normalize_text(sub.wiw_name) == target:
                return sub
        return None


def expand_tally_row(row: dict[str, Any]) -> tuple[Slot, ...]:
    """Expand the 50 wide candidate slots of one tally row, dropping empty slots.

    Empty slots come back as ('', '', '0'), so emptiness is decided by name and
    party, never by the vote count alone.
    """
    slots: list[Slot] = []
    for index in range(1, MAX_SLOTS + 1):
        suffix = f"{index:02d}"
        name = as_str(row.get(f"hbj{suffix}"))
        party = as_str(row.get(f"jd{suffix}"))
        if name is None and party is None:
            continue
        slots.append(Slot(index, name, party, as_int(row.get(f"dugsu{suffix}"))))
    return tuple(slots)


def is_wide_tally_row(row: dict[str, Any]) -> bool:
    """True for tally-API rows (wide slots and/or area metrics), false for long-format candidate rows."""
    if any(f"hbj{index:02d}" in row or f"jd{index:02d}" in row for index in (1, 2)):
        return True
    return "yutusu" in row or "sunsu" in row


def area_row(row: dict[str, Any]) -> AreaRow:
    return AreaRow(
        sd_name=as_str(first_of(row, "sdName", "sd_name")),
        sgg_name=as_str(first_of(row, "sggName", "sgg_name")),
        wiw_name=as_str(first_of(row, "wiwName", "wiw_name")),
        electorate=as_int(first_of(row, "sunsu")),
        turnout=as_int(first_of(row, "tusu")),
        valid=as_int(first_of(row, "yutusu")),
        invalid=as_int(first_of(row, "mutusu")),
        abstention=as_int(first_of(row, "gigwonsu")),
        slots=expand_tally_row(row),
        raw=row,
    )


def district_key(sd_name: str | None, sgg_name: str | None) -> tuple[str, str]:
    return sido_key(sd_name), normalize_text(sgg_name)


def build_district_tallies(rows: Iterable[dict[str, Any]]) -> dict[tuple[str, str], DistrictTally]:
    """Group wide tally rows by (province, district), keeping NEC order."""
    tallies: dict[tuple[str, str], DistrictTally] = {}
    for row in rows:
        area = area_row(row)
        key = district_key(area.sd_name, area.sgg_name)
        tally = tallies.get(key)
        if tally is None:
            tally = DistrictTally(key=key, sd_name=area.sd_name, sgg_name=area.sgg_name)
            tallies[key] = tally
        if area.is_total:
            if tally.total is None:
                tally.total = area
            continue
        tally.subs.append(area)
    for tally in tallies.values():
        tally.warnings.extend(integrity_warnings(tally.rollup))
    return tallies


def _synthesize_total(tally: DistrictTally) -> AreaRow:
    if len(tally.subs) == 1:
        return tally.subs[0]
    votes_by_position: dict[int, int | None] = {}
    first_slot: dict[int, Slot] = {}
    for sub in tally.subs:
        for slot in sub.slots:
            first_slot.setdefault(slot.ballot_position, slot)
            current = votes_by_position.get(slot.ballot_position, 0)
            votes_by_position[slot.ballot_position] = (
                None if current is None or slot.votes is None else current + slot.votes
            )
    slots = tuple(
        Slot(position, first_slot[position].name, first_slot[position].party, votes_by_position[position])
        for position in sorted(first_slot)
    )
    synthesized = AreaRow(
        sd_name=tally.sd_name,
        sgg_name=tally.sgg_name,
        wiw_name=TOTAL_WIW_NAME,
        electorate=_sum(sub.electorate for sub in tally.subs),
        turnout=_sum(sub.turnout for sub in tally.subs),
        valid=_sum(sub.valid for sub in tally.subs),
        invalid=_sum(sub.invalid for sub in tally.subs),
        abstention=_sum(sub.abstention for sub in tally.subs),
        slots=slots,
        synthetic=True,
    )
    message = (
        f"No NEC total (합계) row for {tally.sgg_name or tally.sd_name}; "
        f"district figures were summed from {len(tally.subs)} sub-area rows."
    )
    if message not in tally.warnings:
        tally.warnings.append(message)
    return synthesized


def _sum(values: Iterable[int | None]) -> int | None:
    total = 0
    for value in values:
        if value is None:
            return None
        total += value
    return total


def integrity_warnings(area: AreaRow) -> list[str]:
    warnings: list[str] = []
    label = " ".join(part for part in (area.sgg_name, area.wiw_name) if part) or (area.sd_name or "area")
    votes = [slot.votes for slot in area.slots]
    if area.valid is not None and votes and all(value is not None for value in votes):
        slot_total = sum(value for value in votes if value is not None)
        if slot_total != area.valid:
            warnings.append(f"{label}: candidate votes sum to {slot_total} but NEC valid votes are {area.valid}.")
    if area.valid is not None and area.invalid is not None and area.turnout is not None:
        if area.valid + area.invalid != area.turnout:
            warnings.append(
                f"{label}: valid ({area.valid}) + invalid ({area.invalid}) votes do not equal turnout ({area.turnout})."
            )
    return warnings


def nec_share(votes: int | None, valid: int | None) -> float | None:
    """Vote share the way NEC publishes it: truncated (not rounded) to 2 decimals."""
    if votes is None or not valid:
        return None
    return (votes * 10000 // valid) / 100


def turnout_rate(turnout: int | None, electorate: int | None) -> float | None:
    if turnout is None or not electorate:
        return None
    return round(turnout / electorate * 100, 3)


def match_winners(
    slots: Iterable[Slot],
    winner_rows: Iterable[dict[str, Any]],
    *,
    has_party: bool = True,
) -> dict[int, dict[str, Any]]:
    """Join winner rows onto slots by name, using party to separate namesakes.

    Returns {ballot_position: winner_row}. A winner that cannot be placed on
    exactly one slot is left out rather than guessed.
    """
    slot_list = list(slots)
    matched: dict[int, dict[str, Any]] = {}
    for winner in winner_rows:
        name = normalize_candidate_name(as_str(first_of(winner, "name", "huboNm")))
        if not name:
            continue
        options = [slot for slot in slot_list if normalize_candidate_name(slot.name) == name]
        if len(options) > 1 and has_party:
            party = normalize_party_name(as_str(first_of(winner, "jdName", "partyName")))
            options = [slot for slot in options if normalize_party_name(slot.party) == party]
        if len(options) == 1 and options[0].ballot_position not in matched:
            matched[options[0].ballot_position] = winner
    return matched


def ranked(slots: Iterable[Slot]) -> Iterator[tuple[int, Slot]]:
    """Yield (competition rank, slot) by votes descending; ties share a rank."""
    ordered = sorted(slots, key=lambda slot: (-(slot.votes or 0), slot.ballot_position))
    previous_votes: int | None = None
    rank = 0
    for index, slot in enumerate(ordered, start=1):
        if slot.votes != previous_votes:
            rank = index
            previous_votes = slot.votes
        yield rank, slot
