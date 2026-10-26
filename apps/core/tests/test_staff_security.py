import io
import time

import pytest
from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.core.management import CommandError, call_command
from django.test import Client
from django_otp.oath import totp
from django_otp.plugins.otp_static.models import StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User
from apps.core import staff
from apps.core.models import AuditAction, AuditEvent

pytestmark = pytest.mark.django_db

ADMIN = f"/{settings.ADMIN_URL}"
PHONE = "+201005550000"
PASSWORD = "a-long-staff-password-123"


@pytest.fixture
def staff_user():
    return User.objects.create_superuser(PHONE, PASSWORD)


@pytest.fixture
def require_2fa(settings):
    settings.STAFF_REQUIRE_2FA = True


def setup_otp(phone: str = PHONE) -> str:
    out = io.StringIO()
    call_command("staff_otp_setup", phone, stdout=out)
    return out.getvalue()


def code_for(device: TOTPDevice) -> str:
    return f"{totp(device.bin_key, device.step, device.t0, device.digits, device.drift):06d}"


def login(client: Client, otp: str = "", device: str = "") -> int:
    data = {"username": PHONE, "password": PASSWORD, "otp_token": otp}
    if device:
        data["otp_device"] = device
    return client.post(f"{ADMIN}login/", data).status_code


def test_admin_needs_a_one_time_code(staff_user, require_2fa):
    c = Client()
    c.force_login(staff_user)  # password only
    assert c.get(ADMIN)["Location"].startswith(f"{ADMIN}login/")


def test_setup_prints_qr_and_backup_codes_and_is_audited(staff_user):
    text = setup_otp()
    assert "otpauth://totp/" in text
    assert "Sabaq" in text
    assert StaticToken.objects.filter(device__user=staff_user).count() == 10
    assert AuditEvent.objects.filter(action=AuditAction.STAFF_2FA_CHANGED).exists()
    # Running it again replaces the old device (lost phone).
    first = TOTPDevice.objects.get(user=staff_user).key
    setup_otp()
    assert TOTPDevice.objects.get(user=staff_user).key != first


def test_password_and_totp_code_open_the_admin(staff_user, require_2fa):
    setup_otp()
    device = TOTPDevice.objects.get(user=staff_user)
    c = Client()
    assert login(c, "000000", device.persistent_id) == 200  # wrong code: form again
    assert c.get(ADMIN).status_code == 302
    device.refresh_from_db()
    device.throttle_reset()  # a wrong code throttles the device for a moment
    c = Client()
    assert login(c, code_for(device), device.persistent_id) == 302
    assert c.get(ADMIN).status_code == 200


def test_backup_code_works_once(staff_user, require_2fa):
    text = setup_otp()
    code = text.strip().splitlines()[-1].strip()
    static = staff_user.staticdevice_set.get()
    c = Client()
    assert login(c, code, static.persistent_id) == 302
    assert c.get(ADMIN).status_code == 200
    assert login(Client(), code, static.persistent_id) == 200  # used up


def test_setup_refuses_non_staff_and_bad_numbers():
    User.objects.create_user("+201005550001")
    with pytest.raises(CommandError, match="No staff"):
        setup_otp("+201005550001")
    with pytest.raises(CommandError, match="country code"):
        setup_otp("12")


def test_admin_hidden_outside_allowed_networks(settings, staff_user):
    settings.ADMIN_ALLOWED_NETWORKS = ["203.0.113.0/24"]
    c = Client()
    c.force_login(staff_user)
    assert c.get(ADMIN, REMOTE_ADDR="198.51.100.9").status_code == 404
    assert c.get(f"{ADMIN}login/", REMOTE_ADDR="198.51.100.9").status_code == 404
    assert c.get(ADMIN, REMOTE_ADDR="203.0.113.7").status_code == 200
    assert c.get("/", REMOTE_ADDR="198.51.100.9").status_code == 200  # only the admin


@pytest.mark.parametrize(
    ("networks", "ip", "allowed"),
    [
        ([], None, True),
        (["10.0.0.1"], "10.0.0.1", True),
        (["10.0.0.0/8"], "10.9.9.9", True),
        (["10.0.0.0/8"], None, False),
        (["10.0.0.0/8"], "not-an-ip", False),
        (["2001:db8::/32"], "2001:db8::1", True),
    ],
)
def test_ip_allowed(settings, networks, ip, allowed):
    settings.ADMIN_ALLOWED_NETWORKS = networks
    assert staff.ip_allowed(ip) is allowed


def test_idle_staff_are_signed_out(settings, staff_user, monkeypatch):
    settings.STAFF_IDLE_TIMEOUT_S = 60
    c = Client()
    c.force_login(staff_user)
    assert c.get(ADMIN).status_code == 200
    now = time.time()
    monkeypatch.setattr(time, "time", lambda: now + 61)
    assert c.get(ADMIN).status_code == 302
    assert "_auth_user_id" not in c.session


def test_athletes_are_not_timed_out(settings, monkeypatch):
    settings.STAFF_IDLE_TIMEOUT_S = 1
    athlete = User.objects.create_user("+201005550002")
    c = Client()
    c.force_login(athlete)
    c.get("/")
    later = time.time() + 3600
    monkeypatch.setattr(time, "time", lambda: later)
    c.get("/")
    assert c.session.get("_auth_user_id") == str(athlete.pk)


def test_roles_are_created_with_exact_permissions():
    call_command("sync_roles", stdout=io.StringIO())
    finance = Group.objects.get(name="finance")
    codenames = set(finance.permissions.values_list("codename", flat=True))
    assert codenames == {"view_order", "view_payment", "refund_order", "view_plan"}
    # Extra permissions added by hand are removed on the next sync.
    finance.permissions.add(Permission.objects.get(codename="delete_user"))
    staff.sync_roles()
    assert "delete_user" not in set(finance.permissions.values_list("codename", flat=True))
    assert (
        not Group.objects.get(name="support")
        .permissions.filter(codename="view_health_answers")
        .exists()
    )


def test_every_role_permission_exists():
    staff.sync_roles()
    for name, perms in staff.ROLES.items():
        assert Group.objects.get(name=name).permissions.count() == len(perms), name


def test_staff_permission_changes_are_audited(staff_user):
    athlete = User.objects.create_user("+201005550003")
    group = Group.objects.create(name="tmp")
    before = AuditEvent.objects.filter(action=AuditAction.STAFF_PERMISSIONS_CHANGED).count()
    athlete.is_staff = True
    athlete.save()
    athlete.groups.add(group)
    athlete.user_permissions.add(Permission.objects.get(codename="view_user"))
    group.permissions.add(Permission.objects.get(codename="view_order"))
    group.user_set.remove(athlete)
    events = AuditEvent.objects.filter(action=AuditAction.STAFF_PERMISSIONS_CHANGED)
    changes = [e.metadata["change"] for e in events.order_by("created_at")][before:]
    assert changes == [
        "flags",
        "groups:post_add",
        "user_permissions:post_add",
        "group_permissions:post_add",
        "groups:post_remove",
    ]
    athlete.save()  # nothing changed: no event
    assert events.count() == before + 5


def test_new_staff_accounts_are_audited():
    User.objects.create_superuser("+201005550004", PASSWORD)
    event = AuditEvent.objects.filter(action=AuditAction.STAFF_PERMISSIONS_CHANGED).latest(
        "created_at"
    )
    assert event.metadata["change"] == "created"
