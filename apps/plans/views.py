"""Result page (anonymous preview), saving the plan, and the athlete's plan page."""

from datetime import date

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.athletes import services as athletes
from apps.plans import services
from apps.plans.selectors import active_plan

QUESTIONNAIRE = "questionnaire_id"


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
    return render(
        request,
        "plans/mine.html",
        {
            "plan": plan,
            "weeks": weeks,
            "today": today,
            "today_day": services.today_view(weeks, today),
        },
    )


@require_GET
@login_required
def day(request: HttpRequest, day: date) -> HttpResponse:
    plan = active_plan(request.user)  # type: ignore[arg-type]
    if plan is None:
        return redirect("races:landing")
    page = services.day_page(plan, day)
    if page is None:
        return redirect("plans:mine")
    return render(
        request, "plans/day.html", {"plan": plan, "page": page, "today": timezone.localdate()}
    )
