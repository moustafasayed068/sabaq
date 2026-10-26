"""Ownership tests for every endpoint (docs/security.md): athlete B can never read or change
athlete A's answers, health data or plan. New URLs must be classified here or this fails."""

from __future__ import annotations

from datetime import date

import pytest
from django.test import Client
from django.urls import URLPattern, URLResolver, get_resolver
from django.utils import timezone

from apps.accounts.models import User
from apps.athletes.models import HealthScreen, Questionnaire
from apps.athletes.tests.test_questionnaire import ANSWERS, TODAY, answer_all
from apps.plans.models import Plan, PlanDay

pytestmark = pytest.mark.django_db

# route name -> how it is protected
PUBLIC = {"healthz", "landing", "login", "verify", "logout", "start"}
SIGNED = {"callback"}  # Paymob server-to-server: authenticated by HMAC (apps/payments/tests)
STAFF = {"styleguide"}
SESSION_OR_OWNER = {"step", "review", "result"}  # anonymous answers: this session or their owner
OWNER = {
    "mine",
    "save",
    "day",
    "log_day",
    "check_in",
    "resume",
    "checkout",
    "done",
}  # signed-in athlete's own data only


def _route_names() -> set[str]:
    names: set[str] = set()

    def walk(patterns: list[URLPattern | URLResolver], prefix: str = "") -> None:
        for p in patterns:
            if isinstance(p, URLResolver):
                if str(p.pattern).startswith("staff-") or "admin" in str(p.pattern):
                    continue
                walk(p.url_patterns, prefix + str(p.pattern))
            elif p.name and not prefix.startswith("__debug__"):
                names.add(p.name)

    walk(get_resolver().url_patterns)
    return names


def test_every_endpoint_is_classified():
    classified = PUBLIC | SIGNED | STAFF | SESSION_OR_OWNER | OWNER
    assert _route_names() == classified, "classify the new URL in sabaq/tests/test_ownership.py"


@pytest.fixture(autouse=True)
def _today(monkeypatch):
    monkeypatch.setattr(timezone, "localdate", lambda: TODAY)


def athlete(phone: str, race: str, health: dict[str, object]) -> tuple[Client, User, Questionnaire]:
    client = Client()
    client.post(f"/start/{race}/")
    q = Questionnaire.objects.latest("created_at")
    race_step: dict[str, object] = {"start_date": "2026-10-27"}
    if race != "hyrox-dubai":
        race_step["distance_km"] = "21.1"
    answer_all(client, {**ANSWERS, "race": race_step, "health": health})
    user = User.objects.create_user(phone)
    q.refresh_from_db()
    q.user = user
    q.save()
    client.force_login(user)
    session = client.session
    session["questionnaire_id"] = str(q.pk)
    session.save()
    assert client.post("/plan/save/")["Location"] == "/plan/"
    Plan.objects.filter(user=user).update(paid_at=timezone.now())  # every day open
    return client, user, Questionnaire.objects.get(pk=q.pk)


@pytest.fixture
def alice():
    health = {**ANSWERS["health"], "injury": "knee"}
    return athlete("+201001111111", "pyramids", health)


@pytest.fixture
def bob():
    return athlete("+201002222222", "luxor", ANSWERS["health"])


def plant(client: Client, questionnaire: Questionnaire) -> None:
    """Bob puts Alice's questionnaire id in his own session."""
    session = client.session
    session["questionnaire_id"] = str(questionnaire.pk)
    session.save()


def test_b_cannot_read_a_answers_through_the_questionnaire(alice, bob):
    _, _, a_q = alice
    b_client, _, _ = bob
    plant(b_client, a_q)
    for url in ["/questions/race/", "/questions/health/", "/questions/review/", "/plan/result/"]:
        response = b_client.get(url)
        assert response.status_code == 302, url
        assert response["Location"] == "/", url


def test_b_cannot_change_a_answers_or_health(alice, bob):
    _, _, a_q = alice
    b_client, _, _ = bob
    plant(b_client, a_q)
    b_client.post("/questions/you/", {"age": "70", "sex": "f"})
    b_client.post("/questions/health/", {**ANSWERS["health"], "heart": "yes", "injury": "none"})
    a_q.refresh_from_db()
    assert (a_q.age, a_q.sex) == (28, "m")
    data = HealthScreen.objects.get(questionnaire=a_q).data
    assert data["answers"]["heart"] is False
    assert data["injury"] == "knee"


def test_b_cannot_save_a_plan_from_a_answers(alice, bob):
    _, alice_user, a_q = alice
    b_client, bob_user, _ = bob
    plant(b_client, a_q)
    before = Plan.objects.count()
    assert b_client.post("/plan/save/")["Location"] == "/"
    assert Plan.objects.count() == before
    assert not Plan.objects.filter(user=bob_user, questionnaire=a_q).exists()
    assert Plan.objects.get(user=alice_user, is_active=True).questionnaire == a_q


def test_b_sees_only_their_own_plan_and_days(alice, bob):
    a_client, alice_user, _ = alice
    b_client, bob_user, _ = bob
    assert "نص ماراثون الأهرامات" in a_client.get("/plan/").content.decode()
    html = b_client.get("/plan/").content.decode()
    assert "ماراثون الأقصر" in html
    assert "نص ماراثون الأهرامات" not in html
    # On A's race day B sees B's own day, never A's race.
    a_race_day = PlanDay.objects.get(plan__user=alice_user, role="race").date
    b_day = PlanDay.objects.get(plan__user=bob_user, date=a_race_day)
    page = b_client.get(f"/plan/day/{a_race_day.isoformat()}/").content.decode()
    assert b_day.title in page
    assert "نص ماراثون الأهرامات" not in page
    # A date outside B's plan sends B to their own plan.
    assert b_client.get("/plan/day/2026-10-01/")["Location"] == "/plan/"
    # A date both plans share shows B's own workout.
    shared = date(2026, 11, 6)
    a_day = PlanDay.objects.get(plan__user=alice_user, date=shared)
    b_day = PlanDay.objects.get(plan__user=bob_user, date=shared)
    page = b_client.get(f"/plan/day/{shared.isoformat()}/").content.decode()
    if a_day.steps != b_day.steps:
        assert all(step not in page for step in a_day.steps if step not in b_day.steps)


@pytest.mark.parametrize("url", ["/plan/", "/plan/day/2026-11-06/"])
def test_owner_pages_need_login(url):
    response = Client().get(url)
    assert response.status_code == 302
    assert response["Location"].startswith("/login/")


def test_anonymous_save_needs_login():
    assert Client().post("/plan/save/")["Location"].startswith("/login/")


def test_check_in_and_resume_touch_only_my_own_plan(alice, bob, monkeypatch):
    _, alice_user, _ = alice
    b_client, bob_user, _ = bob
    a_plan = Plan.objects.get(user=alice_user, is_active=True)
    a_weeks = list(a_plan.weeks.values_list("pk", flat=True))
    monkeypatch.setattr(timezone, "localdate", lambda: date(2026, 10, 31))
    b_client.post(
        "/plan/check-in/",
        {"done": "0", "long_done": "no", "feel": "hard", "pain": "sharp", "sick": "none"},
    )
    b_client.post("/plan/resume/", {"cleared": "on"})
    a_plan.refresh_from_db()
    assert a_plan.paused_at is None
    assert list(a_plan.weeks.values_list("pk", flat=True)) == a_weeks
    assert not a_plan.check_ins.exists()
    assert Plan.objects.get(user=bob_user, is_active=True).check_ins.count() <= 1
