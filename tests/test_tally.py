from __future__ import annotations

from app.tally import (
    Slot,
    build_district_tallies,
    expand_tally_row,
    match_winners,
    nec_share,
    ranked,
)
from tests.fixtures.nec_stub import load_fixture

SEOUL = "서울특별시"


def test_expand_tally_row_skips_empty_slots_but_keeps_zero_vote_candidates():
    row = {
        "hbj01": "A", "jd01": "P1", "dugsu01": "10",
        "hbj02": "B", "jd02": "P2", "dugsu02": "0",
        "hbj03": "", "jd03": "", "dugsu03": "0",
    }
    assert expand_tally_row(row) == (Slot(1, "A", "P1", 10), Slot(2, "B", "P2", 0))


def test_build_district_tallies_uses_total_rows_and_keeps_sub_rows_separate():
    tallies = build_district_tallies(load_fixture("20240410_2_busan_tally.json")["tally_rows"])
    tally = next(t for t in tallies.values() if t.sgg_name == "중구영도구")

    assert tally.total is not None
    assert [sub.wiw_name for sub in tally.subs] == ["중구", "영도구"]
    assert tally.rollup.valid == 84367
    assert [slot.votes for slot in tally.rollup.slots] == [36739, 46254, 1374]
    assert tally.warnings == []
    assert len(tallies) == 18


def test_rollup_is_summed_only_within_one_district_when_total_row_is_missing():
    rows = [row for row in load_fixture("20240410_2_busan_tally.json")["tally_rows"] if row["wiwName"] != "합계"]
    tallies = build_district_tallies(rows)
    tally = next(t for t in tallies.values() if t.sgg_name == "중구영도구")

    assert tally.rollup.synthetic
    assert tally.rollup.electorate == 132866
    assert [slot.votes for slot in tally.rollup.slots] == [36739, 46254, 1374]
    single = next(t for t in tallies.values() if t.sgg_name == "동래구")
    assert single.rollup.valid == 157212
    assert not single.rollup.synthetic


def test_nec_share_truncates_like_nec():
    assert nec_share(57788, 96529) == 59.86
    assert nec_share(44713, 87809) == 50.92
    assert nec_share(2835, 87809) == 3.22
    assert nec_share(1, 0) is None
    assert nec_share(None, 100) is None


def test_ranked_uses_competition_ranking_for_ties():
    slots = [Slot(1, "A", "P", 10), Slot(2, "B", "P", 30), Slot(3, "C", "P", 10), Slot(4, "D", "P", 1)]
    assert [(rank, slot.name) for rank, slot in ranked(slots)] == [(1, "B"), (2, "A"), (2, "C"), (4, "D")]


def test_match_winners_uses_party_for_namesakes_and_never_guesses():
    slots = [Slot(1, "Kim", "P1", 10), Slot(2, "Kim", "P2", 20), Slot(3, "Lee", "P3", 5)]
    matched = match_winners(slots, [{"name": "Kim", "jdName": "P2", "huboid": "H2"}])
    assert list(matched) == [2]

    ambiguous = match_winners(slots, [{"name": "Kim", "jdName": "P9"}])
    assert ambiguous == {}


def test_seoul_fixture_integrity_checks_pass():
    tallies = build_district_tallies(load_fixture("20240410_2_seoul.json")["tally_rows"])
    assert all(t.warnings == [] for t in tallies.values())
    assert {t.sgg_name for t in tallies.values()} == {
        "종로구", "용산구", "구로구갑", "구로구을", "금천구"
    }
