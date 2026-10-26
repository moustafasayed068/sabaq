"""Runtime code must not import dev-only packages (the production image does not have them)."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEV_ONLY = {"django_stubs_ext", "pytest", "debug_toolbar", "mypy", "ruff"}


def _runtime_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    guarded: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and "TYPE_CHECKING" in ast.unparse(node.test):
            guarded |= {id(n) for child in node.body for n in ast.walk(child)}
        if isinstance(node, ast.Try):  # optional imports, e.g. debug_toolbar in dev.py
            guarded |= {id(n) for child in node.body for n in ast.walk(child)}
    names: set[str] = set()
    for node in ast.walk(tree):
        if id(node) in guarded:
            continue
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def test_no_dev_only_imports_at_runtime():
    for folder in ("apps", "engine", "sabaq"):
        for path in (ROOT / folder).rglob("*.py"):
            if "tests" in path.parts or path.name == "conftest.py":
                continue
            bad = _runtime_imports(path) & DEV_ONLY
            assert not bad, f"{path.relative_to(ROOT)} imports {bad} at runtime"
