"""Public API of the plans app: preview a plan, and store it for a signed-in athlete."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any
from uuid import UUID

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from apps.athletes.models import Questionnaire
from apps.athletes.services import plan_input
from apps.plans.models import Plan, PlanDay, PlanStatus, PlanWeek
from apps.plans.selectors import active_plan
from engine import ENGINE_VERSION, generate
from engine.types import Plan as EnginePlan
from engine.types import Week as EngineWeek

if TYPE_CHECKING:
    from apps.accounts.models import User

__all__ = [
    "CannotSavePlanError",
    "active_plan",
    "create_plan",
    "mark_paid",
    "mark_unpaid",
    "preview",
    "week_count",
]


class CannotSavePlanError(Exception):
    """The engine blocked this plan (health, pain, age, date or feasibility)."""


def preview(q: Questionnaire) -> EnginePlan:
    """Run the engine on the answers; nothing is stored."""
    return generate(plan_input(q))


def summary_of(result: EnginePlan) -> dict[str, Any]:
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
    previous = Plan.objects.filter(user=user, is_active=True).first()
    # A paid plan stays paid when the athlete redoes the questions for the same race
    # (docs/product.md: one payment per race).
    paid_at = previous.paid_at if previous and previous.race_id == q.race_id else None
    Plan.objects.filter(user=user, is_active=True).update(is_active=False)
    plan = Plan.objects.create(
        paid_at=paid_at,
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
        summary=summary_of(result),
    )
    store_weeks(plan, result.weeks, first_start=result.weeks[0].start)
    return plan


def store_weeks(plan: Plan, weeks: list[EngineWeek], *, first_start: date) -> None:
    """Store engine weeks and their days. Week numbers count calendar weeks from the plan's
    first week, so a regenerated or resumed plan keeps its numbering."""
    days: list[PlanDay] = []
    for wk in weeks:
        week = PlanWeek.objects.create(
            plan=plan,
            index=(wk.start - first_start).days // 7,
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


# ---------------------------------------------------------------- payment state
# Only apps.payments calls these, and only after a verified Paymob callback or a refund.


def week_count(plan: Plan) -> int:
    return plan.weeks.count()


def mark_paid(plan_id: UUID | str, when: datetime) -> None:
    Plan.objects.filter(pk=plan_id, paid_at__isnull=True).update(paid_at=when)


def mark_unpaid(user_id: UUID | str, race_id: UUID | str) -> None:
    """After a refund: every plan of this athlete for this race goes back to week 1 only."""
    Plan.objects.filter(user_id=user_id, race_id=race_id).update(paid_at=None)


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
    status: str = ""  # done / missed / feel, from the athlete's day log


@dataclass(frozen=True)
class WeekView:
    number: int
    phase_name: str
    km: float
    days: list[DayView]
    locked: bool = False
    start: date | None = None


FREE_WEEKS = 1  # week 1 is free; the rest opens after payment (docs/product.md)


def week_is_open(plan: Plan, index: int) -> bool:
    return index < FREE_WEEKS or plan.paid_at is not None


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


def _day_view(d: PlanDay) -> DayView:
    try:
        status = d.log.status
    except ObjectDoesNotExist:
        status = ""
    return DayView(
        d.date, d.day_name, d.role, d.kind, d.title, float(d.km), d.steps, d.extra, status
    )


def weeks_from_plan(plan: Plan) -> list[WeekView]:
    """Uses the prefetched weeks and days (selectors.active_plan). Locked weeks carry no days,
    so their workouts never reach the page."""
    views = []
    for wk in plan.weeks.all():
        is_open = week_is_open(plan, wk.index)
        views.append(
            WeekView(
                number=wk.index + 1,
                phase_name=wk.phase_name,
                km=float(wk.km),
                days=[_day_view(d) for d in wk.days.all()] if is_open else [],
                locked=not is_open,
                start=wk.start,
            )
        )
    return views


def today_view(weeks: list[WeekView], today: date) -> DayView | None:
    """Today's workout, or on a rest day the next open workout."""
    for week in weeks:
        for day in week.days:
            if day.date >= today and day.kind:
                return day
    return None


@dataclass(frozen=True)
class DayPage:
    day: DayView
    week_number: int
    previous: date | None
    next: date | None


def day_page(plan: Plan, day: date) -> DayPage | None:
    """The day with its neighbours, or None when it is not in the plan or its week is locked."""
    weeks = weeks_from_plan(plan)
    days = [(w.number, d) for w in weeks for d in w.days]
    for i, (number, d) in enumerate(days):
        if d.date == day:
            prev_day = days[i - 1][1].date if i else None
            next_day = days[i + 1][1].date if i + 1 < len(days) else None
            return DayPage(d, number, prev_day, next_day)
    return None
