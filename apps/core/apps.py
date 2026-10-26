from django.apps import AppConfig
from django.db.models.signals import post_migrate


class CoreConfig(AppConfig):
    name = "apps.core"
    label = "core"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from django.contrib import admin  # noqa: PLC0415 - apps must be loaded first

        from apps.core import signals, staff  # noqa: PLC0415

        # The default admin site needs 2FA (django-otp); every app's admin.py keeps working.
        admin.site.__class__ = staff.SabaqAdminSite
        signals.connect()
        post_migrate.connect(staff.sync_roles_after_migrate, dispatch_uid="sync_roles")
