from __future__ import annotations

import pytest

from app.district_resolver import DistrictMatch, district_components, resolve_district_name

SEOUL = ["종로구", "용산구", "구로구갑", "구로구을", "금천구"]
BUSAN = [
    "중구영도구", "서구동구", "부산진구갑", "부산진구을",
    "동래구", "남구", "북구갑", "북구을", "사하구갑", "사하구을",
]


@pytest.mark.parametrize(
    ("query", "available", "name", "method"),
    [
        ("종로구", SEOUL, "종로구", "exact"),
        ("종로", SEOUL, "종로구", "suffix"),
        ("구로갑", SEOUL, "구로구갑", "suffix"),
        ("사하갑", BUSAN, "사하구갑", "suffix"),
        ("부산진구갑", BUSAN, "부산진구갑", "exact"),
        ("남구", BUSAN, "남구", "exact"),
        ("영도구", BUSAN, "중구영도구", "component"),
    ],
)
def test_resolves(query, available, name, method):
    resolution = resolve_district_name(query, available)
    assert resolution.status == DistrictMatch.RESOLVED
    assert (resolution.name, resolution.method) == (name, method)


@pytest.mark.parametrize(
    ("query", "available", "options"),
    [
        ("구로구", SEOUL, ["구로구갑", "구로구을"]),
        ("북구", BUSAN, ["북구갑", "북구을"]),
        ("부산진", BUSAN, ["부산진구갑", "부산진구을"]),
    ],
)
def test_split_districts_are_ambiguous(query, available, options):
    resolution = resolve_district_name(query, available)
    assert resolution.status == DistrictMatch.AMBIGUOUS
    assert resolution.options == options
    assert resolution.warnings


def test_component_match_is_disabled_in_strict_mode():
    assert resolve_district_name("영도구", BUSAN, strict=True).status == DistrictMatch.NOT_FOUND


def test_not_found_returns_suggestions_without_a_threshold_match():
    resolution = resolve_district_name("강남구갑", SEOUL)
    assert resolution.status == DistrictMatch.NOT_FOUND
    assert resolution.name is None
    assert len(resolution.options) == 5


def test_district_components():
    assert district_components("중구영도구") == ["중구", "영도구"]
    assert district_components("북구강서구을") == ["북구", "강서구"]
    assert district_components("창원시의창구") == ["창원시", "의창구"]
