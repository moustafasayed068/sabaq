from datetime import date
from decimal import Decimal

from django import template
from django.utils.html import format_html
from django.utils.safestring import SafeString

from apps.core.formatting import date_ar, days_left_ar, km_ar

register = template.Library()


@register.filter
def ar_date(value: date) -> str:
    return date_ar(value)


@register.filter
def ar_date_short(value: date) -> str:
    return date_ar(value, weekday=True, year=False)


@register.filter
def km(value: float | Decimal) -> SafeString:
    """Distance with its number LTR-isolated: <span class="num">21.1</span> كم."""
    number, unit = km_ar(float(value)).split(" ")
    return format_html('<span class="num">{}</span> {}', number, unit)


@register.filter
def num(value: object) -> SafeString:
    return format_html('<span class="num">{}</span>', value)


@register.filter
def days_left(value: int) -> SafeString:
    """باقي <span class="num">25</span> يوم, or بكرة / النهارده."""
    number, words = days_left_ar(value)
    if not number:
        return format_html("{}", words)
    return format_html('باقي <span class="num">{}</span> {}', number, words)


@register.filter
def hms(seconds: int | None) -> SafeString:
    """1:55:00 or 28:00, LTR-isolated."""
    if seconds is None:
        return format_html("")
    h, m, sec = seconds // 3600, seconds % 3600 // 60, seconds % 60
    text = f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"
    return format_html('<span class="num">{}</span>', text)


@register.filter
def weekdays(values: list[int]) -> str:
    """JS weekday numbers (0 = Sunday) as Arabic day names in Egyptian week order."""
    from apps.athletes.models import WEEKDAY_CHOICES  # noqa: PLC0415 - avoid core -> athletes at import

    return "، ".join(str(label) for v, label in WEEKDAY_CHOICES if v in values)
