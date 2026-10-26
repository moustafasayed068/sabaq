"""Phone numbers as people type them, to E.164."""

import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.core.forms import latin_digits

# Egyptian mobiles: 010, 011, 012, 015 then 8 digits.
_EG_LOCAL = re.compile(r"^01[0125]\d{8}$")
_E164 = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_phone(text: str) -> str:
    """'010 0123 4567', '+20 100 123 4567', '00201001234567' or Arabic digits -> '+201001234567'."""
    raw = re.sub(r"[\s\-().]", "", str(latin_digits(text) or ""))
    if raw.startswith("00"):
        raw = "+" + raw[2:]
    if _EG_LOCAL.match(raw):
        raw = "+2" + raw
    if raw.startswith("+20") and not _EG_LOCAL.match(raw[2:]):
        raise ValidationError(_("رقم الموبايل المصري لازم يبدأ بـ 010 أو 011 أو 012 أو 015."))
    if not _E164.match(raw):
        raise ValidationError(_("اكتب رقم موبايل صحيح، زي 01001234567."))
    return raw
