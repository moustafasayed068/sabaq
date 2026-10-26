"""Admin for athlete data. Health answers are shown only to the health_viewer role, and
every view of them is written to the audit log (docs/security.md)."""

from typing import Any

from django.contrib import admin
from django.http import HttpRequest, HttpResponse

from apps.athletes.models import Consent, HealthScreen, Questionnaire
from apps.core.services import AuditAction, record_audit

HEALTH_PERMISSION = "athletes.view_health_answers"


@admin.register(Questionnaire)
class QuestionnaireAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("pk", "race", "user", "created_at")
    list_select_related = ("race", "user")
    list_filter = ("race",)
    readonly_fields = ("session_key", "completed_steps", "created_at", "updated_at")
    exclude = ("session_key",)


@admin.register(Consent)
class ConsentAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("kind", "text_version", "created_at")
    readonly_fields = ("questionnaire", "user", "kind", "text_version", "text_sha256", "created_at")

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False


@admin.register(HealthScreen)
class HealthScreenAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("pk", "questionnaire", "created_at")
    fields = ("questionnaire", "data", "created_at", "updated_at")
    readonly_fields = fields

    def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return request.user.has_perm(HEALTH_PERMISSION)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: Any = None,  # noqa: ANN401
    ) -> HttpResponse:
        response = super().change_view(request, object_id, form_url, extra_context)
        if response.status_code == 200:
            screen = self.get_object(request, object_id)
            record_audit(AuditAction.HEALTH_DATA_VIEWED, target=screen, request=request)
        return response
