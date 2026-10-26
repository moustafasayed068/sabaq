from datetime import date, timedelta

import pytest
from django.db import connection
from django.test import Client
from django.utils import timezone

from apps.plans import daylogs
from apps.plans.models import DayLog, Plan, PlanDay
from apps.plans.tests.test_check_in import WEEK1_START, make_plan, on

pytestmark = pytest.mark.django_db


@pytest.fixture
def plan(client, monkeypatch) -> Plan:
    return make_plan(client, monkeypatch)


def first_workout(p: Plan) -> PlanDay:
    day = PlanDay.objects.filter(plan=p, week__index=0).exclude(kind__in=["", "rest"]).first()
    assert day is not None
    return day


def mark(client: Client, day: date, status: str):
    return client.post(f"/plan/day/{day.isoformat()}/log/", {"status": status})


def test_mark_a_day_done_then_change_it(client, plan, monkeypatch):
    day = first_workout(plan)
    on(monkeypatch, day.date)
    assert "خلّصته" in client.get(f"/plan/day/{day.date.isoformat()}/").content.decode()
    assert mark(client, day.date, "done")["Location"] == f"/plan/day/{day.date.isoformat()}/"
    assert DayLog.objects.get(day=day).status == "done"
    assert (
        'aria-pressed="true">خلّصته'
        in client.get(f"/plan/day/{day.date.isoformat()}/").content.decode()
    )
    mark(client, day.date, "missed")
    log = DayLog.objects.get(day=day)
    assert (log.status, log.flagged) == ("missed", False)
    assert "مفيش مشكلة" in client.get(f"/plan/day/{day.date.isoformat()}/").content.decode()
    assert "فوّته" in client.get("/plan/").content.decode()


def test_future_days_and_unknown_statuses_are_refused(client, plan, monkeypatch):
    day = first_workout(plan)
    on(monkeypatch, day.date - timedelta(days=1))
    html = client.get(f"/plan/day/{day.date.isoformat()}/").content.decode()
    assert "plans:log_day" not in html
    assert "/log/" not in html
    mark(client, day.date, "done")
    on(monkeypatch, day.date)
    mark(client, day.date, "hacked")
    assert not DayLog.objects.exists()


def test_locked_week_days_cannot_be_marked(client, plan, monkeypatch):
    day = PlanDay.objects.filter(plan=plan, week__index=1).exclude(kind__in=["", "rest"]).first()
    assert day is not None
    on(monkeypatch, day.date)
    mark(client, day.date, "done")
    assert not DayLog.objects.exists()


def test_feel_something_shows_safety_steps_and_opens_check_in(client, plan, monkeypatch):
    day = first_workout(plan)
    on(monkeypatch, day.date)
    assert day.date < WEEK1_START + timedelta(days=4)  # before the usual day-5 opening
    mark(client, day.date, "feel")
    log = DayLog.objects.get(day=day)
    assert log.flagged
    html = client.get(f"/plan/day/{day.date.isoformat()}/").content.decode()
    assert "وقّف الجري" in html
    assert "الإسعاف" in html
    assert "سجّل أسبوعك دلوقتي" in html
    assert client.get("/plan/check-in/").status_code == 200
    with connection.cursor() as cursor:
        cursor.execute("SELECT data FROM plans_daylog")
        assert "feel" not in str(cursor.fetchone()[0])


def test_check_in_counts_days_marked_done(client, plan, monkeypatch):
    days = PlanDay.objects.filter(plan=plan, week__index=0).exclude(kind__in=["", "rest"])
    on(monkeypatch, WEEK1_START + timedelta(days=6))
    for d in days[:2]:
        mark(client, d.date, "done")
    html = client.get("/plan/check-in/").content.decode()
    assert 'name="done" value="2" id="id_done_2" checked' in html


def test_service_refuses_other_athletes(plan, django_user_model):
    other = django_user_model.objects.create_user("+201003333344")
    with pytest.raises(PermissionError):
        daylogs.log_day(other, plan, first_workout(plan).date, "done", date(2027, 1, 1))


def test_paused_plans_cannot_be_marked(client, plan, monkeypatch):
    day = first_workout(plan)
    on(monkeypatch, day.date)
    Plan.objects.filter(pk=plan.pk).update(paused_at=timezone.now())
    mark(client, day.date, "done")
    assert not DayLog.objects.exists()
