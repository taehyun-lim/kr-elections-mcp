from __future__ import annotations

from app.geo import resolve_sido, sido_key, sido_request_names, split_sido_prefix


def test_sido_key_is_era_independent():
    assert sido_key("강원도") == sido_key("강원특별자치도") == sido_key("강원")
    assert sido_key("전라북도") == sido_key("전북특별자치도")
    assert sido_key("서울") == sido_key("서울특별시")
    assert sido_key("부산직할시") == sido_key("부산광역시")
    assert sido_key("서울특별시") != sido_key("부산광역시")


def test_unknown_names_fall_back_to_normalized_text():
    assert sido_key("Metro City") == "metrocity"
    assert sido_key("합계") == "합계"


def test_gyeonggi_gwangju_city_is_not_gwangju_metropolitan_city():
    assert sido_key("광주시") != sido_key("광주광역시")


def test_resolve_sido_uses_the_name_valid_on_election_day():
    assert resolve_sido("전라북도", "20240410") == "전북특별자치도"
    assert resolve_sido("전북", "20200415") == "전라북도"
    assert resolve_sido("강원", "20220601") == "강원도"
    assert resolve_sido("강원도", "20240410") == "강원특별자치도"
    assert resolve_sido("제주", "20020613") == "제주도"
    assert resolve_sido("서울") == "서울특별시"
    assert resolve_sido("Metro City", "20240410") == "Metro City"


def test_request_names_try_resolved_name_first():
    names = sido_request_names("강원", "20220601")
    assert names[0] == "강원도"
    assert "강원특별자치도" in names


def test_split_sido_prefix_only_splits_on_whitespace():
    assert split_sido_prefix("서울 종로구") == ("서울", "종로구")
    assert split_sido_prefix("부산진구갑") == (None, "부산진구갑")
    assert split_sido_prefix("제주시갑") == (None, "제주시갑")
    assert split_sido_prefix("세종특별자치시갑") == (None, "세종특별자치시갑")
