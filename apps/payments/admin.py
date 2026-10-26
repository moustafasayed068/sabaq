"""Read-only orders and transactions, plus a full refund action for staff with
payments.refund_order. Statuses change only through services (callbacks or refunds)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest

from apps.payments import services
from apps.payments.models import Order, OrderStatus, Payment


class PaymentInline(admin.TabularInline):  # type: ignore[type-arg]
    model = Payment
    extra = 0
    can_delete = False
    fields = (
        "paymob_transaction_id",
        "amount_cents",
        "currency",
        "success",
        "pending",
        "is_refunded",
        "is_voided",
        "is_refund",
        "source_type",
        "source_sub_type",
        "callbacks",
        "created_at",
    )
    readonly_fields = fields

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = (
        "created_at",
        "status",
        "amount",
        "product",
        "user",
        "race",
        "week_two_starts",
    )
    list_filter = ("status", "product", "currency")
    search_fields = ("=id", "=paymob_order_id", "=payments__paymob_transaction_id")
    readonly_fields = (
        "id",
        "user",
        "plan",
        "product",
        "amount_cents",
        "currency",
        "status",
        "intention_id",
        "paymob_order_id",
        "paid_at",
        "refunded_at",
        "created_at",
        "updated_at",
    )
    fields = readonly_fields
    inlines = (PaymentInline,)
    actions = ("refund_in_full",)

    def get_queryset(self, request: HttpRequest) -> QuerySet[Order]:
        return super().get_queryset(request).select_related("user", "plan__race")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False

    @admin.display(description="Amount")
    def amount(self, obj: Order) -> str:
        return f"{obj.amount_cents / 100:.2f} {obj.currency}"

    @admin.display(description="Race")
    def race(self, obj: Order) -> str:
        return obj.plan.race.name if obj.plan else "—"

    @admin.display(description="Week 2 starts (refund in full before)")
    def week_two_starts(self, obj: Order) -> date | None:
        return obj.plan.starts_on + timedelta(days=7) if obj.plan else None

    @admin.action(description="Refund in full through Paymob", permissions=["refund"])
    def refund_in_full(self, request: HttpRequest, queryset: QuerySet[Order]) -> None:
        done = 0
        for order in queryset:
            if order.status != OrderStatus.PAID:
                continue
            try:
                services.refund(order, actor=request.user)  # type: ignore[arg-type]
            except services.RefundError as exc:
                self.message_user(request, f"{order.pk}: {exc}", messages.ERROR)
            else:
                done += 1
        self.message_user(request, f"Refunded {done} order(s).", messages.SUCCESS)

    def has_refund_permission(self, request: HttpRequest) -> bool:
        return request.user.has_perm("payments.refund_order")
