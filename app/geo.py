"""Province (sido) naming across NEC eras.

NEC rows use the province name that was official on election day, so the same
province appears as "강원도" (before 2023-06-11) and "강원특별자치도" (after).
`sido_key()` gives an era-independent comparison key; `resolve_sido()` gives the
name NEC expects for a specific election.
"""
from __future__ import annotations

from dataclasses import dataclass

from .normalize import normalize_text


@dataclass(frozen=True)
class Sido:
    code: str
    # (effective_from_yyyymmdd, official name) in chronological order.
    names: tuple[tuple[str, str], ...]
    aliases: tuple[str, ...] = ()


SIDOS: tuple[Sido, ...] = (
    Sido("11", (("00000000", "서울특별시"),), ("서울", "서울시")),
    Sido(
        "26",
        (("00000000", "부산직할시"), ("19950101", "부산광역시")),
        ("부산", "부산시"),
    ),
    Sido(
        "27",
        (("00000000", "대구직할시"), ("19950101", "대구광역시")),
        ("대구", "대구시"),
    ),
    Sido(
        "28",
        (("00000000", "인천직할시"), ("19950101", "인천광역시")),
        ("인천", "인천시"),
    ),
    Sido(
        "29",
        (("00000000", "광주직할시"), ("19950101", "광주광역시")),
        # Deliberately no "광주시" alias: that is also a city in 경기도.
        ("광주",),
    ),
    Sido(
        "30",
        (("00000000", "대전직할시"), ("19950101", "대전광역시")),
        ("대전", "대전시"),
    ),
    Sido("31", (("19970715", "울산광역시"),), ("울산", "울산시")),
    Sido("36", (("20120701", "세종특별자치시"),), ("세종", "세종시")),
    Sido("41", (("00000000", "경기도"),), ("경기",)),
    Sido(
        "51",
        (("00000000", "강원도"), ("20230611", "강원특별자치도")),
        ("강원",),
    ),
    Sido("43", (("00000000", "충청북도"),), ("충북",)),
    Sido("44", (("00000000", "충청남도"),), ("충남",)),
    Sido(
        "52",
        (("00000000", "전라북도"), ("20240118", "전북특별자치도")),
        ("전북",),
    ),
    Sido("46", (("00000000", "전라남도"),), ("전남",)),
    Sido("47", (("00000000", "경상북도"),), ("경북",)),
    Sido("48", (("00000000", "경상남도"),), ("경남",)),
    Sido(
        "50",
        (("00000000", "제주도"), ("20060701", "제주특별자치도")),
        ("제주",),
    ),
)

_BY_CODE = {sido.code: sido for sido in SIDOS}
_ALIAS_TO_CODE: dict[str, str] = {}
for _sido in SIDOS:
    for _, _name in _sido.names:
        _ALIAS_TO_CODE[normalize_text(_name)] = _sido.code
    for _alias in _sido.aliases:
        _ALIAS_TO_CODE[normalize_text(_alias)] = _sido.code


def sido_code(name: str | None) -> str | None:
    """Return the stable province code for any era name or alias, else None."""
    return _ALIAS_TO_CODE.get(normalize_text(name))


def sido_key(name: str | None) -> str:
    """Era-independent comparison key. Unknown names fall back to normalized text."""
    code = sido_code(name)
    if code:
        return f"sido:{code}"
    return normalize_text(name)


def _date_stamp(sg_id: str | None) -> str | None:
    digits = "".join(character for character in str(sg_id or "") if character.isdigit())
    return digits[:8] if len(digits) >= 8 else None


def resolve_sido(name: str | None, sg_id: str | None = None) -> str | None:
    """Return the official NEC province name for the election date, or the input unchanged."""
    code = sido_code(name)
    if not code:
        return name.strip() if isinstance(name, str) else name
    names = _BY_CODE[code].names
    stamp = _date_stamp(sg_id)
    if stamp is None:
        return names[-1][1]
    selected = names[0][1]
    for effective_from, official in names:
        if stamp >= effective_from:
            selected = official
    return selected


def sido_request_names(name: str | None, sg_id: str | None = None) -> list[str]:
    """Names worth trying as the NEC `sdName` parameter, most likely first."""
    candidates: list[str] = []
    resolved = resolve_sido(name, sg_id)
    for value in (resolved, name.strip() if isinstance(name, str) else None):
        if value and value not in candidates:
            candidates.append(value)
    code = sido_code(name)
    if code:
        for _, official in reversed(_BY_CODE[code].names):
            if official not in candidates:
                candidates.append(official)
    return candidates


def split_sido_prefix(text: str | None) -> tuple[str | None, str]:
    """Split a leading province token off "서울 종로구"-style input.

    Only splits on whitespace: glued input such as "부산진구갑" or "제주시갑" must
    not be cut, because their leading characters look like province aliases.
    """
    if not text:
        return None, ""
    stripped = text.strip()
    parts = stripped.split(None, 1)
    if len(parts) == 2 and sido_code(parts[0]):
        return parts[0], parts[1].strip()
    if len(parts) == 1 and sido_code(parts[0]):
        return parts[0], ""
    return None, stripped
