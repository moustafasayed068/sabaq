"""Weekly check-in, the sharp-pain pause and the doctor-cleared resume.

The engine decides everything (engine.check_in, engine.generate, engine.resume_after_clearance);
this module only finds the week, feeds the engine what the athlete saw, and stores the result.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils import timezone

from apps.core.services import AuditAction, record_audit
from apps.plans.daylogs import feels_something
from apps.plans.models import CheckIn, Plan, PlanStatus, PlanWeek
from apps.plans.services import store_weeks, summary_of, week_is_open
from engine import ENGINE_VERSION, check_in, generate, resume_after_clearance
from engine.types import CheckInFeedback, Day, PlanInput, Week, Workout
from engine.types import Plan as EnginePlan

if TYPE_CHECKING:
    from apps.accounts.models import User

# A week's check-in opens on its 5th day and stays open until the end of the next week.
OPENS_ON_DAY = 4
CLOSES_AFTER_DAYS = 13


class CannotCheckInError(Exception):
    """The week is not open for a check-in, or the engine cannot build the rest of the plan."""

    def __init__(self, reason: str, messages: list[str] | None = None) -> None:
        super().__init__(reason)
        self.messages = messages or []


@dataclass(frozen=True)
class CheckInOutcome:
    action: str
    messages: list[str]
    regenerated: bool


def _engine_week(week: PlanWeek) -> Week:
    """The week as the athlete saw it (stored rows), not as today's engine would make it."""
    days = [
        Day(
            date=d.date,
            day_name=d.day_name,
            role=d.role,
            workout=Workout(d.kind, d.title, d.intensity, float(d.km), list(d.steps))
            if d.kind
            else None,
        )
        for d in week.days.all()
    ]
    return Week(
        index=week.index,
        start=week.start,
        phase=week.phase,
        phase_name=week.phase_name,
        target_km=week.target_km,
        km=float(week.km),
        days=days,
    )


def planned_sessions(week: PlanWeek) -> int:
    return sum(1 for d in week.days.all() if d.kind and d.kind != "rest")


def has_long_run(week: PlanWeek) -> bool:
    return any(d.kind == "long" for d in week.days.all())


def check_in_week(plan: Plan, today: date) -> PlanWeek | None:
    """The week the athlete can check in now: open, not the race week, started at least
    OPENS_ON_DAY days ago, not older than last week, and not checked in yet."""
    if plan.paused_at is not None:
        return None
    for week in plan.weeks.all():
        if week.phase == "race" or not week_is_open(plan, week.index):
            continue
        # "حاسس بحاجة" on a day opens the check-in at once, so sharp pain can pause the plan.
        opens = week.start if feels_something(week) else week.start + timedelta(days=OPENS_ON_DAY)
        if not opens <= today <= week.start + timedelta(days=CLOSES_AFTER_DAYS):
            continue
        if CheckIn.objects.filter(week=week).exists():
            continue
        return week
    return None


def _replace_weeks_after(plan: Plan, index: int, result: EnginePlan | None) -> None:
    plan.weeks.filter(index__gt=index).delete()
    if result is None:
        return
    first = plan.weeks.order_by("index").first()
    first_start = first.start if first else result.weeks[0].start
    store_weeks(plan, result.weeks, first_start=first_start)
    plan.status = PlanStatus(result.status)
    plan.messages = result.messages
    plan.warnings = result.warnings
    plan.summary = summary_of(result)
    plan.engine_version = ENGINE_VERSION


@transaction.atomic
def submit_check_in(
    user: User, plan: Plan, week: PlanWeek, fb: CheckInFeedback, today: date
) -> CheckInOutcome:
    plan = Plan.objects.select_for_update().get(pk=plan.pk)
    if plan.user_id != user.pk or not plan.is_active:
        raise PermissionError("not this athlete's plan")
    if week.plan_id != plan.pk or check_in_week(plan, today) != week:
        raise CannotCheckInError("this week cannot be checked in now")
    inp = PlanInput.from_dict(plan.engine_input)
    engine_plan = EnginePlan(input=inp, weeks=[_engine_week(week)])
    res = check_in(inp, engine_plan, 0, fb)
    messages = list(res.messages)
    regenerated = False
    if res.action == "paused":
        plan.paused_at = timezone.now()
        _replace_weeks_after(plan, week.index, None)
        plan.engine_input = res.input.to_dict()  # encrypted JSON
        record_audit(AuditAction.PLAN_PAUSED, actor=user, target=plan)
    else:
        result = generate(res.input)
        if result.status != "blocked" and result.weeks:
            _replace_weeks_after(plan, week.index, result)
            plan.engine_input = res.input.to_dict()
            regenerated = True
        else:
            messages.extend(result.messages)
    plan.save()
    flagged = res.action != "continue" or fb.pain in ("mild", "sharp")
    feedback: dict[str, Any] = {
        "done": fb.done,
        "longDone": fb.long_done,
        "feel": fb.feel,
        "pain": fb.pain,
        "sick": fb.sick,
        "sickDays": fb.sick_days,
        "newTime": fb.new_time,
    }
    CheckIn.objects.create(
        plan=plan,
        week=week,
        data={"feedback": feedback, "action": res.action, "messages": messages},  # type: ignore[misc]
        flagged=flagged,
    )
    return CheckInOutcome(res.action, messages, regenerated)


@transaction.atomic
def resume(user: User, plan: Plan, today: date) -> None:
    """The athlete confirms a doctor cleared them. The plan restarts lighter (engine rule)."""
    plan = Plan.objects.select_for_update().get(pk=plan.pk)
    if plan.user_id != user.pk or not plan.is_active:
        raise PermissionError("not this athlete's plan")
    if plan.paused_at is None:
        return
    paused = PlanInput.from_dict(plan.engine_input)
    last = plan.weeks.order_by("-index").first()
    start = max(today, last.start + timedelta(days=7)) if last else today
    inp = resume_after_clearance(paused, start)
    result = generate(inp)
    if result.status == "blocked" or not result.weeks:
        raise CannotCheckInError(result.block_kind or "no weeks left", result.messages)
    _replace_weeks_after(plan, last.index if last else -1, result)
    plan.engine_input = inp.to_dict()
    plan.paused_at = None
    plan.save()
    record_audit(AuditAction.PLAN_RESUMED, actor=user, target=plan)


def latest_check_in(plan: Plan) -> CheckIn | None:
    return plan.check_ins.order_by("-created_at").first()
