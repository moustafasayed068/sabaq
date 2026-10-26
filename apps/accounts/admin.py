from typing import Any

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from apps.accounts.models import LoginCode, User
from apps.core.services import AuditAction, record_audit


@admin.register(User)
class UserAdmin(BaseUserAdmin):  # type: ignore[type-arg]
    ordering = ("-created_at",)
    list_display = ("__str__", "is_staff", "is_active", "created_at")
    list_filter = ("is_staff", "is_active")
    search_fields = ("phone",)
    readonly_fields = ("id", "created_at", "updated_at", "last_login", "phone_verified_at")
    fieldsets = (
        (None, {"fields": ("id", "phone", "password")}),
        ("Status", {"fields": ("is_active", "is_staff", "is_superuser", "phone_verified_at")}),
        ("Permissions", {"fields": ("groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("phone", "password1", "password2")}),)


@admin.register(LoginCode)
class LoginCodeAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Pending codes for the 'outbox' sender. Only staff with accounts.send_login_codes, audited."""

    list_display = ("__str__", "created_at", "expires_at", "used_at", "attempts")
    fields = ("phone", "pending_code", "created_at", "expires_at", "used_at", "attempts")
    readonly_fields = fields

    def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return request.user.has_perm("accounts.send_login_codes")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False

    @admin.display(description="Code to send")
    def pending_code(self, obj: LoginCode) -> str:
        if obj.outbox and obj.used_at is None and obj.expires_at > timezone.now():
            return str(obj.outbox["code"])
        return "—"

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: Any = None,  # noqa: ANN401
    ) -> HttpResponse:
        response = super().change_view(request, object_id, form_url, extra_context)
        if response.status_code == 200:
            record_audit(
                AuditAction.LOGIN_CODE_VIEWED,
                target=self.get_object(request, object_id),
                request=request,
            )
        return response
