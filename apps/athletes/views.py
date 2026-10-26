"""Questionnaire views: parse input, call services, render. No business rules here."""

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from apps.athletes import services
from apps.athletes.models import Questionnaire
from apps.races.services import race_by_slug

SESSION_KEY = "questionnaire_id"


def _session_key(request: HttpRequest) -> str:
    if not request.session.session_key:
        request.session.save()
    return str(request.session.session_key)


def _current(request: HttpRequest) -> Questionnaire | None:
    return services.questionnaire_for(
        request.session.get(SESSION_KEY),
        session_key=request.session.session_key,
        user=request.user if request.user.is_authenticated else None,
    )


@require_POST
def start(request: HttpRequest, slug: str) -> HttpResponse:
    race = race_by_slug(slug)
    if race is None or race.date <= timezone.localdate():
        raise Http404
    q = services.start_questionnaire(_session_key(request), race)
    request.session[SESSION_KEY] = str(q.pk)
    return redirect("athletes:step", step=services.STEPS[0].slug)


@require_http_methods(["GET", "POST"])
def step(request: HttpRequest, step: str) -> HttpResponse:
    if step not in services.STEP_BY_SLUG:
        raise Http404
    q = _current(request)
    if q is None:
        return redirect("races:landing")
    today = timezone.localdate()
    form = services.build_form(step, q, today, request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        services.save_step(q, step, form.cleaned_data)
        nxt = services.next_step(q)
        return redirect("athletes:step", step=nxt) if nxt else redirect("athletes:review")
    index = [s.slug for s in services.STEPS].index(step)
    return render(
        request,
        "athletes/step.html",
        {
            "q": q,
            "form": form,
            "step": services.STEP_BY_SLUG[step],
            "number": index + 1,
            "total": len(services.STEPS),
            "previous": services.STEPS[index - 1].slug if index else None,
        },
        status=422 if request.method == "POST" else 200,
    )


@require_http_methods(["GET"])
def review(request: HttpRequest) -> HttpResponse:
    q = _current(request)
    if q is None:
        return redirect("races:landing")
    missing = services.next_step(q)
    if missing:
        return redirect("athletes:step", step=missing)
    return render(request, "athletes/review.html", {"q": q, "steps": services.STEPS})
