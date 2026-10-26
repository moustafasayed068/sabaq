from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.accounts.models import User


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
