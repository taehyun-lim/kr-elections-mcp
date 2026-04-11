from __future__ import annotations

import json

from .models import ListDistrictsInput, ListElectionsInput, ListPartiesInput
from .tool_handlers import ToolHandlers

def _resource_json(data: object) -> str:
    """MCP resource bodies must be str/bytes/list, not raw dicts."""
    return json.dumps(data, ensure_ascii=False, indent=2)

def register_resources(mcp, handlers: ToolHandlers) -> None:
    def elections_json() -> str:
        return _resource_json(handlers.list_elections(ListElectionsInput()).model_dump())

    @mcp.resource("resource://nec/elections", mime_type="application/json")
    def elections_resource():
        return elections_json()

    def districts_json(sg_id: str, sg_typecode: str) -> str:
        return _resource_json(
            handlers.list_districts(
                ListDistrictsInput(sg_id=sg_id, sg_typecode=sg_typecode)
            ).model_dump()
        )

    @mcp.resource(
        "resource://nec/districts/{sg_id}/{sg_typecode}",
        mime_type="application/json",
    )
    def districts_resource(sg_id: str, sg_typecode: str):
        return districts_json(sg_id, sg_typecode)

    def parties_json(sg_id: str, sg_typecode: str) -> str:
        return _resource_json(
            handlers.list_parties(
                ListPartiesInput(sg_id=sg_id, sg_typecode=sg_typecode)
            ).model_dump()
        )

    @mcp.resource(
        "resource://nec/parties/{sg_id}/{sg_typecode}",
        mime_type="application/json",
    )
    def parties_resource(sg_id: str, sg_typecode: str):
        return parties_json(sg_id, sg_typecode)

