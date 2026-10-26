"""Orders and Paymob transactions. Money is integer cents (piastres) plus a currency code.

We never see or store card numbers: only Paymob ids, amounts, status and the card brand.
Finance records outlive accounts (tax law), so deleting a user or a plan keeps the order.
"""

from __future__ import annotations

from typing import ClassVar

from django.conf import settings
from django.db import models

from apps.core.models import BaseModel
from apps.plans.models import Plan


class Product(models.TextChoices):
    SHORT = "short", "خطة الشهر الأخير"
    LONG = "long", "خطة طويلة"


class OrderStatus(models.TextChoices):
    CREATED = "created"  # checkout started, nothing heard from Paymob yet
    PAID = "paid"
    FAILED = "failed"  # Paymob declined; the athlete can try again with a new order
    REFUNDED = "refunded"
    # A verified callback whose amount or currency does not match: never unlocks, staff review.
    MISMATCH = "mismatch"


class Order(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="orders"
    )
    plan = models.ForeignKey(Plan, null=True, on_delete=models.SET_NULL, related_name="orders")
    product = models.CharField(max_length=10, choices=Product.choices)
    amount_cents = models.PositiveIntegerField()
    currency = models.CharField(max_length=3)
    status = models.CharField(
        max_length=10, choices=OrderStatus.choices, default=OrderStatus.CREATED, db_index=True
    )
    intention_id = models.CharField(max_length=80, blank=True)
    paymob_order_id = models.BigIntegerField(null=True, blank=True, unique=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]
        permissions = (("refund_order", "Can refund a paid order through Paymob"),)

    def __str__(self) -> str:
        return f"Order {self.pk} ({self.status}, {self.amount_cents / 100:.2f} {self.currency})"


class Payment(BaseModel):
    """One verified Paymob transaction callback. Unique by Paymob transaction id, so a
    repeated callback updates the row instead of adding one (idempotent)."""

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="payments")
    paymob_transaction_id = models.BigIntegerField(unique=True)
    amount_cents = models.PositiveIntegerField()
    currency = models.CharField(max_length=3)
    success = models.BooleanField()
    pending = models.BooleanField()
    is_refunded = models.BooleanField(default=False)
    is_voided = models.BooleanField(default=False)
    is_refund = models.BooleanField(default=False)  # a refund transaction (has a parent)
    source_type = models.CharField(max_length=30, blank=True)  # card, wallet, ...
    source_sub_type = models.CharField(max_length=30, blank=True)  # MasterCard, Visa, ...
    callbacks = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]

    def __str__(self) -> str:
        return f"Paymob transaction {self.paymob_transaction_id}"
