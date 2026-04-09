from __future__ import annotations

from app.models import Candidate, CandidateRef
from app.normalize import canonicalize_district, map_party_name, score_candidate_match

SEOUL = "\uc11c\uc6b8\ud2b9\ubcc4\uc2dc"
JONGNO = "\uc885\ub85c\uad6c"
BUSAN = "\ubd80\uc0b0\uad11\uc5ed\uc2dc"
HAEUNDAE = "\ud574\uc6b4\ub300\uad6c"
HONG = "\ud64d\uae38\ub3d9"
KIM = "\uae40\ucca0\uc218"
PPP_ALIAS = "\uad6d\ud798"
PPP = "\uad6d\ubbfc\uc758\ud798"
DPK_ALIAS = "\ub354\ubbfc\uc8fc"
DPK = "\ub354\ubd88\uc5b4\ubbfc\uc8fc\ub2f9"
JP = "\uc815\uc758\ub2f9"


def test_map_party_name_resolves_aliases():
    assert map_party_name(PPP_ALIAS) == PPP
    assert map_party_name(DPK_ALIAS) == DPK


def test_score_candidate_match_emits_low_confidence_warning():
    district = canonicalize_district("20240410", "2", SEOUL, JONGNO)
    candidate = Candidate(
        candidate_ref=CandidateRef(
            sg_id="20240410",
            sg_typecode="2",
            huboid="H1",
            candidate_name=HONG,
            district_label=district.district_label,
            party_name=DPK,
            giho="1",
        ),
        district=district,
        party_name=DPK,
        giho="1",
    )

    match = score_candidate_match(
        candidate,
        {
            "huboid": "H2",
            "huboNm": KIM,
            "jdName": JP,
            "giho": "9",
            "sdName": BUSAN,
            "sggName": HAEUNDAE,
        },
        district_label=district.district_label,
    )

    assert match.match_confidence < 0.45
    assert "Low confidence result match." in match.warnings