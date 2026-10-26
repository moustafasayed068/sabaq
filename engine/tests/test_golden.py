"""Every golden file in reference/engine-js/golden must be reproduced exactly."""

import json
from pathlib import Path
from typing import Any

import pytest

from engine import CheckInFeedback, PlanInput, check_in, generate

GOLDEN_DIR = Path(__file__).resolve().parents[2] / "reference" / "engine-js" / "golden"
GOLDEN_FILES = sorted(GOLDEN_DIR.glob("*.json"))


def diff(expected: Any, actual: Any, path: str = "$") -> list[str]:
    """Strict comparison: same keys, same values; bool is never equal to a number."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        out = [f"{path}: missing key {k!r}" for k in expected if k not in actual]
        out += [f"{path}: unexpected key {k!r}" for k in actual if k not in expected]
        for k in expected:
            if k in actual:
                out += diff(expected[k], actual[k], f"{path}.{k}")
        return out
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return [f"{path}: length {len(actual)} != expected {len(expected)}"]
        return [
            e
            for i, (a, b) in enumerate(zip(expected, actual, strict=True))
            for e in diff(a, b, f"{path}[{i}]")
        ]
    numeric = (int, float)
    if isinstance(expected, bool) or isinstance(actual, bool):
        same = type(expected) is type(actual) and expected == actual
    elif isinstance(expected, numeric) and isinstance(actual, numeric):
        same = expected == actual
    else:
        same = type(expected) is type(actual) and expected == actual
    return [] if same else [f"{path}: {actual!r} != expected {expected!r}"]


def test_there_are_golden_files():
    assert len(GOLDEN_FILES) == 21


@pytest.mark.parametrize("path", GOLDEN_FILES, ids=lambda p: p.stem)
def test_golden(path: Path):
    case = json.loads(path.read_text(encoding="utf-8"))
    inp = PlanInput.from_dict(case["input"])
    if "output" in case:
        actual = generate(inp).to_dict()
        problems = diff(case["output"], actual)
    else:
        plan = generate(inp)
        result = check_in(inp, plan, 0, CheckInFeedback.from_dict(case["feedback"]))
        problems = diff(case["checkIn"], result.to_dict(), "$.checkIn")
        next_plan = None if result.action == "paused" else generate(result.input).to_dict()
        problems += diff(case["nextPlan"], next_plan, "$.nextPlan")
    assert not problems, "\n".join(problems[:20])
