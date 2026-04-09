from __future__ import annotations

from app.models import ListPartiesOutput, Party
from app.tool_handlers import register_tools


class FakeMCP:
    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self, fn):
        self.tools[fn.__name__] = fn
        return fn


class StubHandlers:
    def list_parties(self, payload):
        return ListPartiesOutput(
            items=[
                Party(
                    party_uid=f"{payload.sg_id}:{payload.sg_typecode}:001",
                    sg_id=payload.sg_id,
                    sg_typecode=payload.sg_typecode,
                    party_code="001",
                    party_name="Independent",
                )
            ]
        )


def test_register_tools_exposes_list_parties():
    mcp = FakeMCP()
    handlers = StubHandlers()

    register_tools(mcp, handlers)

    payload = mcp.tools["list_parties"]("20240410", "2")

    assert payload["items"][0]["party_name"] == "Independent"
