import uuid

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.accounts.models import User, mask_phone

pytestmark = pytest.mark.django_db


def test_auth_user_model_is_custom():
    assert get_user_model() is User


def test_create_athlete_has_uuid_and_no_usable_password():
    user = User.objects.create_user("+201001234567")
    assert isinstance(user.pk, uuid.UUID)
    assert not user.has_usable_password()
    assert not user.is_staff
    assert user.created_at is not None


def test_create_staff_with_password_is_hashed_with_argon2(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.Argon2PasswordHasher"]
    user = User.objects.create_user("+201001234568", password="a-long-staff-password")
    assert user.password.startswith("argon2")
    assert user.check_password("a-long-staff-password")


@pytest.mark.parametrize("phone", ["01001234567", "+0123456789", "+20 100 123", "abc", "+2"])
def test_invalid_phone_rejected(phone):
    with pytest.raises(ValidationError):
        User.objects.create_user(phone)


def test_empty_phone_rejected():
    with pytest.raises(ValueError, match="phone"):
        User.objects.create_user("")


def test_phone_is_unique():
    User.objects.create_user("+201001234567")
    with pytest.raises((IntegrityError, ValidationError)):
        User.objects.create_user("+201001234567")


def test_superuser_needs_password_and_flags():
    with pytest.raises(ValueError, match="password"):
        User.objects.create_superuser("+201001234569")
    with pytest.raises(ValueError, match="superuser"):
        User.objects.create_superuser("+201001234569", password="x" * 12, is_staff=False)
    admin = User.objects.create_superuser("+201001234569", password="x" * 12)
    assert admin.is_staff
    assert admin.is_superuser


def test_str_masks_the_phone():
    user = User(phone="+201001234567")
    assert str(user) == "+2010******67"
    assert "1234" not in str(user)
    assert mask_phone("+2010") == "*****"
