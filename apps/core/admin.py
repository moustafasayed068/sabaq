from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from apps.core.models import AuditAction, AuditEvent, FeatureFlag
from apps.core.services import record_audit


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Read-only: the audit log is append-only."""

    list_display = ("created_at", "action", "actor", "target_type", "target_id", "ip_address")
    list_filter = ("action",)
    search_fields = ("target_id", "request_id")
    list_select_related = ("actor",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False


@admin.register(FeatureFlag)
class FeatureFlagAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("name", "enabled", "description", "updated_at")
    list_editable = ("enabled",)

    def save_model(self, request: HttpRequest, obj: FeatureFlag, form: Any, change: bool) -> None:  # noqa: ANN401
        super().save_model(request, obj, form, change)
        record_audit(
            AuditAction.FEATURE_FLAG_CHANGED,
            target=obj,
            request=request,
            metadata={"name": obj.name, "enabled": obj.enabled},
        )
