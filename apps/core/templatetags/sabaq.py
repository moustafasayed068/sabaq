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
