from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.test import Client
from django.utils import timezone

from apps.accounts.models import User
from apps.athletes.tests.test_questionnaire import TODAY
from apps.core.models import AuditAction, AuditEvent
from apps.payments import paymob, services, views
from apps.payments.models import Order, OrderStatus, Payment, Product
from apps.payments.tests.test_paymob import DOCS_OBJ
from apps.plans.models import Plan
from apps.plans.tests.test_plans import finished, sign_in

pytestmark = pytest.mark.django_db

HMAC_SECRET = "test-hmac-secret"


@pytest.fixture(autouse=True)
def _today(monkeypatch):
    monkeypatch.setattr(timezone, "localdate", lambda: TODAY)


@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    cache.clear()


@pytest.fixture
def keys(settings):
    settings.PAYMOB_SECRET_KEY = "sk_test"
    settings.PAYMOB_PUBLIC_KEY = "pk_test"
    settings.PAYMOB_HMAC_SECRET = HMAC_SECRET
    settings.PAYMOB_INTEGRATION_IDS = [11]
    return settings


class FakeClient:
    """Stands in for Paymob: records intentions and refunds."""

    def __init__(self):
        self.intentions = []
        self.refunds = []
        self.fail = False
        self.next_order_id = 5000

    def create_intention(self, **kwargs):
        if self.fail:
            raise paymob.PaymobError("down")
        self.intentions.append(kwargs)
        self.next_order_id += 1
        return paymob.Intention("pi_x", "cs_x", self.next_order_id)

    def checkout_url(self, client_secret):
        return f"https://accept.paymob.com/unifiedcheckout/?clientSecret={client_secret}"

    def refund(self, *, transaction_id, amount_cents):
        if self.fail:
            raise paymob.PaymobError("down")
        self.refunds.append((transaction_id, amount_cents))
        return {"success": True}


@pytest.fixture
def fake(monkeypatch):
    client = FakeClient()
    monkeypatch.setattr(paymob, "client", lambda: client)
    return client


@pytest.fixture
def plan(client) -> Plan:
    q = finished(client)
    sign_in(client, q)
    client.post("/plan/save/")
    return Plan.objects.get()


def checkout(client, plan) -> Order:
    response = client.post("/pay/start/")
    assert response.status_code == 302
    assert response["Location"].startswith("https://accept.paymob.com/unifiedcheckout/")
    return Order.objects.get(plan=plan)


def tx(o: Order, **changes) -> dict[str, object]:
    obj = {
        **DOCS_OBJ,
        "id": 900001,
        "amount_cents": o.amount_cents,
        "currency": o.currency,
        "order": {"id": o.paymob_order_id, "merchant_order_id": str(o.pk)},
    }
    obj.update(changes)
    return obj


def post_callback(obj: dict[str, object], *, secret: str = HMAC_SECRET, kind: str = "TRANSACTION"):
    signature = paymob.transaction_hmac(obj, secret)
    return Client().post(
        f"/payments/paymob/callback/?hmac={signature}",
        data={"type": kind, "obj": obj},
        content_type="application/json",
    )


# ---------------------------------------------------------------- prices


@pytest.mark.parametrize(
    ("weeks", "product", "cents"),
    [(1, Product.SHORT, 34900), (4, Product.SHORT, 34900), (5, Product.LONG, 79900)],
)
def test_price_comes_from_the_plan_length(weeks, product, cents):
    price = services.price_for_weeks(weeks)
    assert (price.product, price.amount_cents, price.currency) == (product, cents, "EGP")


def test_landing_shows_server_prices(client):
    html = client.get("/").content.decode()
    assert "349" in html
    assert "799" in html


# ---------------------------------------------------------------- checkout


def test_without_keys_checkout_is_closed(client, plan, fake):
    html = client.get("/pay/").content.decode()
    assert "الدفع هيتفتح قريب" in html
    assert client.post("/pay/start/")["Location"] == "/pay/?error=1"
    assert not Order.objects.exists()
    assert not fake.intentions


def test_checkout_page_shows_the_plan_price(client, plan, keys, fake):
    html = client.get("/pay/").content.decode()
    price = services.price_for_plan(plan)
    assert "ادفع" in html
    assert f">{price.amount}<" in html


def test_checkout_creates_an_order_at_the_server_price(client, plan, keys, fake):
    # Whatever the browser sends, the price is the server's.
    response = client.post("/pay/start/", {"amount": "1", "amount_cents": "1"})
    order = Order.objects.get(plan=plan)
    price = services.price_for_plan(plan)
    assert response["Location"].endswith("clientSecret=cs_x")
    assert (order.amount_cents, order.currency, order.status) == (
        price.amount_cents,
        "EGP",
        OrderStatus.CREATED,
    )
    sent = fake.intentions[0]
    assert sent["amount_cents"] == price.amount_cents
    assert sent["reference"] == str(order.pk)
    assert sent["notification_url"] == "http://testserver/payments/paymob/callback/"
    assert sent["redirection_url"] == "http://testserver/pay/done/"
    assert order.paymob_order_id == fake.next_order_id
    plan.refresh_from_db()
    assert plan.paid_at is None  # starting checkout never unlocks


def test_paymob_down_marks_the_order_failed(client, plan, keys, fake):
    fake.fail = True
    assert client.post("/pay/start/")["Location"] == "/pay/?error=1"
    assert Order.objects.get().status == OrderStatus.FAILED
    assert "الدفع مبدأش" in client.get("/pay/?error=1").content.decode()


def test_checkout_is_rate_limited(client, plan, keys, fake):
    for _ in range(services.CHECKOUTS_PER_HOUR):
        client.post("/pay/start/")
    assert client.post("/pay/start/")["Location"] == "/pay/?error=1"
    assert Order.objects.count() == services.CHECKOUTS_PER_HOUR


def test_paid_plan_skips_checkout(client, plan, keys, fake):
    Plan.objects.filter(pk=plan.pk).update(paid_at=timezone.now())
    assert client.get("/pay/")["Location"] == "/plan/"
    assert client.post("/pay/start/")["Location"] == "/plan/"


def test_another_users_plan_cannot_be_bought(plan, keys, fake):
    other = User.objects.create_user("+201009999999")
    with pytest.raises(services.CheckoutClosedError):
        services.start_checkout(other, plan, notification_url="x", redirection_url="y")


def test_pages_need_a_plan_and_login(keys, fake):
    assert Client().get("/pay/")["Location"].startswith("/login/")
    user = User.objects.create_user("+201007777777")
    c = Client()
    c.force_login(user)
    assert c.get("/pay/")["Location"] == "/"
    assert c.post("/pay/start/")["Location"] == "/"
    assert c.get("/pay/done/")["Location"] == "/plan/"


# ---------------------------------------------------------------- callbacks


def test_verified_callback_unlocks_the_plan(client, plan, keys, fake):
    order = checkout(client, plan)
    assert "بنأكد الدفع" in client.get("/pay/done/").content.decode()
    assert post_callback(tx(order)).status_code == 200
    order.refresh_from_db()
    plan.refresh_from_db()
    assert order.status == OrderStatus.PAID
    assert plan.paid_at == order.paid_at
    payment = Payment.objects.get()
    assert (payment.paymob_transaction_id, payment.source_sub_type) == (900001, "MasterCard")
    assert not hasattr(payment, "pan")
    assert AuditEvent.objects.filter(
        action=AuditAction.PAYMENT_STATUS_CHANGED, target_id=str(order.pk)
    ).exists()
    assert "الخطة كلها مفتوحة" in client.get("/pay/done/").content.decode()


def test_callback_is_idempotent(client, plan, keys, fake):
    order = checkout(client, plan)
    for _ in range(3):
        assert post_callback(tx(order)).status_code == 200
    order.refresh_from_db()
    assert Payment.objects.get().callbacks == 3
    assert AuditEvent.objects.filter(action=AuditAction.PAYMENT_STATUS_CHANGED).count() == 1
    assert order.status == OrderStatus.PAID


def test_bad_hmac_is_rejected_and_changes_nothing(client, plan, keys, fake):
    order = checkout(client, plan)
    assert post_callback(tx(order), secret="wrong").status_code == 401
    obj = tx(order)
    signature = paymob.transaction_hmac(obj, HMAC_SECRET)
    tampered = {**obj, "amount_cents": 100}
    response = Client().post(
        f"/payments/paymob/callback/?hmac={signature}",
        data={"type": "TRANSACTION", "obj": tampered},
        content_type="application/json",
    )
    assert response.status_code == 401
    no_hmac = Client().post(
        "/payments/paymob/callback/",
        data={"type": "TRANSACTION", "obj": obj},
        content_type="application/json",
    )
    assert no_hmac.status_code == 401
    plan.refresh_from_db()
    assert plan.paid_at is None
    assert not Payment.objects.exists()


def test_without_keys_every_callback_is_rejected(client, plan, keys, fake):
    order = checkout(client, plan)
    keys.PAYMOB_HMAC_SECRET = ""
    assert post_callback(tx(order), secret="").status_code == 401


@pytest.mark.parametrize("body", [b"not json", b"[]", b'{"obj": 1}'])
def test_malformed_callbacks_are_rejected(keys, body):
    response = Client().post(
        "/payments/paymob/callback/?hmac=x", data=body, content_type="application/json"
    )
    assert response.status_code in (400, 401)


def test_callback_needs_post(keys):
    assert Client().get("/payments/paymob/callback/").status_code == 405


@pytest.mark.parametrize(
    "changes", [{"amount_cents": 100}, {"currency": "USD"}], ids=["amount", "currency"]
)
def test_amount_or_currency_mismatch_never_unlocks(client, plan, keys, fake, changes):
    order = checkout(client, plan)
    assert post_callback(tx(order, **changes)).status_code == 200
    order.refresh_from_db()
    plan.refresh_from_db()
    assert order.status == OrderStatus.MISMATCH
    assert plan.paid_at is None
    assert "بنراجع الدفع" in client.get("/pay/done/").content.decode()


def test_declined_then_paid(client, plan, keys, fake):
    order = checkout(client, plan)
    post_callback(tx(order, success=False))
    order.refresh_from_db()
    assert order.status == OrderStatus.FAILED
    assert "الدفع مكملش" in client.get("/pay/done/").content.decode()
    post_callback(tx(order, id=900002))
    order.refresh_from_db()
    assert order.status == OrderStatus.PAID


def test_pending_changes_nothing(client, plan, keys, fake):
    order = checkout(client, plan)
    post_callback(tx(order, success=False, pending=True))
    order.refresh_from_db()
    assert order.status == OrderStatus.CREATED


def test_order_found_by_merchant_reference(client, plan, keys, fake):
    order = checkout(client, plan)
    obj = tx(order, order={"id": 1, "merchant_order_id": str(order.pk)})
    post_callback(obj)
    order.refresh_from_db()
    assert order.status == OrderStatus.PAID


@pytest.mark.parametrize("order_data", [{"id": 1}, {"id": 1, "merchant_order_id": "nope"}, None])
def test_unknown_order_is_acknowledged_but_changes_nothing(client, plan, keys, fake, order_data):
    order = checkout(client, plan)
    assert post_callback(tx(order, order=order_data)).status_code == 200
    assert not Payment.objects.exists()


def test_non_transaction_callbacks_are_ignored(client, plan, keys, fake):
    order = checkout(client, plan)
    assert post_callback(tx(order), kind="TOKEN").status_code == 200
    assert not Payment.objects.exists()


def test_redirect_query_string_never_unlocks(client, plan, keys, fake):
    checkout(client, plan)
    client.get("/pay/done/?success=true&amount_cents=34900&hmac=whatever")
    plan.refresh_from_db()
    assert plan.paid_at is None


def test_done_page_shows_only_my_order(client, plan, keys, fake):
    checkout(client, plan)
    stranger = User.objects.create_user("+201008888888")
    c = Client()
    c.force_login(stranger)
    session = c.session
    session["last_order_id"] = str(Order.objects.get().pk)
    session.save()
    assert c.get("/pay/done/")["Location"] == "/plan/"
    session["last_order_id"] = "not-a-uuid"
    session.save()
    assert c.get("/pay/done/")["Location"] == "/plan/"


def test_paid_after_refund_needs_staff(client, plan, keys, fake):
    order = checkout(client, plan)
    Order.objects.filter(pk=order.pk).update(status=OrderStatus.REFUNDED)
    post_callback(tx(order, id=900005))
    order.refresh_from_db()
    plan.refresh_from_db()
    assert order.status == OrderStatus.REFUNDED
    assert plan.paid_at is None


def test_callbacks_are_rate_limited_per_ip(keys, monkeypatch):
    monkeypatch.setattr(views, "CALLBACKS_PER_MINUTE_PER_IP", 2)
    c = Client()
    statuses = [
        c.post("/payments/paymob/callback/", data=b"x", content_type="application/json").status_code
        for _ in range(3)
    ]
    assert statuses == [400, 400, 429]


# ---------------------------------------------------------------- refunds


@pytest.fixture
def paid(client, plan, keys, fake):
    order = checkout(client, plan)
    post_callback(tx(order))
    order.refresh_from_db()
    return order


@pytest.fixture
def finance():
    user = User.objects.create_user("+201005555555", "pw-not-used", is_staff=True)
    user.user_permissions.add(Permission.objects.get(codename="refund_order"))
    return User.objects.get(pk=user.pk)


def test_refund_locks_the_plan_again(paid, plan, finance, fake):
    services.refund(paid, actor=finance)
    paid.refresh_from_db()
    plan.refresh_from_db()
    assert paid.status == OrderStatus.REFUNDED
    assert plan.paid_at is None
    assert fake.refunds == [(900001, paid.amount_cents)]
    event = AuditEvent.objects.filter(actor=finance).get()
    assert event.metadata["to"] == "refunded"


def test_refund_needs_the_permission(paid):
    staff = User.objects.create_user("+201006666666", "pw", is_staff=True)
    with pytest.raises(PermissionError):
        services.refund(paid, actor=staff)


def test_refund_only_once_and_only_paid(paid, finance, fake):
    services.refund(paid, actor=finance)
    with pytest.raises(services.RefundError):
        services.refund(paid, actor=finance)
    assert len(fake.refunds) == 1


def test_refund_failure_keeps_the_order_paid(paid, plan, finance, fake):
    fake.fail = True
    with pytest.raises(services.RefundError):
        services.refund(paid, actor=finance)
    paid.refresh_from_db()
    assert paid.status == OrderStatus.PAID


def test_refund_without_a_transaction(finance, plan, keys):
    order = Order.objects.create(
        user=plan.user, plan=plan, product="short", amount_cents=1, currency="EGP", status="paid"
    )
    with pytest.raises(services.RefundError):
        services.refund(order, actor=finance)


def test_refund_callback_from_paymob_locks_the_plan(paid, plan):
    post_callback(tx(paid, is_refunded=True))
    paid.refresh_from_db()
    plan.refresh_from_db()
    assert paid.status == OrderStatus.REFUNDED
    assert plan.paid_at is None


def test_redoing_the_questions_for_the_same_race_keeps_the_payment(client, paid, plan):
    client.post("/plan/save/")
    new = Plan.objects.get(is_active=True)
    assert new.pk != plan.pk
    assert new.paid_at is not None


def test_admin_refund_action(paid, finance, fake):
    c = Client()
    c.force_login(finance)
    url = f"/{settings.ADMIN_URL}payments/order/"
    finance.user_permissions.add(Permission.objects.get(codename="view_order"))
    assert paid.plan.race.name in c.get(url).content.decode()
    response = c.post(url, {"action": "refund_in_full", "_selected_action": [str(paid.pk)]})
    assert response.status_code == 302
    paid.refresh_from_db()
    assert paid.status == OrderStatus.REFUNDED


def test_admin_without_refund_permission_has_no_action(paid):
    viewer = User.objects.create_user("+201004444444", "pw", is_staff=True)
    viewer.user_permissions.add(Permission.objects.get(codename="view_order"))
    c = Client()
    c.force_login(viewer)
    html = c.get(f"/{settings.ADMIN_URL}payments/order/").content.decode()
    assert "refund_in_full" not in html
    assert paid.refunded_at is None
    assert paid.created_at < timezone.now() + timedelta(seconds=1)
