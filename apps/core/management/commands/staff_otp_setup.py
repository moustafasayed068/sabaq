"""Give a staff account its authenticator app and backup codes. Run on the server:

    docker compose exec web python manage.py staff_otp_setup +201001234567

It prints a QR code (scan it with Google Authenticator, Microsoft Authenticator, 1Password...)
and 10 one-time backup codes. Running it again replaces both, so a lost phone is fixed here.
"""

import io
from typing import Any

import qrcode
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.accounts.models import User
from apps.accounts.phone import normalize_phone
from apps.core.models import AuditAction
from apps.core.services import record_audit

BACKUP_CODES = 10


class Command(BaseCommand):
    help = "Create (or replace) a staff account's TOTP device and backup codes."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("phone")

    def handle(self, *args: Any, **options: Any) -> None:  # noqa: ANN401
        try:
            phone = normalize_phone(options["phone"])
        except ValidationError as exc:
            raise CommandError("Write the phone number with the country code.") from exc
        user = User.objects.filter(phone=phone).first()
        if user is None or not user.is_staff:
            raise CommandError("No staff account with this phone number.")
        with transaction.atomic():
            TOTPDevice.objects.filter(user=user).delete()
            StaticDevice.objects.filter(user=user).delete()
            totp = TOTPDevice.objects.create(user=user, name="authenticator", confirmed=True)
            static = StaticDevice.objects.create(user=user, name="backup codes", confirmed=True)
            codes = [StaticToken.random_token() for _ in range(BACKUP_CODES)]
            for code in codes:
                static.token_set.create(token=code)
            record_audit(
                AuditAction.STAFF_2FA_CHANGED, target=user, metadata={"change": "replaced"}
            )
        qr = qrcode.QRCode(border=1)
        qr.add_data(totp.config_url)
        out = io.StringIO()
        qr.print_ascii(out=out, invert=True)
        self.stdout.write(out.getvalue())
        self.stdout.write("Scan the code above with an authenticator app, or enter this URL:")
        self.stdout.write(totp.config_url)
        self.stdout.write("\nBackup codes (each works once; keep them off the phone):")
        for code in codes:
            self.stdout.write(f"  {code}")
