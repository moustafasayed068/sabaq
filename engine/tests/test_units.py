import math
from dataclasses import replace
from datetime import date

import pytest

from engine import ENGINE_VERSION, PlanInput, generate, race_by_id
from engine.data import TARGET
from engine.jsmath import fmt_num, js_number, js_plus, js_round, js_sum, num_or, round1, round_half
from engine.layout import layout
from engine.paces import fmt_pace, fmt_time, parse_duration
from engine.types import CheckInFeedback, Env, Flags, HealthAnswers


@pytest.mark.parametrize(
    ("x", "expected"), [(0.5, 1), (1.5, 2), (2.5, 3), (-0.5, 0), (-1.5, -1), (2.4999, 2)]
)
def test_js_round_rounds_halves_up(x, expected):
    assert js_round(x) == expected
    assert isinstance(js_round(x), int)


def test_round_helpers():
    assert round1(2.25) == 2.3
    assert round_half(2.25) == 2.5
    assert round_half(2.2) == 2


@pytest.mark.parametrize(
    ("x", "text"), [(3, "3"), (3.0, "3"), (2.5, "2.5"), (0.1 + 0.2, "0.30000000000000004")]
)
def test_fmt_num_matches_js_string(x, text):
    assert fmt_num(x) == text


def test_fmt_num_rejects_bool():
    with pytest.raises(TypeError):
        fmt_num(True)


@pytest.mark.parametrize(
    ("text", "expected"),
    [("", 0), ("  ", 0), ("12", 12), (" 1.5 ", 1.5), ("1e3", 1000), ("0x10", 16), ("0b11", 3),
     ("Infinity", math.inf), ("-Infinity", -math.inf), ("+5", 5)],
)  # fmt: skip
def test_js_number(text, expected):
    assert js_number(text) == expected


@pytest.mark.parametrize("text", ["abc", "1_0", "nan", "inf", "0xZZ", "0o9"])
def test_js_number_nan(text):
    assert math.isnan(js_number(text))


def test_js_plus_and_num_or():
    assert js_plus(True) == 1
    assert js_plus(False) == 0
    assert math.isnan(js_plus(None))
    assert math.isnan(js_plus([1]))
    assert num_or("0", 30) == 30
    assert num_or("abc", 30) == 30
    assert num_or("25", 30) == 25


def test_js_sum_is_left_to_right():
    values = [0.1] * 10
    assert js_sum(values) == 0.9999999999999999  # what Array.reduce gives


def test_fmt_pace_and_time():
    assert fmt_pace(329.5) == "5:30"
    assert fmt_time(3725) == "1:02:05"
    assert fmt_time(1680) == "28:00"


@pytest.mark.parametrize(
    ("text", "km", "expected"),
    [("1.55", 21.1, 6900), ("1,55", 21.1, 6900), ("1:55:00", 21.1, 6900), ("28", 0, None),
     (None, 5, None), ("  ", 5, None), ("1:2:3:4", 5, None), ("-28", 5, None), ("28", math.nan, None)],
)  # fmt: skip
def test_parse_duration_edges(text, km, expected):
    assert parse_duration(text, km) == expected


def test_layout_long_day_choice_and_second_quality_gap():
    assert layout([6, 1, 3], 1)[6] == "long"
    assert layout([0, 2, 4], 1)[0] == "long"
    assert layout([1, 3, 4], 1)[4] == "long"
    # 5 consecutive days: the second hard day has no 1-day gap, so it is not placed.
    roles = layout([0, 1, 2, 3, 4], 2)
    assert list(roles.values()).count("q2") == 0
    assert layout([3], 2) == {3: "long"}


def test_race_lookup():
    pyramids = race_by_id("pyramids")
    assert pyramids.date_for(5) == date(2026, 12, 11)
    assert pyramids.date_for(21.1) == date(2026, 12, 12)
    assert pyramids.date_for(None) == date(2026, 12, 12)
    with pytest.raises(KeyError):
        race_by_id("nope")
    assert set(TARGET) == {5, 10, 21.1, 42.2}
    assert ENGINE_VERSION


def test_input_round_trip(make_input):
    inp = make_input("pyramids", 21.1, flags=Flags(continuing=True, rest_until=date(2026, 11, 1)))
    assert PlanInput.from_dict(inp.to_dict()) == inp


def test_from_dict_applies_reference_defaults():
    inp = PlanInput.from_dict(
        {"startDate": "2026-10-27", "raceDate": "2026-12-12", "raceName": "X", "age": "0",
         "weeklyKm": -5, "weightKg": "", "env": {"where": "track"}}
    )  # fmt: skip
    assert inp.age == 30
    assert inp.weekly_km == 0
    assert inp.weight_kg is None
    assert inp.distance_km == 21.1
    assert inp.days == (6, 1, 3, 5)
    assert inp.env == Env("track", True, ())
    assert "goalTime" not in inp.to_dict()
    assert inp.to_dict()["weightKg"] is None


def test_from_dict_requires_dates():
    with pytest.raises(ValueError, match="startDate"):
        PlanInput.from_dict({"raceDate": "2026-12-12"})


def test_health_answers_ignore_unknown_ids():
    assert HealthAnswers.from_dict({"heart": True, "bogus": True}).yes() == ["heart"]


def test_feedback_from_dict_defaults():
    fb = CheckInFeedback.from_dict({"done": "x"})
    assert fb.done == 0
    assert fb.pain is None
    assert fb.new_time is None


def test_typed_input_is_normalised_like_the_reference(make_input):
    plan = generate(make_input("pyramids", 21.1, age=0, distance_km=0, weight_kg=0))
    assert plan.input.age == 30
    assert plan.input.distance_km == 21.1
    assert plan.input.weight_kg is None


@pytest.mark.parametrize(("field", "value", "kind"), [("age", 16, "age"), ("pain", "now", "pain")])
def test_blocks_before_any_plan(make_input, field, value, kind):
    plan = generate(make_input("pyramids", 10, **{field: value}))
    assert plan.status == "blocked"
    assert plan.block_kind == kind
    assert plan.weeks == []


def test_race_too_close_is_blocked(make_input):
    plan = generate(make_input("pyramids", 10, start_date=date(2026, 12, 10)))
    assert plan.block_kind == "date"


def test_race_far_away_starts_sixteen_weeks_out(make_input):
    plan = generate(make_input("luxor", 21.1, start_date=date(2026, 6, 1)))
    assert len(plan.weeks) == 16
    assert any("لسه بعيد" in m for m in plan.messages)


def test_unsupported_distance_is_an_error(make_input):
    with pytest.raises(ValueError, match="Unsupported"):
        generate(make_input("pyramids", 15))


def test_goal_too_fast_uses_realistic_time(make_input):
    plan = generate(make_input("pyramids", 21.1, goal="time", goal_time="1:20:00"))
    assert plan.goal_verdict is not None
    assert not plan.goal_verdict.ok


def test_nonsense_goal_warns(make_input):
    plan = generate(make_input("pyramids", 21.1, goal="time", goal_time="9"))
    assert any("الهدف" in w for w in plan.warnings)


def test_hyrox_without_long_runs_is_risky(make_input):
    plan = generate(make_input("hyrox-cairo", longest_km=3, recent_time=None))
    assert plan.status == "risky"
    assert plan.to_dict()["peakLong"] is None
    assert "peakWeekly" not in plan.to_dict()


def test_week_days_cover_the_plan_window(make_input):
    plan = generate(make_input("pyramids", 21.1))
    dates = [d.date for w in plan.weeks for d in w.days if d.role != "off"]
    assert dates[0] == plan.input.start_date
    assert dates[-1] == plan.input.race_date
    assert dates == sorted(dates)
    assert replace(plan.input) == plan.input
