"""Differential test: many generated inputs run through the JS reference and the Python
port must give identical output. Covers branches the 21 golden files do not reach.
Skipped when Node.js is not installed (CI has it)."""

import json
import random
import shutil
import subprocess
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from engine import RACES, CheckInFeedback, PlanInput, check_in, generate
from engine.tests.test_golden import diff

NODE = shutil.which("node")
RUNNER = Path(__file__).with_name("js_runner.js")
N_CASES = 1500

TIMES = ["28:00", "28", "24:30", "1:55", "٢٢:١٥", "45", "3:00", "abc", "", None, "19.40", "50:00"]
KIT = ["dumbbells", "gym", "rower", "skierg", "sled", "wallball", "sandbag"]
HEALTH = ["heart", "chestActive", "chestRest", "dizzy", "joint", "meds", "pregnant", "other"]


def _case(rng: random.Random) -> dict[str, Any]:
    race = rng.choice(RACES)
    km = rng.choice(race.distances) if race.type == "run" else None
    race_date = race.date_for(km)
    start = race_date - timedelta(
        days=rng.choice([2, 4, 6, 9, 13, 20, 27, 34, 41, 55, 70, 90, 130])
    )
    inp: dict[str, Any] = {
        "startDate": start.isoformat(),
        "age": rng.choice([16, 22, 28, 35, 49, 50, 61]),
        "sex": rng.choice(["m", "f"]),
        "weeklyKm": rng.choice([0, 4, 8, 12, 20, 28, 35, 50, 70]),
        "longestKm": rng.choice([0, 2, 3.5, 5, 8, 10, 14, 18, 24, 28]),
        "runsPerWeek": rng.choice([0, 1, 2, 3, 4, 5, 6]),
        "recentKm": rng.choice([5, 5, 10, 21.1]),
        "goal": rng.choice(["finish", "time"]),
        "days": sorted(rng.sample(range(7), rng.randint(3, 6))),
        "injury": rng.choice(["none", "none", "knee", "other"]),
        "pain": rng.choice(["none"] * 6 + ["now"]),
        "health": dict.fromkeys(rng.sample(HEALTH, rng.choice([0] * 8 + [1])), True),
        "env": {
            "where": rng.choice(["outdoor", "treadmill", "track", "mixed"]),
            "gps": rng.random() < 0.7,
            "kit": rng.sample(KIT, rng.randint(0, 4)),
        },
        "raceId": race.id,
        "raceName": race.name,
        "raceType": race.type,
        "raceDate": race_date.isoformat(),
    }
    if km is not None:
        inp["distanceKm"] = km
    time = rng.choice(TIMES)
    if time is not None:
        inp["recentTime"] = time
    if rng.random() < 0.8:
        inp["weightKg"] = rng.choice([55, 72, 90])
    if inp["goal"] == "time":
        inp["goalTime"] = rng.choice(["1:45:00", "2:05:00", "25:00", "50:00", "4:00:00", "xx"])
    if inp["health"] and rng.random() < 0.5:
        inp["doctorCleared"] = True
    case: dict[str, Any] = {"input": inp}
    if rng.random() < 0.4:
        fb: dict[str, Any] = {
            "done": rng.randint(0, 6),
            "feel": rng.choice(["easy", "ok", "hard"]),
            "pain": rng.choice(["none", "none", "mild", "sharp"]),
            "sick": rng.choice(["none", "none", "head", "chest"]),
            "longDone": rng.random() < 0.6,
        }
        if fb["sick"] == "chest":
            fb["sickDays"] = rng.choice([1, 3, 7])
        if rng.random() < 0.3:
            fb["newTime"] = rng.choice(["24:00", "26:40", "31:10"])
        case["feedback"] = fb
    return case


def _python(case: dict[str, Any]) -> dict[str, Any]:
    inp = PlanInput.from_dict(case["input"])
    plan = generate(inp)
    if "feedback" not in case:
        return {"output": plan.to_dict()}
    if not plan.weeks:
        return {"skipped": True}
    res = check_in(inp, plan, 0, CheckInFeedback.from_dict(case["feedback"]))
    next_plan = None if res.action == "paused" else generate(res.input).to_dict()
    return {"checkIn": res.to_dict(), "nextPlan": next_plan}


@pytest.mark.skipif(NODE is None, reason="Node.js is not installed")
def test_python_matches_js_on_generated_cases():
    assert NODE is not None
    rng = random.Random(20261027)
    cases = [_case(rng) for _ in range(N_CASES)]
    proc = subprocess.run(  # noqa: S603 - fixed local script, test only
        [NODE, str(RUNNER)], input=json.dumps(cases), capture_output=True, text=True, check=True
    )
    expected = json.loads(proc.stdout)
    failures = []
    for i, (case, js_out) in enumerate(zip(cases, expected, strict=True)):
        problems = diff(js_out, _python(case))
        if problems:
            failures.append(
                f"case {i}: {json.dumps(case, ensure_ascii=False)}\n  " + "\n  ".join(problems[:5])
            )
    assert not failures, f"{len(failures)} of {N_CASES} differ:\n" + "\n".join(failures[:5])


def test_case_generator_is_deterministic():
    assert _case(random.Random(1)) == _case(random.Random(1))
    assert date.fromisoformat(_case(random.Random(2))["input"]["startDate"])
