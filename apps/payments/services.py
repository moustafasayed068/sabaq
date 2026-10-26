"""Public API of the payments app: prices, checkout, Paymob callbacks and refunds.

Rules (docs/security.md): the price comes from the server, never the browser; a plan is unlocked
only by a verified, idempotent Paymob callback whose amount and currency match the order; the
redirect back from Paymob never unlocks anything.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core import ratelimit
from apps.core.export import row
from apps.core.services import AuditAction, record_audit
from apps.payments import paymob
from apps.payments.models import Order, OrderStatus, Payment, Product
from apps.payments.selectors import order_for
from apps.plans import services as plans

if TYPE_CHECKING:
    from apps.accounts.models import User
    from apps.plans.models import Plan

__all__ = [
    "CallbackResult",
    "CheckoutClosedError",
    "CheckoutError",
    "Price",
    "RefundError",
    "export_for",
    "handle_callback",
    "is_open",
    "order_for",
    "price_for_plan",
    "price_for_weeks",
    "prices",
    "refund",
    "start_checkout",
]

log = logging.getLogger(__name__)

CURRENCY = "EGP"
# Test prices from docs/product.md, in piastres. "Last month" covers plans up to 4 weeks;
# anything longer is the long plan (the doc lists 8-16 weeks; 5-7 weeks is priced long too).
PRICE_CENTS = {Product.SHORT: 349_00, Product.LONG: 799_00}
SHORT_PLAN_MAX_WEEKS = 4
CHECKOUTS_PER_HOUR = 10


class CheckoutError(Exception):
    """Checkout could not start (Paymob unreachable, refused, or too many attempts)."""


class CheckoutClosedError(CheckoutError):
    """Paymob keys are not configured, or this plan cannot be bought."""


class RefundError(Exception):
    pass


@dataclass(frozen=True)
class Price:
    product: Product
    amount_cents: int
    currency: str

    @property
    def amount(self) -> int:
        """Whole pounds, for display."""
        return self.amount_cents // 100


def prices() -> dict[str, Price]:
    return {str(p): Price(p, PRICE_CENTS[p], CURRENCY) for p in Product}


def price_for_weeks(weeks: int) -> Price:
    product = Product.SHORT if weeks <= SHORT_PLAN_MAX_WEEKS else Product.LONG
    return Price(product, PRICE_CENTS[product], CURRENCY)


def price_for_plan(plan: Plan) -> Price:
    return price_for_weeks(plans.week_count(plan))


def is_open() -> bool:
    return paymob.PaymobConfig.from_settings().is_complete


# ---------------------------------------------------------------- checkout


def start_checkout(
    user: User, plan: Plan, *, notification_url: str, redirection_url: str
) -> tuple[Order, str]:
    """Create an Order at the server price and return it with Paymob's checkout URL."""
    if not is_open():
        raise CheckoutClosedError("payments are not configured")
    if plan.user_id != user.pk or not plan.is_active or plan.paid_at is not None:
        raise CheckoutClosedError("plan cannot be bought")
    if not ratelimit.hit(f"checkout:{user.pk}", limit=CHECKOUTS_PER_HOUR, window_s=3600):
        raise CheckoutError("too many checkouts")
    price = price_for_plan(plan)
    order = Order.objects.create(
        user=user,
        plan=plan,
        product=price.product,
        amount_cents=price.amount_cents,
        currency=price.currency,
    )
    client = paymob.client()
    try:
        intention = client.create_intention(
            amount_cents=order.amount_cents,
            currency=order.currency,
            item_name=f"خطة سبق: {plan.race.name}",
            reference=str(order.pk),
            phone=user.phone,
            notification_url=notification_url,
            redirection_url=redirection_url,
        )
    except paymob.PaymobError as exc:
        order.status = OrderStatus.FAILED
        order.save(update_fields=["status", "updated_at"])
        raise CheckoutError(str(exc)) from exc
    order.intention_id = intention.id
    order.paymob_order_id = intention.paymob_order_id
    order.save(update_fields=["intention_id", "paymob_order_id", "updated_at"])
    return order, client.checkout_url(intention.client_secret)


# ---------------------------------------------------------------- callbacks


class CallbackResult(enum.Enum):
    REJECTED = "rejected"  # bad or missing HMAC: answer 401, change nothing
    IGNORED = "ignored"  # not a transaction (e.g. a saved-card token)
    UNKNOWN_ORDER = "unknown_order"
    RECORDED = "recorded"


def _find_order(obj: dict[str, Any]) -> Order | None:
    order_data = obj.get("order")
    if not isinstance(order_data, dict):
        return None
    paymob_order_id = order_data.get("id")
    if isinstance(paymob_order_id, int):
        found = Order.objects.filter(paymob_order_id=paymob_order_id).first()
        if found is not None:
            return found
    reference = order_data.get("merchant_order_id") or obj.get("special_reference")
    if isinstance(reference, str):
        try:
            return Order.objects.filter(pk=reference).first()
        except (ValueError, ValidationError):  # not a UUID: not ours
            return None
    return None


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _set_status(order: Order, status: OrderStatus, **reason: str | int | bool | None) -> None:
    old = order.status
    order.status = status
    order.save(update_fields=["status", "paid_at", "refunded_at", "updated_at"])
    record_audit(
        AuditAction.PAYMENT_STATUS_CHANGED,
        target=order,
        metadata={"from": old, "to": str(status), **reason},
    )
    log.info("payments.status", extra={"order": str(order.pk), "from": old, "to": str(status)})


def _record_payment(order: Order, obj: dict[str, Any], tx_id: int) -> Payment:
    raw_source = obj.get("source_data")
    source: dict[str, Any] = raw_source if isinstance(raw_source, dict) else {}
    fields = {
        "amount_cents": _as_int(obj.get("amount_cents")) or 0,
        "currency": str(obj.get("currency") or "")[:3],
        "success": obj.get("success") is True,
        "pending": obj.get("pending") is True,
        "is_refunded": obj.get("is_refunded") is True,
        "is_voided": obj.get("is_voided") is True,
        "is_refund": obj.get("is_refund") is True,
        # Card brand and type only; the masked PAN is never stored.
        "source_type": str(source.get("type") or "")[:30],
        "source_sub_type": str(source.get("sub_type") or "")[:30],
    }
    payment = Payment.objects.select_for_update().filter(paymob_transaction_id=tx_id).first()
    if payment is None:
        return Payment.objects.create(order=order, paymob_transaction_id=tx_id, **fields)
    for name, value in fields.items():
        setattr(payment, name, value)
    payment.callbacks += 1
    payment.save()
    return payment


def handle_callback(
    payload: object, received_hmac: str, secret: str | None = None
) -> CallbackResult:
    """Process one Paymob "transaction processed" callback. Safe to call many times."""
    if not isinstance(payload, dict) or not isinstance(payload.get("obj"), dict):
        return CallbackResult.REJECTED
    obj: dict[str, Any] = payload["obj"]
    secret = secret if secret is not None else paymob.PaymobConfig.from_settings().hmac_secret
    if not paymob.hmac_matches(obj, received_hmac, secret):
        log.warning("payments.callback_bad_hmac")
        return CallbackResult.REJECTED
    if payload.get("type") != "TRANSACTION":
        return CallbackResult.IGNORED
    tx_id = _as_int(obj.get("id"))
    if tx_id is None:
        return CallbackResult.REJECTED

    with transaction.atomic():
        found = _find_order(obj)
        if found is None:
            log.error("payments.callback_unknown_order", extra={"transaction": tx_id})
            return CallbackResult.UNKNOWN_ORDER
        order = Order.objects.select_for_update().get(pk=found.pk)
        payment = _record_payment(order, obj, tx_id)
        _apply(order, payment)
    return CallbackResult.RECORDED


def _apply(order: Order, payment: Payment) -> None:
    now = timezone.now()
    if payment.is_refunded or payment.is_voided or payment.is_refund:
        if order.status == OrderStatus.PAID:
            order.refunded_at = now
            _set_status(order, OrderStatus.REFUNDED, transaction=payment.paymob_transaction_id)
            _lock(order)
        return
    if payment.pending:
        return
    if not payment.success:
        if order.status == OrderStatus.CREATED:
            _set_status(order, OrderStatus.FAILED, transaction=payment.paymob_transaction_id)
        return
    matches = (payment.amount_cents, payment.currency) == (order.amount_cents, order.currency)
    if not matches:
        if order.status in (OrderStatus.CREATED, OrderStatus.FAILED):
            log.error("payments.amount_mismatch", extra={"order": str(order.pk)})
            _set_status(
                order,
                OrderStatus.MISMATCH,
                transaction=payment.paymob_transaction_id,
                paid_cents=payment.amount_cents,
            )
        return
    if order.status in (OrderStatus.CREATED, OrderStatus.FAILED):
        order.paid_at = now
        _set_status(order, OrderStatus.PAID, transaction=payment.paymob_transaction_id)
        if order.plan_id is not None:
            plans.mark_paid(order.plan_id, now)
    elif order.status == OrderStatus.PAID:
        return  # a repeated callback: already done
    else:
        # Paid after a refund or a mismatch: never unlock by itself; staff look at it.
        log.error("payments.paid_needs_review", extra={"order": str(order.pk)})


def _lock(order: Order) -> None:
    if order.plan is not None and order.user_id is not None:
        plans.mark_unpaid(order.user_id, order.plan.race_id)


# ---------------------------------------------------------------- refunds (staff)


def refund(order: Order, *, actor: User) -> None:
    """Refund a paid order in full through Paymob, then lock the plan back to week 1."""
    if not actor.has_perm("payments.refund_order"):
        raise PermissionError("needs payments.refund_order")
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order.pk)
        if order.status != OrderStatus.PAID:
            raise RefundError("only paid orders can be refunded")
        paid = order.payments.filter(success=True, is_refund=False).order_by("created_at").first()
        if paid is None:
            raise RefundError("no successful transaction on this order")
        try:
            paymob.client().refund(
                transaction_id=paid.paymob_transaction_id, amount_cents=order.amount_cents
            )
        except paymob.PaymobError as exc:
            raise RefundError(str(exc)) from exc
        order.refunded_at = timezone.now()
        old = order.status
        order.status = OrderStatus.REFUNDED
        order.save(update_fields=["status", "refunded_at", "updated_at"])
        record_audit(
            AuditAction.PAYMENT_STATUS_CHANGED,
            actor=actor,
            target=order,
            metadata={"from": old, "to": OrderStatus.REFUNDED, "by": "staff"},
        )
        _lock(order)


# ---------------------------------------------------------------- the athlete's own data


def export_for(user: User) -> dict[str, Any]:
    return {
        "orders": [
            row(o, skip=("user", "intention_id"))
            for o in Order.objects.filter(user=user).order_by("created_at")
        ]
    }
