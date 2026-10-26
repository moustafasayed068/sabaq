"""Rules from docs/engine-rules.md checked over many generated plans."""

import random
from datetime import timedelta

import pytest

from engine import Plan, PlanInput, generate
from engine.tests.test_differential import _case

RACE_EFFORT = {"تنشيط قبل السباق", "محاكاة السباق"}


def _plans(n: int = 600) -> list[Plan]:
    rng = random.Random(7)
    plans = [generate(PlanInput.from_dict(_case(rng)["input"])) for _ in range(n)]
    return [p for p in plans if p.weeks]


@pytest.fixture(scope="module")
def plans() -> list[Plan]:
    return _plans()


def test_every_plan_ends_with_race_day_and_rest_the_day_before(plans):
    for p in plans:
        last = p.weeks[-1]
        assert last.phase == "race"
        race_day = last.days[-1]
        assert race_day.date == p.input.race_date
        assert race_day.role == "race"
        before = last.days[-2]
        assert before.workout is None or before.workout.kind == "rest"


def test_one_race_effort_session_in_race_week(plans):
    for p in plans:
        titles = [d.workout.title for d in p.weeks[-1].days if d.workout]
        assert sum(t in RACE_EFFORT for t in titles) <= 1


def test_no_cutback_in_the_last_build_week(plans):
    for p in plans:
        build = [w for w in p.weeks if w.phase not in ("taper", "race")]
        if len(p.weeks) >= 7 and build:
            assert build[-1].phase == "peak"


def test_short_plans_have_a_race_week(make_input):
    for days_out in range(3, 15):
        inp = make_input("pyramids", 10)
        p = generate(
            PlanInput.from_dict(
                {
                    **inp.to_dict(),
                    "startDate": (inp.race_date - timedelta(days=days_out)).isoformat(),
                }
            )
        )
        assert p.weeks[-1].phase == "race", days_out
