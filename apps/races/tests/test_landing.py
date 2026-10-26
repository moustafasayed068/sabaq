from datetime import date

import pytest
from django.utils import timezone

from apps.core.formatting import date_ar, days_left_ar, days_until, km_ar
from apps.races.models import Race

pytestmark = pytest.mark.django_db


@pytest.fixture
def today(monkeypatch):
    monkeypatch.setattr(timezone, "localdate", lambda: date(2026, 11, 20))
    return date(2026, 11, 20)


def test_landing_lists_upcoming_races_only(client, today, django_assert_max_num_queries):
    with django_assert_max_num_queries(2):
        response = client.get("/")
    html = response.content.decode()
    assert response.status_code == 200
    assert '<html lang="ar" dir="rtl">' in html
    assert "اختار سباقك" in html
    assert "HYROX Cairo" not in html  # 14 Nov: already past
    assert "نص ماراثون الجونة" in html
    assert 'باقي <span class="num">8</span> أيام' in html  # Sharm, 28 Nov
    assert '<span class="num">21.1</span> كم' in html
    assert '<span class="num">349</span> جنيه' in html
    assert html.index("نص ماراثون الجونة") < html.index("ماراثون شرم الشيخ")


def test_landing_without_races_says_so(client, today):
    Race.objects.update(is_active=False)
    assert "مفيش سباقات جاية" in client.get("/").content.decode()


def test_landing_is_get_only(client):
    assert client.post("/").status_code == 405


def test_date_and_number_formatting():
    assert date_ar(date(2026, 12, 12)) == "12 ديسمبر 2026"
    assert date_ar(date(2026, 12, 11), weekday=True, year=False) == "الجمعة 11 ديسمبر"
    assert km_ar(21.1) == "21.1 كم"
    assert km_ar(5.0) == "5 كم"
    assert days_until(date(2026, 11, 20), date(2026, 11, 21)) == 1


@pytest.mark.parametrize(
    ("n", "expected"),
    [(0, ("", "النهارده")), (1, ("", "بكرة")), (2, ("", "باقي يومين")), (3, ("3", "أيام")),
     (10, ("10", "أيام")), (11, ("11", "يوم"))],
)  # fmt: skip
def test_days_left_wording(n, expected):
    assert days_left_ar(n) == expected
