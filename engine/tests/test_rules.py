"""Rules from docs/engine-rules.md checked over many generated plans."""

import itertools
import random
from datetime import timedelta

import pytest

from engine import Plan, PlanInput, generate, js_round
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


def _full_build_weeks(p: Plan):
    return [
        w for w in p.weeks if w.phase in ("build", "peak") and all(d.role != "off" for d in w.days)
    ]


def test_start_week_is_at_most_10_percent_above_current(plans):
    for p in plans:
        if p.input.race_type != "run" or p.weeks[0].phase not in ("build", "peak"):
            continue
        run_walk = any(d.workout and d.workout.title == "جري ومشي" for w in p.weeks for d in w.days)
        if not run_walk and not p.input.flags.progress_now:
            assert p.weeks[0].target_km <= js_round(max(p.input.weekly_km * 1.1, p.input.weekly_km))


def test_never_fewer_runs_than_the_athlete_does_now(plans):
    for p in plans:
        if p.input.race_type != "run" or p.input.flags.rest_until:
            continue
        min_runs = min(len(p.input.days), max(2, p.input.runs_per_week))
        for w in _full_build_weeks(p):
            runs = [d for d in w.days if d.workout and d.workout.km > 0]
            assert len(runs) >= min_runs
            assert all(d.workout.km >= 2 for d in runs)


def test_cutback_long_run_is_shorter_than_the_week_before(plans):
    for p in plans:
        longs = [
            (
                w.phase,
                next(
                    (d.workout.km for d in w.days if d.workout and d.workout.kind == "long"), None
                ),
            )
            for w in p.weeks
        ]
        for (_, before), (phase, km) in itertools.pairwise(longs):
            if phase == "cutback" and before and km:
                assert km <= before
