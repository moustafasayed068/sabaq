from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.auth.models import Permission
from django.test import Client
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import AuditAction, AuditEvent
from apps.plans.models import CheckIn, DayLog, Plan, PlanWeek
from apps.plans.tests.test_check_in import make_plan

pytestmark = pytest.mark.django_db

ADMIN = f"/{settings.ADMIN_URL}"


def staff(*perms: str) -> Client:
    user = User.objects.create_user(
        f"+2010000{len(perms)}{User.objects.count():04d}", "pw", is_staff=True
    )
    for codename in perms:
        user.user_permissions.add(Permission.objects.get(codename=codename))
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def plans(client, monkeypatch):
    """Three athletes: calm, flagged (mild pain in a check-in), paused."""
    calm = make_plan(client, monkeypatch)
    out = {"calm": calm}
    for i, name in enumerate(("flagged", "paused")):
        out[name] = make_plan(Client(), monkeypatch, phone=f"+20100777000{i}")
    week = PlanWeek.objects.get(plan=out["flagged"], index=0)
    CheckIn.objects.create(
        plan=out["flagged"], week=week, flagged=True, **{"data": {"feedback": {"pain": "mild"}}}
    )
    Plan.objects.filter(pk=out["paused"].pk).update(paused_at=timezone.now())
    return out


def test_paused_then_flagged_come_first(plans):
    c = staff("view_plan")
    html = c.get(f"{ADMIN}plans/plan/").content.decode()
    paused, flagged, calm = (html.index(str(plans[k].pk)) for k in ("paused", "flagged", "calm"))
    assert paused < flagged < calm
    assert "Paused" in html
    assert "Flagged" in html
    assert "mild" not in html  # no health detail in the list


def test_filter_needs_a_look(plans):
    c = staff("view_plan")
    html = c.get(f"{ADMIN}plans/plan/?look=flagged").content.decode()
    assert str(plans["flagged"].pk) in html
    assert str(plans["calm"].pk) not in html
    html = c.get(f"{ADMIN}plans/plan/?look=paused").content.decode()
    assert str(plans["paused"].pk) in html
    assert str(plans["flagged"].pk) not in html


def test_old_flags_drop_off(plans):
    CheckIn.objects.update(created_at=timezone.now() - timedelta(days=15))
    html = staff("view_plan").get(f"{ADMIN}plans/plan/?look=flagged").content.decode()
    assert str(plans["flagged"].pk) not in html


def test_check_in_answers_need_the_health_role_and_are_audited(plans):
    ci = CheckIn.objects.get()
    url = f"{ADMIN}plans/checkin/{ci.pk}/change/"
    assert staff("view_plan").get(url).status_code in (302, 403)
    c = staff("view_health_answers")
    response = c.get(url)
    assert response.status_code == 200
    assert "mild" in response.content.decode()
    assert AuditEvent.objects.filter(
        action=AuditAction.HEALTH_DATA_VIEWED, target_id=str(ci.pk)
    ).exists()


def test_day_logs_need_the_health_role(plans):
    day = plans["calm"].days.exclude(kind="").first()
    log = DayLog.objects.create(
        plan=plans["calm"], day=day, flagged=True, **{"data": {"status": "feel"}}
    )
    url = f"{ADMIN}plans/daylog/{log.pk}/change/"
    assert staff().get(url).status_code in (302, 403)
    assert staff("view_health_answers").get(url).status_code == 200
    html = staff("view_plan").get(f"{ADMIN}plans/plan/").content.decode()
    # A flagged day log puts the calm athlete with the flagged ones, after the paused one.
    assert html.index(str(plans["paused"].pk)) < html.index(str(plans["calm"].pk))


def test_plans_are_read_only_for_staff(plans):
    c = staff("view_plan", "change_plan", "delete_plan", "add_plan")
    p = plans["calm"]
    assert c.get(f"{ADMIN}plans/plan/add/").status_code == 403
    response = c.post(f"{ADMIN}plans/plan/{p.pk}/change/", {"is_active": ""})
    assert response.status_code == 403
    assert c.get(f"{ADMIN}plans/plan/{p.pk}/change/").status_code == 200
