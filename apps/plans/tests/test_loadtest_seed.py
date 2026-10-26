import io

import pytest
from django.core.management import CommandError, call_command
from django.test import Client

from apps.accounts.models import User
from apps.plans.models import Plan

pytestmark = pytest.mark.django_db


def test_seed_makes_signed_in_athletes_with_plans_and_cleanup_removes_them(tmp_path, settings):
    out = tmp_path / "s.txt"
    call_command("loadtest_seed", "--athletes", "2", "--out", str(out), stdout=io.StringIO())
    lines = out.read_text().split()
    assert len(lines) == 4
    assert Plan.objects.filter(user__phone__startswith="+2010999").count() == 2
    c = Client()
    c.cookies[settings.SESSION_COOKIE_NAME] = lines[0]
    assert c.get("/plan/").status_code == 200
    assert c.get(f"/plan/day/{lines[1]}/").status_code == 200
    staff = User.objects.create_user("+201099900099", "pw", is_staff=True)
    call_command("loadtest_seed", "--cleanup", stdout=io.StringIO())
    assert not User.objects.filter(phone__startswith="+2010999", is_staff=False).exists()
    assert User.objects.filter(pk=staff.pk).exists()  # never staff


def test_seed_refuses_production_settings(settings):
    settings.SETTINGS_MODULE = "sabaq.settings.prod"
    with pytest.raises(CommandError, match="production"):
        call_command("loadtest_seed", "--athletes", "1")


def test_seed_needs_a_known_race():
    with pytest.raises(CommandError, match="No race"):
        call_command("loadtest_seed", "--athletes", "1", "--race", "nope")
