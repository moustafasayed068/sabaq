"""Public API of the accounts app: phone login with one-time codes."""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import LoginCode, User, mask_phone
from apps.core import ratelimit
from apps.core.services import AuditAction, record_audit

logger = logging.getLogger(__name__)

CODE_TTL = timedelta(minutes=10)
MAX_ATTEMPTS_PER_CODE = 5
CODES_PER_PHONE = (3, 15 * 60)  # 3 codes per 15 minutes
CODES_PER_IP = (10, 60 * 60)  # 10 codes per hour
FAILURES_PER_PHONE = (10, 60 * 60)  # lockout after 10 wrong codes in an hour


class Sender(StrEnum):
    CONSOLE = "console"  # development only: the code goes to the log
    OUTBOX = "outbox"  # staff read it in the admin and send it by hand (beta)
    DISABLED = "disabled"


class RequestOutcome(StrEnum):
    SENT = "sent"
    RATE_LIMITED = "rate_limited"
    DISABLED = "disabled"


class VerifyOutcome(StrEnum):
    OK = "ok"
    WRONG = "wrong"
    EXPIRED = "expired"
    LOCKED = "locked"


@dataclass(frozen=True)
class VerifyResult:
    outcome: VerifyOutcome
    user: User | None = None


def _hash(phone: str, code: str) -> str:
    key = settings.SECRET_KEY.encode()
    return hmac.new(key, f"{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def sender() -> Sender:
    return Sender(settings.LOGIN_CODE_SENDER)


def request_code(phone: str, ip: str | None) -> RequestOutcome:
    """Create a code for this phone and hand it to the configured channel."""
    if sender() is Sender.DISABLED:
        return RequestOutcome.DISABLED
    phone_ok = ratelimit.hit(
        f"code:phone:{phone}", limit=CODES_PER_PHONE[0], window_s=CODES_PER_PHONE[1]
    )
    ip_ok = ratelimit.hit(f"code:ip:{ip}", limit=CODES_PER_IP[0], window_s=CODES_PER_IP[1])
    if not (phone_ok and ip_ok):
        return RequestOutcome.RATE_LIMITED
    code = f"{secrets.randbelow(10**6):06d}"
    with transaction.atomic():
        # Only the newest code works.
        LoginCode.objects.filter(phone=phone, used_at__isnull=True).update(
            used_at=timezone.now(), outbox=None
        )
        LoginCode.objects.create(
            phone=phone,
            code_hash=_hash(phone, code),
            expires_at=timezone.now() + CODE_TTL,
            # The django-stubs plugin types EncryptedJSONField as text; it holds JSON.
            outbox={"code": code} if sender() is Sender.OUTBOX else None,  # type: ignore[misc]
        )
    if sender() is Sender.CONSOLE:
        logger.warning("DEV login code for %s: %s", mask_phone(phone), code)
    return RequestOutcome.SENT


def verify_code(phone: str, code: str, ip: str | None) -> VerifyResult:
    if ratelimit.is_limited(f"verify:phone:{phone}", limit=FAILURES_PER_PHONE[0]):
        return VerifyResult(VerifyOutcome.LOCKED)
    with transaction.atomic():
        login = (
            LoginCode.objects.select_for_update()
            .filter(phone=phone, used_at__isnull=True)
            .order_by("-created_at")
            .first()
        )
        if login is None or login.expires_at <= timezone.now():
            return VerifyResult(VerifyOutcome.EXPIRED)
        if login.attempts >= MAX_ATTEMPTS_PER_CODE:
            return VerifyResult(VerifyOutcome.LOCKED)
        if not hmac.compare_digest(login.code_hash, _hash(phone, code.strip())):
            login.attempts += 1
            login.save(update_fields=["attempts"])
            ratelimit.hit(
                f"verify:phone:{phone}", limit=FAILURES_PER_PHONE[0], window_s=FAILURES_PER_PHONE[1]
            )
            record_audit(AuditAction.LOGIN_CODE_FAILED, metadata={"attempts": login.attempts})
            locked = login.attempts >= MAX_ATTEMPTS_PER_CODE
            return VerifyResult(VerifyOutcome.LOCKED if locked else VerifyOutcome.WRONG)
        login.used_at = timezone.now()
        login.outbox = None
        login.save(update_fields=["used_at", "outbox"])
        user = User.objects.filter(phone=phone).first() or User.objects.create_user(phone)
        user.phone_verified_at = user.phone_verified_at or timezone.now()
        user.save()
    ratelimit.reset(f"verify:phone:{phone}")
    return VerifyResult(VerifyOutcome.OK, user)
