"""Public API of the athletes app: the questionnaire flow and the engine input it produces."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _
from django_stubs_ext import StrOrPromise

from apps.athletes.forms import (
    DaysStepForm,
    RaceStepForm,
    RunningStepForm,
    TimeStepForm,
    YouStepForm,
)
from apps.athletes.models import Questionnaire
from apps.athletes.selectors import questionnaire_for
from apps.races.models import Race
from apps.races.services import engine_race
from engine import Env, PlanInput

__all__ = [
    "STEPS",
    "Step",
    "build_form",
    "next_step",
    "plan_input",
    "questionnaire_for",
    "save_step",
]


@dataclass(frozen=True)
class Step:
    slug: str
    title: StrOrPromise
    fields: tuple[str, ...]


STEPS: tuple[Step, ...] = (
    Step("race", _("السباق"), ("distance_km", "start_date")),
    Step("you", _("عنك"), ("age", "sex", "weight_kg")),
    Step("running", _("جريك دلوقتي"), ("runs_per_week", "weekly_km", "longest_km")),
    Step("time", _("سرعتك وهدفك"), ("recent_km", "recent_time_s", "goal", "goal_time_s")),
    Step("days", _("أيامك ومكانك"), ("days", "where", "gps", "kit")),
)
STEP_BY_SLUG = {s.slug: s for s in STEPS}
_FORMS: dict[str, type[forms.Form]] = {
    "race": RaceStepForm,
    "you": YouStepForm,
    "running": RunningStepForm,
    "time": TimeStepForm,
    "days": DaysStepForm,
}
# Form field name -> model field name where they differ.
_FIELD_MAP = {"recent_time": "recent_time_s", "goal_time": "goal_time_s"}


def start_questionnaire(session_key: str, race: Race) -> Questionnaire:
    return Questionnaire.objects.create(session_key=session_key, race=race)


def _initial(q: Questionnaire, form_class: type[forms.Form]) -> dict[str, Any]:
    initial: dict[str, Any] = {}
    for name in form_class.base_fields:
        value = getattr(q, _FIELD_MAP.get(name, name))
        if name == "gps" and value is not None:
            value = "yes" if value else "no"
        if name == "recent_km" and value is None and "time" in q.completed_steps:
            value = ""
        initial[name] = value
    return initial


def build_form(step: str, q: Questionnaire, today: date, data: Any = None) -> forms.Form:  # noqa: ANN401
    form_class = _FORMS[step]
    kwargs: dict[str, Any] = {"initial": _initial(q, form_class)}
    if step == "race":
        kwargs.update(race=q.race, today=today)
    if step == "time":
        kwargs["race"] = q.race
    return form_class(data, **kwargs)


def save_step(q: Questionnaire, step: str, cleaned: dict[str, Any]) -> None:
    for name, value in cleaned.items():
        setattr(q, _FIELD_MAP.get(name, name), value)
    if step not in q.completed_steps:
        q.completed_steps = [s.slug for s in STEPS if s.slug in {*q.completed_steps, step}]
    q.save()


def next_step(q: Questionnaire) -> str | None:
    """The first step not answered yet, or None when all are done."""
    return next((s.slug for s in STEPS if s.slug not in q.completed_steps), None)


def _hms(seconds: int | None) -> str | None:
    if seconds is None:
        return None
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def _float(value: Decimal | None) -> float:
    return float(value) if value is not None else 0.0


def plan_input(q: Questionnaire) -> PlanInput:
    """The engine input for a finished questionnaire (health answers are added in their step)."""
    race = engine_race(q.race, q.distance_km)
    if q.start_date is None:
        raise ValueError("questionnaire is not finished")
    return PlanInput(
        start_date=q.start_date,
        race_date=race.race_date,
        race_name=race.race_name,
        race_type="hyrox" if race.race_type == "hyrox" else "run",
        distance_km=race.distance_km or 21.1,
        race_id=race.race_id,
        age=q.age or 30,
        sex=q.sex or None,
        weight_kg=q.weight_kg,
        weekly_km=_float(q.weekly_km),
        longest_km=_float(q.longest_km),
        runs_per_week=q.runs_per_week or 0,
        recent_km=float(q.recent_km) if q.recent_km else None,
        recent_time=_hms(q.recent_time_s),
        goal=q.goal or "finish",
        goal_time=_hms(q.goal_time_s),
        days=tuple(q.days),
        injury="none",
        pain="none",
        env=Env(where=q.where or "outdoor", gps=bool(q.gps), kit=tuple(q.kit)),  # type: ignore[arg-type]
    )
