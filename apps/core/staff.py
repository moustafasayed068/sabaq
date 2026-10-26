"""Staff security (docs/security.md): the admin needs a password plus a one-time code, can be
limited to known networks, signs staff out after idle time, and staff permissions come from
roles. Every change to a staff account's permissions is audited."""

from __future__ import annotations

import ipaddress
import time
from collections.abc import Callable, Iterable
from typing import Any

from django.conf import settings
from django.contrib.admin import AdminSite
from django.contrib.auth import logout
from django.contrib.auth.models import Group, Permission
from django.http import HttpRequest, HttpResponse, HttpResponseNotFound
from django_otp.admin import OTPAdminSite

from apps.core.request_context import client_ip

# ---------------------------------------------------------------- admin site with 2FA


class SabaqAdminSite(OTPAdminSite):  # type: ignore[misc]  # django-otp has no type hints
    """Staff must be verified by a one-time code (TOTP app or a backup code)."""

    site_header = "Sabaq staff"
    site_title = "Sabaq staff"

    def has_permission(self, request: HttpRequest) -> bool:
        if not getattr(settings, "STAFF_REQUIRE_2FA", True):
            return AdminSite.has_permission(self, request)
        return bool(super().has_permission(request))


# ---------------------------------------------------------------- middleware


def _networks() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    return [ipaddress.ip_network(n, strict=False) for n in settings.ADMIN_ALLOWED_NETWORKS]


def ip_allowed(ip: str | None) -> bool:
    networks = _networks()
    if not networks:
        return True
    if not ip:
        return False
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(address in n for n in networks)


IDLE_KEY = "staff_last_seen"


class StaffAccessMiddleware:
    """Hides the admin outside ADMIN_ALLOWED_NETWORKS (404, as if it did not exist) and signs
    staff out after STAFF_IDLE_TIMEOUT_S without a request."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self.prefix = "/" + settings.ADMIN_URL.lstrip("/")

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.path.startswith(self.prefix) and not ip_allowed(client_ip(request)):
            return HttpResponseNotFound()
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and user.is_staff:
            now = int(time.time())
            last = request.session.get(IDLE_KEY)
            if isinstance(last, int) and now - last > settings.STAFF_IDLE_TIMEOUT_S:
                logout(request)
            else:
                request.session[IDLE_KEY] = now
        return self.get_response(request)


# ---------------------------------------------------------------- roles

# Least privilege. "owner" is a superuser account, not a group.
ROLES: dict[str, tuple[str, ...]] = {
    "support": (
        "accounts.view_user",
        "accounts.view_logincode",
        "accounts.send_login_codes",
        "plans.view_plan",
        "athletes.view_questionnaire",
        "payments.view_order",
        "races.view_race",
        "races.view_racedistance",
    ),
    "coach_reviewer": (
        "plans.view_plan",
        "plans.view_checkin",
        "plans.view_daylog",
        "athletes.view_healthscreen",
        "athletes.view_health_answers",
        "races.view_race",
    ),
    "finance": (
        "payments.view_order",
        "payments.view_payment",
        "payments.refund_order",
        "plans.view_plan",
    ),
    "health_viewer": (
        "athletes.view_healthscreen",
        "athletes.view_health_answers",
        "plans.view_checkin",
        "plans.view_daylog",
    ),
    "race_editor": (
        "races.view_race",
        "races.add_race",
        "races.change_race",
        "races.view_racedistance",
        "races.add_racedistance",
        "races.change_racedistance",
        "races.delete_racedistance",
    ),
}


def _permissions(names: Iterable[str]) -> list[Permission]:
    found = []
    for name in names:
        app_label, codename = name.split(".", 1)
        perm = Permission.objects.filter(
            content_type__app_label=app_label, codename=codename
        ).first()
        if perm is not None:  # created later in the same migrate run; the next call adds it
            found.append(perm)
    return found


def sync_roles() -> dict[str, int]:
    """Create the role groups and set their permissions to exactly ROLES. Idempotent."""
    counts = {}
    for name, perms in ROLES.items():
        group, _ = Group.objects.get_or_create(name=name)
        wanted = _permissions(perms)
        if set(group.permissions.all()) != set(wanted):
            group.permissions.set(wanted)
        counts[name] = len(wanted)
    return counts


def sync_roles_after_migrate(**kwargs: Any) -> None:  # noqa: ANN401
    sync_roles()
