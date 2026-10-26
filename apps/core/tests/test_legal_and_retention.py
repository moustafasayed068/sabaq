from datetime import datetime, time, timedelta

import pytest
from django.core.cache import cache
from django.test import Client
from django.utils import timezone

from apps.accounts.models import User
from apps.athletes.models import HealthScreen, Questionnaire
from apps.core.models import FeatureFlag
from apps.plans.models import CheckIn, DayLog, Plan, PlanDay, PlanWeek
from apps.plans.retention import apply_retention
from apps.plans.tests.test_check_in import make_plan
from apps.races.models import Race

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _fresh_flags():
    cache.clear()  # feature flags are cached


@pytest.mark.parametrize("url", ["/privacy/", "/terms/"])
def test_legal_pages_hidden_until_approved(url):
    assert Client().get(url).status_code == 404
    assert "/privacy/" not in Client().get("/").content.decode()
    staff = User.objects.create_user("+201007770000", "pw", is_staff=True)
    c = Client()
    c.force_login(staff)
    html = c.get(url).content.decode()
    assert "مسودة" in html
    FeatureFlag.objects.create(name="legal_pages", enabled=True)
    html = Client().get(url).content.decode()
    assert "مسودة" not in html
    assert 'href="/privacy/"' in Client().get("/").content.decode()


def _with_health(client, monkeypatch) -> Plan:
    plan = make_plan(client, monkeypatch)
    week = PlanWeek.objects.get(plan=plan, index=0)
    CheckIn.objects.create(plan=plan, week=week, flagged=True, **{"data": {"x": 1}})
    day = PlanDay.objects.filter(plan=plan).exclude(kind="").first()
    assert day is not None
    DayLog.objects.create(plan=plan, day=day, **{"data": {"status": "feel"}})
    return plan


def test_health_data_kept_for_a_year_after_the_last_plan(client, monkeypatch):
    plan = _with_health(client, monkeypatch)
    race_day = plan.race_date
    kept = apply_retention(race_day + timedelta(days=365))
    assert kept.athletes == 0
    assert HealthScreen.objects.exists()
    result = apply_retention(race_day + timedelta(days=366))
    assert (result.athletes, result.health_screens, result.check_ins, result.day_logs) == (
        1,
        1,
        1,
        1,
    )
    assert result.plan_inputs == 1
    plan.refresh_from_db()
    assert plan.engine_input == {}
    assert plan.summary  # the plan itself stays
    assert not CheckIn.objects.exists()
    assert not DayLog.objects.exists()
    # Idempotent.
    again = apply_retention(race_day + timedelta(days=400))
    assert (again.health_screens, again.plan_inputs) == (0, 0)


def test_new_answers_keep_an_old_athlete_s_health_data(client, monkeypatch):
    plan = _with_health(client, monkeypatch)
    later = plan.race_date + timedelta(days=500)
    Questionnaire.objects.filter(user=plan.user).update(created_at=timezone.now())
    q = Questionnaire.objects.create(
        session_key="s", race=Race.objects.get(slug="luxor"), user=plan.user
    )
    Questionnaire.objects.filter(pk=q.pk).update(
        created_at=timezone.make_aware(datetime.combine(later, time.min))
    )
    assert apply_retention(later + timedelta(days=10)).athletes == 0


def test_anonymous_answers_go_after_the_session_ends():
    race = Race.objects.get(slug="pyramids")
    old = Questionnaire.objects.create(session_key="a", race=race)
    new = Questionnaire.objects.create(session_key="b", race=race)
    Questionnaire.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=31))
    result = apply_retention(timezone.localdate())
    assert result.anonymous_questionnaires == 1
    assert not Questionnaire.objects.filter(pk=old.pk).exists()
    assert Questionnaire.objects.filter(pk=new.pk).exists()
