from __future__ import annotations

from app.models import District, Election, ListDistrictsOutput, ListElectionsOutput, ListPartiesOutput, Party
from app.resources import register_resources

SEOUL = "Seoul"
JONGNO = "Jongno"
DISTRICT_LABEL = f"{SEOUL} {JONGNO}"
ELECTION_NAME = "22nd National Assembly Election"
INDEPENDENT = "Independent"


class FakeMCP:
    def __init__(self) -> None:
        self.resources: dict[str, object] = {}

    def resource(self, uri: str):
        def decorator(fn):
            self.resources[uri] = fn
            return fn

        return decorator


class StubHandlers:
    def list_elections(self, payload):
        return ListElectionsOutput(
            items=[
                Election(
                    election_uid="20240410:2",
                    sg_id="20240410",
                    sg_typecode="2",
                    sg_name=ELECTION_NAME,
                    election_date="2024-04-10",
                )
            ]
        )

    def list_districts(self, payload):
        return ListDistrictsOutput(
            items=[
                District(
                    district_uid=f"{payload.sg_id}:{payload.sg_typecode}:seoul:jongno:strict",
                    sg_id=payload.sg_id,
                    sg_typecode=payload.sg_typecode,
                    sd_name=SEOUL,
                    sgg_name=JONGNO,
                    district_label=DISTRICT_LABEL,
                    canonical_name="SeoulJongno",
                    match_mode="strict",
                    aliases=[DISTRICT_LABEL, "SeoulJongno"],
                )
            ]
        )

    def list_parties(self, payload):
        return ListPartiesOutput(
            items=[
                Party(
                    party_uid=f"{payload.sg_id}:{payload.sg_typecode}:001",
                    sg_id=payload.sg_id,
                    sg_typecode=payload.sg_typecode,
                    party_code="001",
                    party_name=INDEPENDENT,
                )
            ]
        )


def test_register_resources_exposes_expected_payloads():
    mcp = FakeMCP()
    handlers = StubHandlers()

    register_resources(mcp, handlers)

    elections = mcp.resources["resource://nec/elections"]()
    districts = mcp.resources["resource://nec/districts/{sg_id}/{sg_typecode}"]("20240410", "2")
    parties = mcp.resources["resource://nec/parties/{sg_id}/{sg_typecode}"]("20240410", "2")

    assert elections["items"][0]["sg_id"] == "20240410"
    assert districts["items"][0]["district_label"] == DISTRICT_LABEL
    assert parties["items"][0]["party_name"] == INDEPENDENT
