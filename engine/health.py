"""Health screen (PAR-Q style). Any yes blocks the plan until a doctor clears the athlete."""

from dataclasses import dataclass

from engine.data import HEALTH_QUESTIONS
from engine.types import HealthAnswers


@dataclass(frozen=True)
class ScreenResult:
    ok: bool
    reasons: list[str]


def screen(answers: HealthAnswers) -> ScreenResult:
    yes = set(answers.yes())
    reasons = [q.id for q in HEALTH_QUESTIONS if q.id in yes]
    return ScreenResult(ok=not reasons, reasons=reasons)
