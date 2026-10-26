"""engine/ is pure Python: no Django, no database, no network (CLAUDE.md)."""

import ast
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
ALLOWED_STDLIB = {"__future__", "dataclasses", "datetime", "math", "re", "typing", "collections"}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def test_engine_imports_only_the_standard_library():
    for path in ENGINE.glob("*.py"):
        bad = _imports(path) - ALLOWED_STDLIB - {"engine"}
        assert not bad, f"{path.name} imports {bad}"
        assert all(name in sys.stdlib_module_names or name == "engine" for name in _imports(path))
