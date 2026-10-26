"""Read queries for plans, always scoped to the owner."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Prefetch

from apps.plans.models import Plan, PlanDay, PlanWeek

if TYPE_CHECKING:
    from apps.accounts.models import User


def active_plan(user: User) -> Plan | None:
    """The user's current plan with weeks and days in 3 queries."""
    weeks = PlanWeek.objects.prefetch_related(
        Prefetch("days", queryset=PlanDay.objects.order_by("date"))
    )
    return (
        Plan.objects.filter(user=user, is_active=True)
        .select_related("race")
        .prefetch_related(Prefetch("weeks", queryset=weeks))
        .first()
    )
