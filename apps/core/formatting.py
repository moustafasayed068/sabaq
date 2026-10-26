"""One place to format dates and numbers for the UI: Arabic words, Western digits."""

from datetime import date

MONTHS_AR = (
    "يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
    "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر",
)  # fmt: skip
WEEKDAYS_AR = ("الاتنين", "التلات", "الأربع", "الخميس", "الجمعة", "السبت", "الأحد")


def date_ar(d: date, *, weekday: bool = False, year: bool = True) -> str:
    """12 ديسمبر 2026 (or الجمعة 12 ديسمبر)."""
    text = f"{d.day} {MONTHS_AR[d.month - 1]}"
    if year:
        text += f" {d.year}"
    if weekday:
        text = f"{WEEKDAYS_AR[d.weekday()]} {text}"
    return text


def km_ar(km: float) -> str:
    """21.1 كم, 5 كم (no trailing .0)."""
    text = f"{km:.1f}".removesuffix(".0")
    return f"{text} كم"


def days_until(today: date, d: date) -> int:
    return (d - today).days


def days_left_ar(n: int) -> tuple[str, str]:
    """(number, words) for a countdown in Egyptian Arabic: النهارده, بكرة, يومين, 3 أيام, 11 يوم."""
    if n <= 0:
        return ("", "النهارده")
    if n == 1:
        return ("", "بكرة")
    if n == 2:
        return ("", "باقي يومين")
    if n <= 10:
        return (str(n), "أيام")
    return (str(n), "يوم")
