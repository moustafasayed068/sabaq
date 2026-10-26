"""Numeric helpers that behave exactly like the JavaScript reference.

The golden files were produced by JavaScript, so rounding, number parsing and
number-to-text must match it bit for bit.
"""

import math
import re

_JS_INT_PREFIX = re.compile(r"^0([xob])([0-9a-f]+)$", re.IGNORECASE)
_JS_DECIMAL = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)(e[+-]?\d+)?$", re.IGNORECASE)


def js_round(x: float) -> int:
    """JavaScript Math.round: halves round up (Python's round() rounds them to even)."""
    return math.floor(x + 0.5)


def round1(x: float) -> float:
    return js_round(x * 10) / 10


def round_half(x: float) -> float:
    return js_round(x * 2) / 2


def fmt_num(x: float) -> str:
    """Number to text like JavaScript's String(x): 3 -> "3", 2.5 -> "2.5"."""
    if isinstance(x, bool):
        raise TypeError("booleans are not numbers here")
    if isinstance(x, int):
        return str(x)
    if math.isfinite(x) and x == math.floor(x) and abs(x) < 1e21:
        return str(int(x))
    return repr(x)


def js_number(text: str) -> float:
    """JavaScript Number(text) for strings; NaN where JavaScript gives NaN."""
    s = text.strip()
    if s == "":
        return 0.0
    if s in ("Infinity", "+Infinity"):
        return math.inf
    if s == "-Infinity":
        return -math.inf
    prefixed = _JS_INT_PREFIX.match(s)
    if prefixed:
        base = {"x": 16, "o": 8, "b": 2}[prefixed.group(1).lower()]
        try:
            return float(int(prefixed.group(2), base))
        except ValueError:
            return math.nan
    if _JS_DECIMAL.match(s):
        return float(s)
    return math.nan


def js_plus(value: object) -> float:
    """JavaScript unary plus (+value) for the value types the engine receives."""
    if value is None:
        return math.nan
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        return js_number(value)
    return math.nan


def num_or(value: object, default: float) -> float:
    """JavaScript `+value || default`: NaN and 0 fall back to the default."""
    x = js_plus(value)
    if math.isnan(x) or x == 0:
        return default
    return x


def js_sum(values: list[float]) -> float:
    """Left-to-right float sum like Array.reduce. Python 3.12's sum() is compensated
    (Neumaier), which can differ from JavaScript in the last bit."""
    total = 0.0
    for v in values:
        total += v
    return total
