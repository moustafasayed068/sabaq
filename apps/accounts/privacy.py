"""The athlete's rights over their data (docs/security.md): download everything, and delete
the account. Deletion removes answers, health data, plans and check-ins. Payment records stay
(tax law) without a link to the person: only amount, date, status and Paymob ids."""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import LoginCode, User
from apps.athletes import services as athletes
from apps.core import ratelimit
from apps.core.services import AuditAction, record_audit
from apps.payments import services as payments
from apps.plans import services as plans

EXPORTS_PER_HOUR = 5
FORMAT_VERSION = 1


class TooManyExportsError(Exception):
    pass


def export_data(user: User) -> dict[str, Any]:
    if not ratelimit.hit(f"export:{user.pk}", limit=EXPORTS_PER_HOUR, window_s=3600):
        raise TooManyExportsError
    data: dict[str, Any] = {
        "format": FORMAT_VERSION,
        "exported_at": timezone.now().isoformat(),
        "account": {
            "phone": user.phone,
            "created_at": user.created_at.isoformat(),
            "phone_verified_at": user.phone_verified_at.isoformat()
            if user.phone_verified_at
            else None,
        },
        **athletes.export_for(user),
        **plans.export_for(user),
        **payments.export_for(user),
    }
    record_audit(AuditAction.DATA_EXPORTED, actor=user, target=user)
    return data


@transaction.atomic
def delete_account(user: User) -> None:
    if user.is_staff or user.is_superuser:
        raise PermissionError("staff accounts are removed by the owner, not from the site")
    orders_kept = payments.export_for(user)["orders"]
    record_audit(
        AuditAction.ACCOUNT_DELETED,
        target=user,
        metadata={"orders_kept": len(orders_kept)},
    )
    LoginCode.objects.filter(phone=user.phone).delete()
    # Cascades: questionnaires (consents, health screens), plans (weeks, days, check-ins,
    # day marks). Orders keep their row with user and plan set to NULL.
    user.delete()
