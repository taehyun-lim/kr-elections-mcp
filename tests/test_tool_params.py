from __future__ import annotations

from pydantic import TypeAdapter

from app.tool_handlers import OptSgId, OptSgTypecode, SgTypecode


def test_numeric_codes_are_accepted_as_strings():
    # Clients that drop `anyOf` from optional params send "20240410" as a number.
    assert TypeAdapter(OptSgId).validate_python(20240410) == "20240410"
    assert TypeAdapter(OptSgTypecode).validate_python(2) == "2"
    assert TypeAdapter(SgTypecode).validate_python(2) == "2"
    assert TypeAdapter(OptSgTypecode).validate_python(None) is None
