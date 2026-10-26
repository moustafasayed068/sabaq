import json

import pytest
from django.core.cache import cache
from django.test import Client
from django.utils import timezone

from apps.accounts import privacy
from apps.accounts.models import LoginCode, User
from apps.athletes.models import Consent, HealthScreen, Questionnaire
from apps.core.models import AuditAction, AuditEvent
from apps.payments.models import Order, OrderStatus
from apps.plans.models import CheckIn, DayLog, Plan, PlanDay, PlanWeek
from apps.plans.tests.test_check_in import make_plan

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _fresh_cache():
    cache.clear()


@pytest.fixture
def athlete(client, monkeypatch):
    plan = make_plan(client, monkeypatch)
    week = PlanWeek.objects.get(plan=plan, index=0)
    CheckIn.objects.create(
        plan=plan, week=week, flagged=True, **{"data": {"feedback": {"pain": "mild"}}}
    )
    day = PlanDay.objects.filter(plan=plan).exclude(kind="").first()
    assert day is not None
    DayLog.objects.create(plan=plan, day=day, **{"data": {"status": "done"}})
    Order.objects.create(
        user=plan.user,
        plan=plan,
        product="long",
        amount_cents=79900,
        currency="EGP",
        status=OrderStatus.PAID,
        paid_at=timezone.now(),
    )
    return client, plan.user, plan


def test_account_page_needs_login():
    assert Client().get("/account/")["Location"].startswith("/login/")
    assert Client().post("/account/export/")["Location"].startswith("/login/")
    assert Client().post("/account/delete/")["Location"].startswith("/login/")


def test_export_has_everything_about_me(athlete):
    client, user, _ = athlete
    assert "نزّل بياناتي" in client.get("/account/").content.decode()
    response = client.post("/account/export/")
    assert response["Content-Disposition"] == 'attachment; filename="sabaq-my-data.json"'
    assert response["Cache-Control"] == "no-store"
    data = json.loads(response.content)
    assert data["account"]["phone"] == user.phone
    q = data["questionnaires"][0]
    assert q["race"] == "نص ماراثون الأهرامات"
    assert q["health"]["answers"]["heart"] is False
    assert q["consents"]
    p = data["plans"][0]
    assert p["weeks"][0]["days"]
    assert p["check_ins"][0]["data"]["feedback"]["pain"] == "mild"
    assert p["day_marks"][0]["data"]["status"] == "done"
    assert "engine_input" in p
    assert data["orders"][0]["amount_cents"] == 79900
    assert "intention_id" not in data["orders"][0]
    assert AuditEvent.objects.filter(action=AuditAction.DATA_EXPORTED, actor=user).exists()


def test_export_is_rate_limited(athlete):
    client, _, _ = athlete
    for _ in range(privacy.EXPORTS_PER_HOUR):
        assert client.post("/account/export/").status_code == 200
    response = client.post("/account/export/")
    assert response.status_code == 429
    assert "جرّب تاني بعد ساعة" in response.content.decode()


def test_export_shows_only_my_data(athlete, monkeypatch):
    _, alice, _ = athlete
    bob_client = Client()
    make_plan(bob_client, monkeypatch, phone="+201002223344")
    data = json.loads(bob_client.post("/account/export/").content)
    assert data["account"]["phone"] == "+201002223344"
    assert len(data["plans"]) == 1
    assert data["orders"] == []
    assert alice.phone not in json.dumps(data)


def test_delete_needs_the_box_ticked(athlete):
    client, user, _ = athlete
    response = client.post("/account/delete/", {})
    assert response.status_code == 422
    assert "علّم إنك فاهم الأول" in response.content.decode()
    assert User.objects.filter(pk=user.pk).exists()


def test_delete_removes_personal_and_health_data_and_keeps_orders(athlete):
    client, user, _ = athlete
    LoginCode.objects.create(phone=user.phone, code_hash="x", expires_at=timezone.now())
    user_id = str(user.pk)
    response = client.post("/account/delete/", {"confirm": "on"})
    assert response.status_code == 200
    assert "حسابك اتمسح" in response.content.decode()
    assert not User.objects.filter(pk=user_id).exists()
    for model in (Questionnaire, HealthScreen, Consent, Plan, PlanWeek, PlanDay, CheckIn, DayLog):
        assert not model.objects.exists(), model.__name__
    assert not LoginCode.objects.filter(phone=user.phone).exists()
    order = Order.objects.get()
    assert (order.user_id, order.plan_id, order.amount_cents) == (None, None, 79900)
    event = AuditEvent.objects.get(action=AuditAction.ACCOUNT_DELETED)
    assert event.target_id == user_id
    assert event.metadata == {"orders_kept": 1}
    assert user.phone not in json.dumps(event.metadata)
    # Signed out.
    assert client.get("/plan/")["Location"].startswith("/login/")


def test_staff_cannot_delete_themselves_from_the_site():
    staff = User.objects.create_user("+201002229999", "pw", is_staff=True)
    c = Client()
    c.force_login(staff)
    assert "امسح حسابي" not in c.get("/account/").content.decode()
    assert c.post("/account/delete/", {"confirm": "on"}).status_code == 422
    assert User.objects.filter(pk=staff.pk).exists()
    with pytest.raises(PermissionError):
        privacy.delete_account(staff)
