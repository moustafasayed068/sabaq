from dataclasses import replace
from datetime import date

import pytest

from engine import Env, PlanInput, race_by_id


def race_input(race_id: str, km: float | None = None, **overrides) -> PlanInput:
    """The `base` + `race()` helpers from reference/engine-js/test.js."""
    race = race_by_id(race_id)
    base = PlanInput(
        start_date=date(2026, 10, 27),
        race_date=race.date_for(km),
        race_name=race.name,
        race_type=race.type,
        race_id=race.id,
        distance_km=km if km is not None else 21.1,
        age=28,
        sex="m",
        weekly_km=20,
        longest_km=10,
        runs_per_week=3,
        recent_km=5,
        recent_time="28:00",
        goal="finish",
        days=(6, 1, 3, 5),
        injury="none",
        pain="none",
        env=Env("outdoor", True, ()),
    )
    return replace(base, **overrides)


@pytest.fixture
def make_input():
    return race_input
