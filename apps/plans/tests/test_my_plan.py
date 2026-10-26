from datetime import date

import pytest
from django.test import Client
from django.utils import timezone

from apps.accounts.models import User
from apps.athletes.tests.test_questionnaire import TODAY
from apps.plans.models import Plan, PlanDay
from apps.plans.tests.test_plans import finished, sign_in

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _today(monkeypatch):
    monkeypatch.setattr(timezone, "localdate", lambda: TODAY)


@pytest.fixture
def plan(client) -> Plan:
    q = finished(client)
    sign_in(client, q)
    client.post("/plan/save/")
    return Plan.objects.get()


def week_day(plan: Plan, index: int) -> PlanDay:
    day = (
        PlanDay.objects.filter(plan=plan, week__index=index)
        .exclude(kind="")
        .order_by("date")
        .first()
    )
    assert day is not None
    return day


def test_week_one_is_open_and_later_weeks_are_locked(client, plan):
    html = client.get("/plan/").content.decode()
    week2_steps = week_day(plan, 1).steps[0]
    assert week_day(plan, 0).steps[0] in html
    assert week2_steps not in html  # locked content never reaches the page
    assert "بيتفتح بعد ما تفتح باقي الخطة" in html
    assert "أول أسبوع ببلاش" in html


def test_paid_plan_opens_every_week(client, plan):
    plan.paid_at = timezone.now()
    plan.save()
    html = client.get("/plan/").content.decode()
    assert week_day(plan, 1).steps[0] in html
    assert "بيتفتح بعد" not in html


def test_today_card_points_to_the_next_workout(client, plan):
    html = client.get("/plan/").content.decode()
    first = week_day(plan, 0)
    assert first.date > TODAY  # TODAY (Tue 27 Oct) is a rest day in this plan
    assert "التمرين الجاي" in html
    assert f'href="/plan/day/{first.date.isoformat()}/"' in html


def test_day_page_shows_the_full_workout_with_neighbours(client, plan):
    first = week_day(plan, 0)
    html = client.get(f"/plan/day/{first.date.isoformat()}/").content.decode()
    assert first.title in html
    for step in first.steps:
        assert step in html
    assert "اليوم اللي بعده" in html


def test_locked_or_unknown_days_redirect_and_bad_dates_404(client, plan):
    locked = week_day(plan, 1)
    assert client.get(f"/plan/day/{locked.date.isoformat()}/")["Location"] == "/plan/"
    assert client.get("/plan/day/2030-01-01/")["Location"] == "/plan/"
    assert client.get("/plan/day/2026-13-45/").status_code == 404


def test_day_page_needs_login_and_only_shows_your_own_plan(client, plan):
    first = week_day(plan, 0)
    anon = Client()
    assert anon.get(f"/plan/day/{first.date.isoformat()}/")["Location"].startswith("/login/")
    bob = Client()
    bob.force_login(User.objects.create_user("+201001234569"))
    assert bob.get(f"/plan/day/{first.date.isoformat()}/")["Location"] == "/"


def test_race_day_page_has_race_day_tips(client, plan):
    plan.paid_at = timezone.now()
    plan.save()
    html = client.get(f"/plan/day/{date(2026, 12, 12).isoformat()}/").content.decode()
    assert "race-day" in html
    assert "متجربش أي حاجة جديدة يوم السباق" in html
