"""Training paces from the published Daniels & Gilbert VDOT formulas, and time parsing."""

import math
import re
from dataclasses import dataclass

from engine.jsmath import js_number, js_round


def vo2_at(v: float) -> float:
    """VO2 (ml/kg/min) at speed v in metres per minute."""
    return -4.6 + 0.182258 * v + 0.000104 * v * v


def pct_max(t: float) -> float:
    """Fraction of VO2max that can be held for t minutes."""
    return 0.8 + 0.1894393 * math.exp(-0.012778 * t) + 0.2989558 * math.exp(-0.1932605 * t)


def vdot_from(km: float, sec: float) -> float:
    t = sec / 60
    return vo2_at((km * 1000) / t) / pct_max(t)


def speed_for_vo2(vo2: float) -> float:
    a, b, c = 0.000104, 0.182258, -(4.6 + vo2)
    return (-b + math.sqrt(b * b - 4 * a * c)) / (2 * a)


def pace_at(vdot: float, frac: float) -> float:
    """Seconds per km at a fraction of VDOT."""
    return 60000 / speed_for_vo2(vdot * frac)


def predict_time(vdot: float, km: float) -> float:
    """Race time in seconds for a VDOT (bisection, same 60 steps as the reference)."""
    lo, hi = 5.0, 900.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if vdot_from(km, mid * 60) > vdot:
            lo = mid
        else:
            hi = mid
    return ((lo + hi) / 2) * 60


@dataclass(frozen=True)
class PaceTable:
    """Seconds per km."""

    easy_slow: float
    easy: float
    easy_fast: float
    marathon: float
    tempo: float
    interval: float
    rep: float

    def get(self, key: str) -> float:
        value: float = getattr(self, key)
        return value


def pace_table(vdot: float) -> PaceTable:
    return PaceTable(
        easy_slow=pace_at(vdot, 0.62),
        easy=pace_at(vdot, 0.70),
        easy_fast=pace_at(vdot, 0.74),
        marathon=pace_at(vdot, 0.80),
        tempo=pace_at(vdot, 0.88),
        interval=pace_at(vdot, 0.975),
        rep=pace_at(vdot, 1.04),
    )


def fmt_pace(sec: float) -> str:
    s = js_round(sec)
    return f"{s // 60}:{s % 60:02d}"


def fmt_time(sec: float) -> str:
    s = js_round(sec)
    h, m, x = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{x:02d}" if h else f"{m}:{x:02d}"


# A reading counts only if its pace is between 2:30 and 15:00 per km.
MIN_PACE = 150
MAX_PACE = 900
_ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_SEPARATORS = re.compile(r"[.,،:؛]+")


def parse_duration(text: str | None, km: float | None) -> float | None:
    """Read a time the way people type it, in seconds, or None when it makes no sense.

    "28" = 28 minutes, "28:00" = mm:ss, "1:55" for a half = 1h55. Arabic digits and
    "." or "," separators are accepted.
    """
    if text is None or str(text).strip() == "" or not km or math.isnan(km):
        return None
    norm = "".join(
        str(_ARABIC_DIGITS.index(ch)) if ch in _ARABIC_DIGITS else ch for ch in str(text).strip()
    )
    norm = _SEPARATORS.sub(":", norm)
    parts = [js_number(x) for x in norm.split(":") if x != ""]
    if not parts or len(parts) > 3 or any(not math.isfinite(x) or x < 0 for x in parts):
        return None
    if len(parts) == 1:
        cands = [parts[0] * 60, parts[0] * 3600]
    elif len(parts) == 2:
        cands = [parts[0] * 60 + parts[1], parts[0] * 3600 + parts[1] * 60]
    else:
        cands = [parts[0] * 3600 + parts[1] * 60 + parts[2]]
    for sec in cands:
        if MIN_PACE <= sec / km <= MAX_PACE and sec:
            return sec
    return None
