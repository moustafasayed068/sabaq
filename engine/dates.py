"""Dates as the JS reference sees them: plain calendar days, Egyptian week Saturday to Friday."""

from datetime import date, timedelta

# Indexed like JavaScript getUTCDay(): 0 = Sunday.
DAY_NAMES = ("الأحد", "الاتنين", "التلات", "الأربع", "الخميس", "الجمعة", "السبت")


def add_days(d: date, n: int) -> date:
    return d + timedelta(days=n)


def diff_days(a: date, b: date) -> int:
    return (b - a).days


def js_weekday(d: date) -> int:
    """0 = Sunday ... 6 = Saturday (JavaScript getUTCDay)."""
    return (d.weekday() + 1) % 7


def eg_pos(js_wd: int) -> int:
    """Position 0..6 in the Egyptian week (Saturday = 0, Friday = 6)."""
    return (js_wd + 1) % 7


def day_name(d: date) -> str:
    return DAY_NAMES[js_weekday(d)]
