"""Public API of the core app. Other apps call these functions, never the models directly."""

from typing import TYPE_CHECKING

from django.db.models import Model
from django.http import HttpRequest

from apps.core import flags
from apps.core.models import AuditAction, AuditEvent
from apps.core.request_context import client_ip, get_request_id

if TYPE_CHECKING:
    from apps.accounts.models import User

__all__ = ["AuditAction", "is_enabled", "record_audit"]

is_enabled = flags.is_enabled


def record_audit(
    action: AuditAction,
    *,
    actor: "User | None" = None,
    target: Model | None = None,
    request: HttpRequest | None = None,
    metadata: dict[str, str | int | bool | None] | None = None,
) -> AuditEvent:
    """Append one audit event. `metadata` must never hold personal or health data."""
    if actor is None and request is not None and request.user.is_authenticated:
        actor = request.user
    return AuditEvent.objects.create(
        action=action,
        actor=actor if actor is not None and actor.pk else None,
        target_type=target._meta.label_lower if target is not None else "",
        target_id=str(target.pk) if target is not None else "",
        ip_address=client_ip(request) if request is not None else None,
        request_id=get_request_id(),
        metadata=metadata or {},
    )
