"""Public API of the plans app: preview a plan, and store it for a signed-in athlete."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.db import transaction

from apps.athletes.models import Questionnaire
from apps.athletes.services import plan_input
from apps.plans.models import Plan, PlanDay, PlanStatus, PlanWeek
from apps.plans.selectors import active_plan
from engine import ENGINE_VERSION, generate
from engine.types import Plan as EnginePlan

if TYPE_CHECKING:
    from apps.accounts.models import User

__all__ = ["CannotSavePlanError", "active_plan", "create_plan", "preview"]


class CannotSavePlanError(Exception):
    """The engine blocked this plan (health, pain, age, date or feasibility)."""


def preview(q: Questionnaire) -> EnginePlan:
    """Run the engine on the answers; nothing is stored."""
    return generate(plan_input(q))


def _summary(result: EnginePlan) -> dict[str, Any]:
    data = result.to_dict()
    keys = (
        "paces",
        "peakLong",
        "peakWeekly",
        "goalVerdict",
        "timeRead",
        "raceDayTips",
        "levelName",
    )
    return {k: data[k] for k in keys if k in data}


@transaction.atomic
def create_plan(user: User, q: Questionnaire) -> Plan:
    """Generate and store the plan. The user's previous plans stop being active."""
    if q.user_id != user.pk:
        raise PermissionError("not this athlete's questionnaire")
    inp = plan_input(q)
    result = generate(inp)
    if result.status == "blocked":
        raise CannotSavePlanError(result.block_kind)
    Plan.objects.filter(user=user, is_active=True).update(is_active=False)
    plan = Plan.objects.create(
        user=user,
        questionnaire=q,
        race=q.race,
        distance_km=q.distance_km,
        race_date=inp.race_date,
        starts_on=inp.start_date,
        engine_version=ENGINE_VERSION,
        engine_input=inp.to_dict(),  # type: ignore[misc]  # encrypted JSON (stubs see text)
        status=PlanStatus(result.status),
        level=result.level or "",
        messages=result.messages,
        warnings=result.warnings,
        summary=_summary(result),
    )
    days: list[PlanDay] = []
    for wk in result.weeks:
        week = PlanWeek.objects.create(
            plan=plan,
            index=wk.index,
            start=wk.start,
            phase=wk.phase,
            phase_name=wk.phase_name,
            target_km=wk.target_km,
            km=Decimal(str(wk.km)),
        )
        for d in wk.days:
            if d.role == "off":
                continue
            w = d.workout
            days.append(
                PlanDay(
                    week=week,
                    plan=plan,
                    date=d.date,
                    day_name=d.day_name,
                    role=d.role,
                    kind=w.kind if w else "",
                    title=w.title if w else "",
                    intensity=w.intensity if w else 0,
                    km=Decimal(str(w.km)) if w else Decimal(0),
                    steps=w.steps if w else [],
                    extra=w.extra.to_dict() if w and w.extra else None,
                )
            )
    PlanDay.objects.bulk_create(days)
    return plan


# ---------------------------------------------------------------- display


@dataclass(frozen=True)
class DayView:
    date: date
    day_name: str
    role: str
    kind: str
    title: str
    km: float
    steps: list[str]
    extra: dict[str, Any] | None


@dataclass(frozen=True)
class WeekView:
    number: int
    phase_name: str
    km: float
    days: list[DayView]


def weeks_from_engine(result: EnginePlan) -> list[WeekView]:
    return [
        WeekView(
            number=wk.index + 1,
            phase_name=wk.phase_name,
            km=wk.km,
            days=[
                DayView(
                    date=d.date,
                    day_name=d.day_name,
                    role=d.role,
                    kind=d.workout.kind if d.workout else "",
                    title=d.workout.title if d.workout else "",
                    km=d.workout.km if d.workout else 0,
                    steps=d.workout.steps if d.workout else [],
                    extra=d.workout.extra.to_dict() if d.workout and d.workout.extra else None,
                )
                for d in wk.days
                if d.role != "off"
            ],
        )
        for wk in result.weeks
    ]


def weeks_from_plan(plan: Plan) -> list[WeekView]:
    """Uses the prefetched weeks and days (selectors.active_plan)."""
    return [
        WeekView(
            number=wk.index + 1,
            phase_name=wk.phase_name,
            km=float(wk.km),
            days=[
                DayView(d.date, d.day_name, d.role, d.kind, d.title, float(d.km), d.steps, d.extra)
                for d in wk.days.all()
            ],
        )
        for wk in plan.weeks.all()
    ]
