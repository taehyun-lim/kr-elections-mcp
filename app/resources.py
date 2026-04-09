from __future__ import annotations

from .models import ListDistrictsInput, ListElectionsInput, ListPartiesInput
from .tool_handlers import ToolHandlers


def register_resources(mcp, handlers: ToolHandlers) -> None:
    @mcp.resource("resource://nec/elections")
    def elections_resource():
        return handlers.list_elections(ListElectionsInput()).model_dump()

    @mcp.resource("resource://nec/districts/{sg_id}/{sg_typecode}")
    def districts_resource(sg_id: str, sg_typecode: str):
        return handlers.list_districts(
            ListDistrictsInput(sg_id=sg_id, sg_typecode=sg_typecode)
        ).model_dump()

    @mcp.resource("resource://nec/parties/{sg_id}/{sg_typecode}")
    def parties_resource(sg_id: str, sg_typecode: str):
        return handlers.list_parties(ListPartiesInput(sg_id=sg_id, sg_typecode=sg_typecode)).model_dump()
