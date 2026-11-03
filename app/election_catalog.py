"""Built-in calendar of regular NEC elections.

Used when the NEC code API (CommonCodeService) is unavailable, which happens
with keys that are approved for the result APIs but not the code API. By-elections
are not listed.
"""
from __future__ import annotations

from .models import Election, ProvenanceRecord

PRESIDENTIAL = (
    ("19871216", 13), ("19921218", 14), ("19971218", 15), ("20021219", 16), ("20071219", 17),
    ("20121219", 18), ("20170509", 19), ("20220309", 20), ("20250603", 21),
)
NATIONAL_ASSEMBLY = (
    ("19880426", 13), ("19920324", 14), ("19960411", 15), ("20000413", 16), ("20040415", 17),
    ("20080409", 18), ("20120411", 19), ("20160413", 20), ("20200415", 21), ("20240410", 22),
)
LOCAL = (
    ("19950627", 1), ("19980604", 2), ("20020613", 3), ("20060531", 4), ("20100602", 5),
    ("20140604", 6), ("20180613", 7), ("20220601", 8), ("20260603", 9),
)

TYPE_NAMES = {
    "1": "대통령선거",
    "2": "국회의원선거",
    "3": "시·도지사선거",
    "4": "구·시·군의 장선거",
    "5": "시·도의회의원선거",
    "6": "구·시·군의회의원선거",
    "7": "국회의원선거(비례대표)",
    "8": "광역의원선거(비례대표)",
    "9": "기초의원선거(비례대표)",
    "10": "교육의원선거",
    "11": "교육감선거",
}

CALENDAR_WARNING = (
    "NEC election code list was unavailable; elections were taken from the built-in "
    "calendar of regular elections (by-elections are not included)."
)


def _local_types(sg_id: str) -> tuple[str, ...]:
    types = ["3", "4", "5", "6", "8"]
    if sg_id >= "20060531":
        types.append("9")
    if sg_id >= "20100602":
        types.extend(["10", "11"])
    return tuple(types)


def _election(sg_id: str, sg_typecode: str, ordinal: int, office: str) -> Election:
    date_text = f"{sg_id[:4]}-{sg_id[4:6]}-{sg_id[6:]}"
    return Election(
        election_uid=f"{sg_id}:{sg_typecode}",
        sg_id=sg_id,
        sg_typecode=sg_typecode,
        sg_name=f"제{ordinal}회 {office}" if office.startswith("전국") else f"제{ordinal}대 {office}",
        election_date=date_text,
        provenance=[ProvenanceRecord(source_name="builtin_calendar", entity_type="election", source_ref=f"{sg_id}:{sg_typecode}")],
    )


def calendar_elections() -> list[Election]:
    items: list[Election] = []
    for sg_id, ordinal in PRESIDENTIAL:
        items.append(_election(sg_id, "1", ordinal, TYPE_NAMES["1"]))
    for sg_id, ordinal in NATIONAL_ASSEMBLY:
        items.append(_election(sg_id, "2", ordinal, TYPE_NAMES["2"]))
        items.append(_election(sg_id, "7", ordinal, TYPE_NAMES["7"]))
    for sg_id, ordinal in LOCAL:
        for sg_typecode in _local_types(sg_id):
            election = _election(sg_id, sg_typecode, ordinal, "전국동시지방선거")
            election.sg_name = f"{election.sg_name} ({TYPE_NAMES[sg_typecode]})"
            items.append(election)
    items.sort(key=lambda item: (item.sg_id, int(item.sg_typecode)))
    return items


def filter_elections(
    items: list[Election],
    *,
    sg_typecode: str | None = None,
    year_from: int | None = None,
    year_to: int | None = None,
) -> list[Election]:
    filtered = []
    for item in items:
        year = int(item.sg_id[:4]) if item.sg_id[:4].isdigit() else None
        if sg_typecode and item.sg_typecode != sg_typecode:
            continue
        if year_from and year and year < year_from:
            continue
        if year_to and year and year > year_to:
            continue
        filtered.append(item)
    return filtered


def calendar_election(sg_id: str, sg_typecode: str) -> Election | None:
    return next(
        (item for item in calendar_elections() if item.sg_id == sg_id and item.sg_typecode == sg_typecode),
        None,
    )
