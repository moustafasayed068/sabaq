"""Read queries for payments, always scoped to the owner."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError

from apps.payments.models import Order

if TYPE_CHECKING:
    from apps.accounts.models import User


def order_for(user: User, order_id: str | None) -> Order | None:
    if not order_id:
        return None
    try:
        return Order.objects.select_related("plan").filter(user=user, pk=order_id).first()
    except (ValueError, TypeError, ValidationError):  # not a UUID
        return None
