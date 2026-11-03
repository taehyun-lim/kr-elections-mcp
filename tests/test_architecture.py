"""Guards against reintroducing similarity-based row filtering in the results path."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app"
RESULT_MODULES = ["results_api.py", "tally.py", "geo.py", "scope.py", "nec_api.py"]


@pytest.mark.parametrize("module", RESULT_MODULES)
def test_result_modules_do_not_use_similarity(module):
    tree = ast.parse((APP / module).read_text(encoding="utf-8"))
    imported = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "similarity" not in imported
