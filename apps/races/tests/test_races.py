from datetime import date
from decimal import Decimal

import pytest
from django.conf import settings
from django.core.exceptions import ValidationError

from apps.accounts.models import User
from apps.races.models import Race, RaceDistance
from apps.races.services import UnknownDistanceError, engine_race, race_by_slug, upcoming_races
from engine import RACES, PlanInput, generate

pytestmark = pytest.mark.django_db


def test_seeded_races_match_the_engine_reference():
    for ref in RACES:
        race = Race.objects.get(slug=ref.id)
        assert race.name == ref.name
        assert race.kind == ref.type
        assert race.date == ref.date
        km = sorted(float(d.distance_km) for d in race.distances.all())
        assert km == sorted(ref.distances)
        for d in race.distances.all():
            assert engine_race(race, d.distance_km).race_date == ref.date_for(float(d.distance_km))


def test_upcoming_races_are_ordered_and_skip_past_and_inactive(django_assert_num_queries):
    Race.objects.filter(slug="luxor").update(is_active=False)
    with django_assert_num_queries(2):  # races + distances, never one query per race
        races = list(upcoming_races(date(2026, 11, 22)))
        for r in races:
            list(r.distances.all())
    assert [r.slug for r in races] == ["hyrox-dubai", "sharm", "pyramids"]


def test_race_by_slug():
    assert race_by_slug("pyramids") is not None
    assert race_by_slug("nope") is None
    Race.objects.filter(slug="gouna").update(is_active=False)
    assert race_by_slug("gouna") is None


def test_engine_race_feeds_the_engine():
    race = Race.objects.get(slug="pyramids")
    er = engine_race(race, Decimal("21.1"))
    assert (er.race_id, er.race_type, er.race_date, er.distance_km) == (
        "pyramids", "run", date(2026, 12, 12), 21.1,
    )  # fmt: skip
    assert engine_race(race, Decimal("5")).race_date == date(2026, 12, 11)
    plan = generate(
        PlanInput(
            start_date=date(2026, 10, 27), race_date=er.race_date, race_name=er.race_name,
            race_type="run", distance_km=er.distance_km or 0, race_id=er.race_id,
            weekly_km=20, longest_km=10, runs_per_week=3,
        )
    )  # fmt: skip
    assert plan.weeks[-1].days[-1].date == er.race_date


def test_engine_race_hyrox_and_unknown_distance():
    hyrox = engine_race(Race.objects.get(slug="hyrox-cairo"))
    assert hyrox.distance_km is None
    assert hyrox.race_type == "hyrox"
    with pytest.raises(UnknownDistanceError):
        engine_race(Race.objects.get(slug="gouna"), Decimal("42.2"))


def test_hyrox_races_have_no_distances():
    distance = RaceDistance(race=Race.objects.get(slug="hyrox-cairo"), distance_km=Decimal("5"))
    with pytest.raises(ValidationError):
        distance.full_clean()


def test_str():
    race = Race.objects.get(slug="pyramids")
    assert str(race) == "نص ماراثون الأهرامات (2026-12-12)"
    assert str(race.distances.get(distance_km=Decimal("10"))) == "نص ماراثون الأهرامات: 10.0 كم"


def test_staff_can_add_a_race_in_admin(client):
    admin = User.objects.create_superuser("+201001234500", password="a-long-staff-password")
    client.force_login(admin)
    url = f"/{settings.ADMIN_URL}races/race/add/"
    assert client.get(url).status_code == 200
    response = client.post(url, {
        "slug": "cairo-marathon", "name": "ماراثون القاهرة", "kind": "run", "date": "2027-02-19",
        "city": "القاهرة", "note": "", "is_active": "on",
        "distances-TOTAL_FORMS": "1", "distances-INITIAL_FORMS": "0",
        "distances-0-distance_km": "42.2", "distances-0-date": "",
    })  # fmt: skip
    assert response.status_code == 302
    assert Race.objects.get(slug="cairo-marathon").distances.get().distance_km == Decimal("42.2")
