from datetime import date, timedelta

import pytest
from django.db import connection
from django.test import Client
from django.utils import timezone

from apps.core.models import AuditAction, AuditEvent
from apps.plans import checkins
from apps.plans.models import CheckIn, Plan, PlanDay, PlanWeek
from apps.plans.tests.test_plans import PHONE, finished, sign_in
from engine.types import CheckInFeedback

pytestmark = pytest.mark.django_db

# The pyramids half plan used across these tests: week 1 runs Sun 25 Oct - Sat 31 Oct.
WEEK1_START = date(2026, 10, 25)
DAY5 = WEEK1_START + timedelta(days=4)

GOOD_WEEK = {"long_done": "yes", "feel": "easy", "pain": "none", "sick": "none"}


def on(monkeypatch, day: date) -> None:
    monkeypatch.setattr(timezone, "localdate", lambda: day)


@pytest.fixture
def plan(client, monkeypatch) -> Plan:
    return make_plan(client, monkeypatch)


def make_plan(client, monkeypatch, phone: str = PHONE) -> Plan:
    on(monkeypatch, date(2026, 10, 27))
    q = finished(client)
    user = sign_in(client, q, phone)
    client.post("/plan/save/")
    p = Plan.objects.get(user=user, is_active=True)
    assert week(p, 0).start == WEEK1_START
    return p


def week(plan: Plan, index: int) -> PlanWeek:
    return PlanWeek.objects.get(plan=plan, index=index)


def planned(plan: Plan, index: int) -> int:
    return checkins.planned_sessions(week(plan, index))


def good(plan: Plan, **changes: str) -> dict[str, str]:
    """A full week done, felt easy, no pain, not sick; `changes` override answers."""
    return {**GOOD_WEEK, "done": str(planned(plan, 0)), **changes}


def test_check_in_opens_on_the_fifth_day(client, plan, monkeypatch):
    assert "سجّل أسبوعك" not in client.get("/plan/").content.decode()
    assert client.get("/plan/check-in/")["Location"] == "/plan/"
    on(monkeypatch, DAY5)
    assert "سجّل أسبوعك" in client.get("/plan/").content.decode()
    html = client.get("/plan/check-in/").content.decode()
    assert f"عملت كام تمرين من {planned(plan, 0)}" in html


def test_good_week_regenerates_the_rest(client, plan, monkeypatch):
    on(monkeypatch, DAY5)
    old_week2 = week(plan, 1).pk
    weeks_before = PlanWeek.objects.filter(plan=plan).count()
    response = client.post("/plan/check-in/", good(plan))
    assert response["Location"] == "/plan/"
    plan.refresh_from_db()
    assert PlanWeek.objects.filter(plan=plan).count() == weeks_before
    assert week(plan, 1).pk != old_week2  # regenerated
    assert week(plan, 1).start == WEEK1_START + timedelta(days=7)
    assert week(plan, 0).days.exists()  # the checked week stays as it was
    assert plan.engine_input["flags"]["continuing"] is True
    ci = CheckIn.objects.get()
    assert not ci.flagged
    assert ci.data["action"] == "continue"
    html = client.get("/plan/").content.decode()
    assert "ظبطنا خطتك" in html
    assert "أسبوع حلو" in html
    # Only once per week.
    assert client.get("/plan/check-in/")["Location"] == "/plan/"
    assert "سجّل أسبوعك" not in html


def test_check_in_answers_are_encrypted_at_rest(client, plan, monkeypatch):
    on(monkeypatch, DAY5)
    client.post("/plan/check-in/", good(plan, pain="mild", sick="head"))
    with connection.cursor() as cursor:
        cursor.execute("SELECT data FROM plans_checkin")
        raw = str(cursor.fetchone()[0])
    assert "mild" not in raw
    assert "head" not in raw
    ci = CheckIn.objects.get()
    assert ci.flagged
    assert ci.data["feedback"]["pain"] == "mild"


def test_sharp_pain_pauses_until_a_doctor_clears(client, plan, monkeypatch):
    on(monkeypatch, DAY5)
    client.post("/plan/check-in/", good(plan, pain="sharp"))
    plan.refresh_from_db()
    assert plan.paused_at is not None
    assert not PlanWeek.objects.filter(plan=plan, index__gt=0).exists()
    assert CheckIn.objects.get().flagged
    assert AuditEvent.objects.filter(action=AuditAction.PLAN_PAUSED).exists()
    html = client.get("/plan/").content.decode()
    assert "الخطة واقفة" in html
    assert "اكشف عند دكتور" in html
    assert "افتح التمرين" not in html  # no workout while paused
    a_day = PlanDay.objects.filter(plan=plan).exclude(kind="").first()
    assert a_day is not None
    assert client.get(f"/plan/day/{a_day.date.isoformat()}/")["Location"] == "/plan/"
    assert client.get("/plan/check-in/")["Location"] == "/plan/"

    # The box must be ticked.
    response = client.post("/plan/resume/", {})
    assert response.status_code == 422
    assert "علّم إن الدكتور وافق الأول" in response.content.decode()

    later = DAY5 + timedelta(days=10)
    on(monkeypatch, later)
    assert client.post("/plan/resume/", {"cleared": "on"})["Location"] == "/plan/"
    plan.refresh_from_db()
    assert plan.paused_at is None
    assert AuditEvent.objects.filter(action=AuditAction.PLAN_RESUMED).exists()
    assert plan.engine_input["doctorCleared"] is True
    first_back = PlanWeek.objects.filter(plan=plan, index__gt=0).order_by("index").first()
    assert first_back is not None
    # Calendar numbering: the week after the gap keeps its real number.
    assert first_back.index == (first_back.start - WEEK1_START).days // 7
    back_days = PlanDay.objects.filter(plan=plan, week=first_back)
    assert back_days.exists()
    assert all(d.date >= later for d in back_days)
    assert not back_days.filter(kind="quality", date__lte=later + timedelta(days=6)).exists()


def test_resume_too_close_to_the_race_explains_why(client, plan, monkeypatch):
    on(monkeypatch, DAY5)
    client.post("/plan/check-in/", good(plan, pain="sharp"))
    on(monkeypatch, date(2026, 12, 11))
    response = client.post("/plan/resume/", {"cleared": "on"})
    assert response.status_code == 422
    assert "السباق قريب" in response.content.decode()
    plan.refresh_from_db()
    assert plan.paused_at is not None


def test_resume_when_not_paused_does_nothing(client, plan):
    assert client.post("/plan/resume/", {"cleared": "on"})["Location"] == "/plan/"


def test_chest_sickness_rests_first(client, plan, monkeypatch):
    on(monkeypatch, DAY5)
    client.post("/plan/check-in/", good(plan, sick="chest", sick_days="3"))
    plan.refresh_from_db()
    assert CheckIn.objects.get().flagged
    roles = list(week(plan, 1).days.order_by("date").values_list("role", flat=True))
    assert roles[0] == "rest-sick"
    assert "متجريش خالص" in client.get("/plan/").content.decode()


def test_new_5k_time_updates_paces(client, plan, monkeypatch):
    on(monkeypatch, DAY5)
    client.post(
        "/plan/check-in/",
        good(plan, new_time_0="0", new_time_1="24", new_time_2="30"),
    )
    plan.refresh_from_db()
    assert plan.engine_input["recentKm"] == 5
    assert plan.engine_input["recentTime"] == "0:24:30"


@pytest.mark.parametrize(
    ("data", "error"),
    [
        ({"done": "99"}, "اختار من الاختيارات"),
        ({"pain": ""}, "اختار واحدة"),
        ({"sick_days": "x"}, "اكتب رقم"),
    ],
)
def test_check_in_validation(client, plan, monkeypatch, data, error):
    on(monkeypatch, DAY5)
    response = client.post("/plan/check-in/", good(plan, **data))
    assert response.status_code == 422
    assert error in response.content.decode()
    assert not CheckIn.objects.exists()


def test_locked_weeks_cannot_be_checked_in(client, plan, monkeypatch):
    on(monkeypatch, DAY5)
    client.post("/plan/check-in/", good(plan))
    on(monkeypatch, WEEK1_START + timedelta(days=7 + 4))
    plan.refresh_from_db()
    assert checkins.check_in_week(plan, timezone.localdate()) is None  # week 2 unpaid
    Plan.objects.filter(pk=plan.pk).update(paid_at=timezone.now())
    plan.refresh_from_db()
    assert checkins.check_in_week(plan, timezone.localdate()) == week(plan, 1)


def test_a_missed_check_in_closes_after_the_next_week(plan):
    assert checkins.check_in_week(plan, WEEK1_START + timedelta(days=13)) == week(plan, 0)
    assert checkins.check_in_week(plan, WEEK1_START + timedelta(days=14)) is None


def test_service_refuses_another_athletes_plan_and_a_closed_week(plan, django_user_model):
    other = django_user_model.objects.create_user("+201003333333")
    with pytest.raises(PermissionError):
        checkins.submit_check_in(other, plan, week(plan, 0), CheckInFeedback(), DAY5)
    with pytest.raises(checkins.CannotCheckInError):
        checkins.submit_check_in(plan.user, plan, week(plan, 0), CheckInFeedback(), WEEK1_START)
    with pytest.raises(PermissionError):
        checkins.resume(other, plan, DAY5)


def test_check_in_pages_need_login():
    assert Client().get("/plan/check-in/")["Location"].startswith("/login/")
    assert Client().post("/plan/resume/")["Location"].startswith("/login/")
