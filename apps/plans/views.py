"""Result page (anonymous preview), saving the plan, and the athlete's plan page."""

import contextlib
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.athletes import services as athletes
from apps.plans import checkins, daylogs, services
from apps.plans.forms import CheckInForm, ResumeForm
from apps.plans.models import DayStatus
from apps.plans.selectors import active_plan

QUESTIONNAIRE = "questionnaire_id"
RECENT_CHECK_IN = timedelta(days=2)


def _questionnaire(request: HttpRequest) -> athletes.Questionnaire | None:
    return athletes.questionnaire_for(
        request.session.get(QUESTIONNAIRE),
        session_key=request.session.session_key,
        user=request.user if request.user.is_authenticated else None,
    )


@require_GET
def result(request: HttpRequest) -> HttpResponse:
    q = _questionnaire(request)
    if q is None:
        return redirect("races:landing")
    missing = athletes.next_step(q)
    if missing:
        return redirect("athletes:step", step=missing)
    plan = services.preview(q)
    first_week = services.weeks_from_engine(plan)[:1]
    return render(request, "plans/result.html", {"q": q, "plan": plan, "first_week": first_week})


@require_POST
@login_required
def save(request: HttpRequest) -> HttpResponse:
    q = _questionnaire(request)
    if q is None or q.user_id != request.user.pk or athletes.next_step(q):
        return redirect("races:landing")
    try:
        services.create_plan(request.user, q)  # type: ignore[arg-type]
    except services.CannotSavePlanError:
        return redirect("plans:result")
    return redirect("plans:mine")


@require_GET
@login_required
def mine(request: HttpRequest) -> HttpResponse:
    plan = active_plan(request.user)  # type: ignore[arg-type]
    if plan is None:
        return redirect("races:landing")
    today = timezone.localdate()
    weeks = services.weeks_from_plan(plan)
    latest = checkins.latest_check_in(plan)
    recent = latest is not None and latest.created_at >= timezone.now() - RECENT_CHECK_IN
    return render(
        request,
        "plans/mine.html",
        {
            "plan": plan,
            "weeks": weeks,
            "today": today,
            "today_day": None if plan.paused_at else services.today_view(weeks, today),
            "check_in_week": checkins.check_in_week(plan, today),
            "check_in_messages": latest.data["messages"] if latest and recent else [],
            "resume_form": ResumeForm() if plan.paused_at else None,
        },
    )


@require_http_methods(["GET", "POST"])
@login_required
def check_in(request: HttpRequest) -> HttpResponse:
    plan = active_plan(request.user)  # type: ignore[arg-type]
    if plan is None:
        return redirect("races:landing")
    today = timezone.localdate()
    week = checkins.check_in_week(plan, today)
    if week is None:
        return redirect("plans:mine")
    planned, has_long = checkins.planned_sessions(week), checkins.has_long_run(week)
    if request.method == "POST":
        form = CheckInForm(request.POST, planned=planned, has_long=has_long)
        if form.is_valid():
            # A double submit loses the race for the week; the first one already counted.
            with contextlib.suppress(checkins.CannotCheckInError):
                checkins.submit_check_in(request.user, plan, week, form.feedback(), today)  # type: ignore[arg-type]
            return redirect("plans:mine")
        status = 422
    else:
        form = CheckInForm(
            planned=planned,
            has_long=has_long,
            initial={"done": str(min(daylogs.done_in_week(week), planned))},
        )
        status = 200
    return render(
        request,
        "plans/check_in.html",
        {"plan": plan, "week": week, "form": form},
        status=status,
    )


@require_POST
@login_required
def resume(request: HttpRequest) -> HttpResponse:
    plan = active_plan(request.user)  # type: ignore[arg-type]
    if plan is None or plan.paused_at is None:
        return redirect("plans:mine")
    form = ResumeForm(request.POST)
    error: list[str] = []
    if form.is_valid():
        try:
            checkins.resume(request.user, plan, timezone.localdate())  # type: ignore[arg-type]
        except checkins.CannotCheckInError as exc:
            error = exc.messages
        else:
            return redirect("plans:mine")
    latest = checkins.latest_check_in(plan)
    return render(
        request,
        "plans/mine.html",
        {
            "plan": plan,
            "weeks": services.weeks_from_plan(plan),
            "today": timezone.localdate(),
            "check_in_messages": latest.data["messages"] if latest else [],
            "resume_form": form,
            "resume_error": error,
        },
        status=422,
    )


@require_GET
@login_required
def day(request: HttpRequest, day: date) -> HttpResponse:
    plan = active_plan(request.user)  # type: ignore[arg-type]
    if plan is None:
        return redirect("races:landing")
    page = None if plan.paused_at else services.day_page(plan, day)
    if page is None:
        return redirect("plans:mine")
    today = timezone.localdate()
    loggable = page.day.kind not in ("", "rest") and page.day.date <= today
    return render(
        request,
        "plans/day.html",
        {
            "plan": plan,
            "page": page,
            "today": today,
            "loggable": loggable,
            "statuses": DayStatus.choices,
            "check_in_open": checkins.check_in_week(plan, today) is not None,
        },
    )


@require_POST
@login_required
def log_day(request: HttpRequest, day: date) -> HttpResponse:
    plan = active_plan(request.user)  # type: ignore[arg-type]
    if plan is None:
        return redirect("races:landing")
    with contextlib.suppress(daylogs.CannotLogDayError):
        daylogs.log_day(
            request.user,  # type: ignore[arg-type]
            plan,
            day,
            request.POST.get("status", ""),
            timezone.localdate(),
        )
    return redirect("plans:day", day=day)
