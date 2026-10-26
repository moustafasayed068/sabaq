"""Marking a day: done, missed, or "حاسس بحاجة" (I feel something)."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

from apps.plans.models import DayLog, DayStatus, Plan, PlanDay, PlanWeek
from apps.plans.services import week_is_open

if TYPE_CHECKING:
    from apps.accounts.models import User


class CannotLogDayError(Exception):
    pass


def status_of(day: PlanDay) -> str:
    """Uses the log select_related by selectors.active_plan when it is there."""
    try:
        return day.log.status
    except ObjectDoesNotExist:
        return ""


def can_log(plan: Plan, day: PlanDay, today: date) -> bool:
    return (
        plan.paused_at is None
        and bool(day.kind)
        and day.kind != "rest"
        and day.date <= today
        and week_is_open(plan, day.week.index)
    )


@transaction.atomic
def log_day(user: User, plan: Plan, day_date: date, status: str, today: date) -> DayStatus:
    if plan.user_id != user.pk or not plan.is_active:
        raise PermissionError("not this athlete's plan")
    if status not in DayStatus.values:
        raise CannotLogDayError("unknown status")
    day = PlanDay.objects.select_related("week").filter(plan=plan, date=day_date).first()
    if day is None or not can_log(plan, day, today):
        raise CannotLogDayError("this day cannot be marked")
    value = DayStatus(status)
    DayLog.objects.update_or_create(
        day=day,
        defaults={
            "plan": plan,
            "data": {"status": value.value},
            "flagged": value == DayStatus.FEEL,
        },
    )
    return value


def done_in_week(week: PlanWeek) -> int:
    return sum(1 for d in week.days.all() if status_of(d) == DayStatus.DONE)


def feels_something(week: PlanWeek) -> bool:
    return any(status_of(d) == DayStatus.FEEL for d in week.days.all())
