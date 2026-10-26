"""reference/engine-js/test.js, ported one section at a time."""

import json

from engine import (
    CheckInFeedback,
    Env,
    HealthAnswers,
    Plan,
    check_in,
    fmt_time,
    generate,
    parse_duration,
    predict_time,
    vdot_from,
)


def _text(plan: Plan) -> str:
    return json.dumps([w.to_dict() for w in plan.weeks], ensure_ascii=False)


def check_run_plan(p: Plan) -> None:
    prev_km = None
    for i, wk in enumerate(p.weeks):
        days = [d for d in wk.days if d.role != "off"]
        longs = [d for d in days if d.workout and d.workout.kind == "long"]
        assert len(longs) <= 1, f"w{i}: more than one long run"
        quality = [d for d in days if d.workout and d.workout.kind == "quality"]
        assert len(quality) <= 2, f"w{i}: {len(quality)} quality sessions"
        if wk.phase != "race" and prev_km and wk.days[0].role != "off":
            assert wk.km <= prev_km * 1.2 + 3, f"w{i}: jump {prev_km} -> {wk.km}"
        if all(d.role != "off" for d in wk.days) and wk.phase not in ("race", "cutback"):
            prev_km = wk.km
    last = p.weeks[-1]
    race_day = next(d for d in last.days if d.role == "race")
    assert race_day.date == p.input.race_date
    before = last.days[last.days.index(race_day) - 1]
    assert before.workout is None or before.workout.kind == "rest", "rest the day before"


def test_1_intermediate_half_four_days(make_input):
    p = generate(make_input("pyramids", 21.1))
    check_run_plan(p)
    assert p.status != "blocked"


def test_2_beginner_marathon_in_four_weeks_is_blocked_with_alternatives(make_input):
    p = generate(make_input("sharm", 42.2, weekly_km=5, longest_km=3, runs_per_week=1))
    assert p.status == "blocked"
    assert p.block_kind == "feasibility"
    assert p.alternatives
    assert p.alternatives[-1].kind == "later"


def test_3_beginner_5k_run_walk_treadmill_no_time(make_input):
    p = generate(
        make_input(
            "gouna", 5, weekly_km=4, longest_km=2, runs_per_week=1, recent_time="",
            env=Env("treadmill", False, ()),
        )
    )  # fmt: skip
    check_run_plan(p)
    assert any(d.workout and "جري ومشي" in d.workout.title for d in p.weeks[0].days)


def test_4_health_yes_blocks_until_doctor_clears(make_input):
    health = HealthAnswers(chestActive=True)
    p = generate(make_input("pyramids", 10, health=health))
    assert p.status == "blocked"
    assert p.block_kind == "health"
    p = generate(make_input("pyramids", 10, health=health, doctor_cleared=True))
    assert p.status != "blocked"


def test_5_outdoor_without_gps_uses_minutes_and_track_uses_laps(make_input):
    p = generate(make_input("pyramids", 10, env=Env("outdoor", False, ())))
    assert "دقيقة بسرعة" in _text(p)
    p = generate(make_input("pyramids", 10, env=Env("track", True, ())))
    assert "لفة" in _text(p)


def test_6_hyrox_home_kit_gets_substitutes(make_input):
    p = generate(
        make_input(
            "hyrox-cairo", sex="f", days=(6, 0, 2, 4), env=Env("outdoor", True, ("dumbbells",))
        )
    )
    txt = _text(p)
    assert "بدل Sled Push" in txt
    assert "بدل Wall Balls" in txt
    assert "2 × 16" in txt
    assert p.warnings


def test_7_long_marathon_plan_has_cutbacks_and_two_week_taper(make_input):
    p = generate(
        make_input(
            "luxor", 42.2, weekly_km=50, longest_km=22, runs_per_week=5, recent_time="21:30",
            days=(6, 0, 1, 3, 5),
        )
    )  # fmt: skip
    check_run_plan(p)
    assert len([w for w in p.weeks if w.phase == "taper"]) == 2
    assert any(w.phase == "cutback" for w in p.weeks)


def test_8_chest_cold_after_week_one(make_input):
    p = generate(make_input("pyramids", 21.1))
    fb = CheckInFeedback(done=2, feel="hard", pain="none", sick="chest", sick_days=3)
    c = check_in(p.input, p, 0, fb)
    assert c.action == "sick"
    p2 = generate(c.input)
    assert any(d.workout and d.workout.kind == "rest" for d in p2.weeks[0].days)
    easy_until = c.input.flags.easy_only_until
    assert easy_until is not None
    assert not any(
        d.workout and d.workout.kind == "quality" and d.date <= easy_until for d in p2.weeks[0].days
    )


def test_9_sharp_pain_pauses_the_plan(make_input):
    p = generate(make_input("pyramids", 21.1))
    c = check_in(p.input, p, 0, CheckInFeedback(done=3, feel="ok", pain="sharp", sick="none"))
    assert c.action == "paused"
    assert generate(c.input).status == "blocked"


def test_10_good_week_keeps_progressing(make_input):
    p = generate(make_input("pyramids", 21.1))
    fb = CheckInFeedback(done=4, feel="easy", pain="none", sick="none", long_done=True)
    p2 = generate(check_in(p.input, p, 0, fb).input)
    assert p2.weeks[0].km >= p.weeks[1].km * 0.85


def test_11_paces_5k_20_minutes_predicts_half_about_1_33():
    v = vdot_from(5, 1200)
    t = predict_time(v, 21.0975)
    assert 5480 < t < 5700, fmt_time(t)


def test_12_times_as_people_type_them(make_input):
    assert parse_duration("28", 5) == 1680
    assert parse_duration("28:00", 5) == 1680
    assert parse_duration("٢٨:٣٠", 5) == 1710
    assert parse_duration("1:55", 21.1) == 6900
    assert parse_duration("2", 21.1) == 7200
    assert parse_duration("0:28", 5) == 1680
    assert parse_duration("3:00", 5) is None
    assert parse_duration("abc", 5) is None

    p = generate(make_input("pyramids", 21.1, recent_time="28", goal="time", goal_time="2:05:00"))
    assert p.paces is not None
    assert p.paces.tempo == "5:52"
    assert all(w.km < 45 for w in p.weeks)

    p = generate(make_input("pyramids", 21.1, recent_time="3:00"))
    assert p.paces is None
    assert any("مش منطقي" in w for w in p.warnings)
