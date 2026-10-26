"""Audit every change to what a staff account can do (docs/security.md)."""

from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models.signals import m2m_changed, post_save, pre_save

from apps.core.models import AuditAction
from apps.core.services import record_audit

_FLAGS = ("is_staff", "is_superuser", "is_active")
_WRITE = {"post_add", "post_remove", "post_clear"}


def _user_flags(sender: Any, instance: Any, **kwargs: Any) -> None:  # noqa: ANN401
    old = sender.objects.filter(pk=instance.pk).values(*_FLAGS).first() if instance.pk else None
    instance._audit_old_flags = old


def _user_saved(sender: Any, instance: Any, created: bool, **kwargs: Any) -> None:  # noqa: ANN401
    old = getattr(instance, "_audit_old_flags", None)
    new = {f: getattr(instance, f) for f in _FLAGS}
    if created:
        if new["is_staff"] or new["is_superuser"]:
            record_audit(
                AuditAction.STAFF_PERMISSIONS_CHANGED,
                target=instance,
                metadata={"change": "created", **new},
            )
        return
    if old is not None and old != new:
        changed = {f: new[f] for f in _FLAGS if old[f] != new[f]}
        record_audit(
            AuditAction.STAFF_PERMISSIONS_CHANGED,
            target=instance,
            metadata={"change": "flags", **changed},
        )


def _user_m2m(sender: Any, instance: Any, action: str, pk_set: Any, **kwargs: Any) -> None:  # noqa: ANN401
    if action not in _WRITE:
        return
    field = "groups" if sender is get_user_model().groups.through else "user_permissions"
    if isinstance(instance, get_user_model()):
        record_audit(
            AuditAction.STAFF_PERMISSIONS_CHANGED,
            target=instance,
            metadata={"change": f"{field}:{action}", "count": len(pk_set or ())},
        )
    else:  # reverse side: users added to or removed from a group, or a permission's users
        for user in get_user_model().objects.filter(pk__in=pk_set or ()):
            record_audit(
                AuditAction.STAFF_PERMISSIONS_CHANGED,
                target=user,
                metadata={"change": f"{field}:{action}", "count": 1},
            )


def _group_permissions(sender: Any, instance: Any, action: str, pk_set: Any, **kwargs: Any) -> None:  # noqa: ANN401
    if action in _WRITE and isinstance(instance, Group):
        record_audit(
            AuditAction.STAFF_PERMISSIONS_CHANGED,
            target=instance,
            metadata={"change": f"group_permissions:{action}", "count": len(pk_set or ())},
        )


def connect() -> None:
    user = get_user_model()
    pre_save.connect(_user_flags, sender=user, dispatch_uid="audit_user_flags_pre")
    post_save.connect(_user_saved, sender=user, dispatch_uid="audit_user_flags_post")
    m2m_changed.connect(_user_m2m, sender=user.groups.through, dispatch_uid="audit_user_groups")
    m2m_changed.connect(
        _user_m2m, sender=user.user_permissions.through, dispatch_uid="audit_user_perms"
    )
    m2m_changed.connect(
        _group_permissions, sender=Group.permissions.through, dispatch_uid="audit_group_perms"
    )
