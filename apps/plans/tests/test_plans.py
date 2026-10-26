from datetime import date
from decimal import Decimal

import pytest
from django.db import connection
from django.test import Client
from django.utils import timezone

from apps.accounts.models import User
from apps.athletes.models import Questionnaire
from apps.athletes.services import plan_input
from apps.athletes.tests.test_questionnaire import ANSWERS, TODAY, answer_all, start
from apps.plans.models import Plan, PlanDay, PlanWeek
from apps.plans.services import CannotSavePlanError, create_plan
from engine import ENGINE_VERSION, generate

pytestmark = pytest.mark.django_db
PHONE = "+201001234567"


@pytest.fixture(autouse=True)
def _today(monkeypatch):
    monkeypatch.setattr(timezone, "localdate", lambda: TODAY)


def finished(client: Client, **overrides) -> Questionnaire:
    q = start(client)
    answer_all(client, {**ANSWERS, **overrides})
    return Questionnaire.objects.get(pk=q.pk)


def sign_in(client: Client, q: Questionnaire, phone: str = PHONE) -> User:
    user = User.objects.filter(phone=phone).first() or User.objects.create_user(phone)
    q.user = user
    q.save()
    client.force_login(user)
    session = client.session
    session["questionnaire_id"] = str(q.pk)
    session.save()
    return user


def test_result_page_previews_without_storing(client):
    finished(client)
    html = client.get("/plan/result/").content.decode()
    assert "ينفع، بس بحذر" in html  # the golden half-intermediate case is risky
    assert "أول أسبوع (ببلاش)" in html
    assert 'الأسبوع <span class="num">1</span>' in html
    assert "جري سهل + تسارعات" in html  # week 1 shows real workouts, not only rest
    assert "الأحد 25 أكتوبر" not in html  # days before the start date are not shown
    assert "سجّل واحفظ خطتك" in html
    assert 'href="/login/?next=/plan/result/"' in html
    assert not Plan.objects.exists()


def test_blocked_by_health_offers_the_doctor_path_and_no_save(client):
    finished(client, health={**ANSWERS["health"], "chestActive": "yes"})
    html = client.get("/plan/result/").content.decode()
    assert "اكشف الأول" in html
    assert "الدكتور وافق؟" in html
    assert "احفظ خطتك" not in html


def test_blocked_for_feasibility_shows_alternatives(client):
    finished(
        client,
        race={"distance_km": "21.1", "start_date": "2026-11-20"},
        running={"runs_per_week": "1", "weekly_km": "5", "longest_km": "3"},
    )
    html = client.get("/plan/result/").content.decode()
    assert "مش هنعمل الخطة دي" in html
    assert "البدائل" in html


def test_result_needs_finished_answers(client):
    assert client.get("/plan/result/")["Location"] == "/"
    start(client)
    assert client.get("/plan/result/")["Location"] == "/questions/race/"


def test_save_stores_the_engine_output_as_rows(client):
    q = finished(client)
    user = sign_in(client, q)
    response = client.post("/plan/save/")
    assert response["Location"] == "/plan/"
    plan = Plan.objects.get(user=user)
    expected = generate(plan_input(q))
    assert plan.engine_version == ENGINE_VERSION
    assert plan.status == expected.status
    assert plan.race_date == date(2026, 12, 12)
    assert PlanWeek.objects.filter(plan=plan).count() == len(expected.weeks)
    stored = list(PlanDay.objects.filter(plan=plan).order_by("date"))
    engine_days = [d for w in expected.weeks for d in w.days if d.role != "off"]
    assert [(d.date, d.role) for d in stored] == [(d.date, d.role) for d in engine_days]
    for row, d in zip(stored, engine_days, strict=True):
        if d.workout:
            assert (row.title, row.km, row.steps) == (
                d.workout.title,
                Decimal(str(d.workout.km)),
                d.workout.steps,
            )
    assert plan.engine_input == plan_input(q).to_dict()


def test_engine_input_is_encrypted_at_rest(client):
    q = finished(client)
    sign_in(client, q)
    client.post("/plan/save/")
    plan = Plan.objects.get()
    with connection.cursor() as cursor:
        cursor.execute("SELECT engine_input FROM plans_plan")
        raw = cursor.fetchone()[0]
    assert raw.startswith("gAAAAA")
    assert "health" not in raw
    assert plan.engine_input["health"] == {}


def test_saving_again_keeps_one_active_plan(client):
    q = finished(client)
    user = sign_in(client, q)
    client.post("/plan/save/")
    client.post("/plan/save/")
    assert Plan.objects.filter(user=user).count() == 2
    assert Plan.objects.filter(user=user, is_active=True).count() == 1


def test_save_needs_login_post_and_a_saveable_plan(client):
    q = finished(client)
    assert client.post("/plan/save/")["Location"].startswith("/login/")
    sign_in(client, q)
    assert client.get("/plan/save/").status_code == 405
    client.post("/questions/health/", {**ANSWERS["health"], "pain": "now"})
    assert client.post("/plan/save/")["Location"] == "/plan/result/"
    assert not Plan.objects.exists()
    with pytest.raises(CannotSavePlanError):
        create_plan(q.user, q)  # type: ignore[arg-type]


def test_athlete_b_cannot_save_or_see_athlete_a_plan(client):
    q = finished(client)
    alice = sign_in(client, q)
    client.post("/plan/save/")
    bob = User.objects.create_user("+201001234568")
    other = Client()
    other.force_login(bob)
    session = other.session
    session["questionnaire_id"] = str(q.pk)
    session.save()
    assert other.post("/plan/save/")["Location"] == "/"
    assert other.get("/plan/")["Location"] == "/"
    with pytest.raises(PermissionError):
        create_plan(bob, q)
    assert Plan.objects.get().user == alice


def test_my_plan_page(client, django_assert_max_num_queries):
    q = finished(client)
    sign_in(client, q)
    client.post("/plan/save/")
    with django_assert_max_num_queries(8):  # session, user, plan, race, weeks, days: no N+1
        response = client.get("/plan/")
    html = response.content.decode()
    assert response.status_code == 200
    assert "نص ماراثون الأهرامات" in html
    assert 'باقي <span class="num">46</span> يوم' in html
    assert "الأسبوع" in html
    assert str(Plan.objects.get()).startswith("Plan ")


def test_my_plan_without_a_plan_goes_home(client):
    client.force_login(User.objects.create_user(PHONE))
    assert client.get("/plan/")["Location"] == "/"
