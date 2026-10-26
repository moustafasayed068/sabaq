"""Custom user, phone-first, from the very first migration."""

from __future__ import annotations

import uuid
from typing import Any, ClassVar

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.crypto import EncryptedJSONField

# E.164: "+" then country code and number, 8 to 15 digits in total.
phone_validator = RegexValidator(
    regex=r"^\+[1-9]\d{7,14}$",
    message=_("اكتب رقم الموبايل بالكود الدولي، زي +201001234567."),
)


def mask_phone(phone: str) -> str:
    """Keep only enough of the number to recognise it; safe for admin lists, never for logs."""
    if len(phone) <= 6:
        return "*" * len(phone)
    return f"{phone[:5]}{'*' * (len(phone) - 7)}{phone[-2:]}"


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def create_user(self, phone: str, password: str | None = None, **extra: Any) -> User:  # noqa: ANN401
        if not phone:
            raise ValueError("A phone number is required.")
        user = self.model(phone=phone.strip(), **extra)
        user.full_clean(exclude=["password"])
        if password:
            user.set_password(password)
        else:
            # Athletes log in with one-time codes, never a password.
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, phone: str, password: str | None = None, **extra: Any) -> User:  # noqa: ANN401
        if not password:
            raise ValueError("Staff accounts need a password.")
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if not extra["is_staff"] or not extra["is_superuser"]:
            raise ValueError("A superuser must have is_staff and is_superuser set.")
        return self.create_user(phone, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone = models.CharField(
        _("رقم الموبايل"), max_length=16, unique=True, validators=[phone_validator]
    )
    phone_verified_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects: ClassVar[UserManager] = UserManager()

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    class Meta:
        verbose_name = _("مستخدم")
        verbose_name_plural = _("مستخدمين")

    def __str__(self) -> str:
        return mask_phone(self.phone)


class LoginCode(models.Model):
    """A one-time login code: short-lived, single use, hashed at rest, attempts counted."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone = models.CharField(max_length=16, db_index=True)
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(null=True, blank=True)
    # Only for the "outbox" sender: staff read it in the admin and send it by hand.
    # Encrypted, and wiped as soon as the code is used.
    outbox = EncryptedJSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]
        permissions = (("send_login_codes", "Can read pending login codes to send them by hand"),)

    def __str__(self) -> str:
        return f"Login code for {mask_phone(self.phone)}"
