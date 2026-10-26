"""Shared building blocks: the base model, the audit log and feature flags."""

from __future__ import annotations

import uuid
from typing import Any, ClassVar, NoReturn

from django.conf import settings
from django.db import models


class BaseModel(models.Model):
    """UUID primary key (safe in URLs) and timestamps on every table."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AppendOnlyError(Exception):
    """Raised when code tries to change or delete an audit event."""


class AuditEventQuerySet(models.QuerySet["AuditEvent"]):
    def update(self, **kwargs: Any) -> NoReturn:  # noqa: ANN401
        raise AppendOnlyError("Audit events cannot be updated.")

    def delete(self) -> NoReturn:
        raise AppendOnlyError("Audit events cannot be deleted.")


class AuditAction(models.TextChoices):
    LOGIN = "login"
    LOGIN_CODE_FAILED = "login_code_failed"
    LOGOUT = "logout"
    HEALTH_DATA_VIEWED = "health_data_viewed"
    PLAN_PAUSED = "plan_paused"
    PLAN_RESUMED = "plan_resumed"
    PAYMENT_STATUS_CHANGED = "payment_status_changed"
    DATA_EXPORTED = "data_exported"
    ACCOUNT_DELETED = "account_deleted"
    STAFF_PERMISSIONS_CHANGED = "staff_permissions_changed"
    FEATURE_FLAG_CHANGED = "feature_flag_changed"
    LOGIN_CODE_VIEWED = "login_code_viewed"


class AuditEvent(models.Model):
    """Append-only record of security-relevant events (docs/security.md).

    Never put health answers, phone numbers, tokens or card data in `metadata`.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    action = models.CharField(max_length=40, choices=AuditAction.choices, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    target_type = models.CharField(max_length=60, blank=True)
    target_id = models.CharField(max_length=64, blank=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    objects: ClassVar[AuditEventQuerySet] = AuditEventQuerySet.as_manager()  # type: ignore[assignment]

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["target_type", "target_id"], name="core_audit_target_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.action} {self.target_type}:{self.target_id}"

    def save(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        if not self._state.adding:
            raise AppendOnlyError("Audit events cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:  # noqa: ANN401
        raise AppendOnlyError("Audit events cannot be deleted.")


class FeatureFlag(BaseModel):
    """A switch for risky features, flipped in the admin without a deploy."""

    name = models.SlugField(max_length=80, unique=True)
    enabled = models.BooleanField(default=False)
    description = models.CharField(max_length=200, blank=True)

    def __str__(self) -> str:
        return f"{self.name}={'on' if self.enabled else 'off'}"
