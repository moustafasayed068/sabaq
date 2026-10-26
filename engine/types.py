"""Engine data: dataclasses in, dataclasses out.

`to_dict()` gives the exact JSON shape of the JavaScript reference (camelCase keys,
absent keys left out), which is what the golden tests compare and what Django stores.
`from_dict()` reads that same shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import date
from typing import Any, Literal

from engine.jsmath import js_plus, num_or

RaceType = Literal["run", "hyrox"]
Where = Literal["outdoor", "treadmill", "track", "mixed"]
Level = Literal["beginner", "intermediate", "advanced"]
Status = Literal["ok", "risky", "blocked"]
BlockKind = Literal["health", "pain", "age", "date", "feasibility"]

DEFAULT_DAYS: tuple[int, ...] = (6, 1, 3, 5)


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d is not None else None


def _date(value: object) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _required_date(value: object, name: str) -> date:
    d = _date(value)
    if d is None:
        raise ValueError(f"{name} is required")
    return d


def _opt_float(value: object) -> float | None:
    return None if value is None else js_plus(value)


@dataclass(frozen=True)
class HealthAnswers:
    """PAR-Q style screen. True = the athlete answered yes."""

    heart: bool = False
    chestActive: bool = False  # noqa: N815 - same ids as the JS reference
    chestRest: bool = False  # noqa: N815
    dizzy: bool = False
    joint: bool = False
    meds: bool = False
    pregnant: bool = False
    other: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> HealthAnswers:
        names = {f.name for f in fields(cls)}
        return cls(**{k: bool(v) for k, v in (data or {}).items() if k in names})

    def yes(self) -> list[str]:
        return [f.name for f in fields(self) if getattr(self, f.name)]

    def to_dict(self) -> dict[str, bool]:
        return dict.fromkeys(self.yes(), True)


@dataclass(frozen=True)
class Env:
    where: Where = "outdoor"
    gps: bool = True
    kit: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Env:
        data = data or {}
        return cls(
            where=data.get("where", "outdoor"),
            gps=bool(data.get("gps", True)),
            kit=tuple(data.get("kit") or ()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"where": self.where, "gps": self.gps, "kit": list(self.kit)}


@dataclass(frozen=True)
class Flags:
    """State carried from a weekly check-in into the next generate()."""

    continuing: bool = False
    progress_now: bool = False
    no_increase_first_week: bool = False
    rest_until: date | None = None
    easy_only_until: date | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Flags:
        data = data or {}
        return cls(
            continuing=bool(data.get("continuing")),
            progress_now=bool(data.get("progressNow")),
            no_increase_first_week=bool(data.get("noIncreaseFirstWeek")),
            rest_until=_date(data.get("restUntil")),
            easy_only_until=_date(data.get("easyOnlyUntil")),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.continuing:
            out["continuing"] = True
        if self.rest_until:
            out["restUntil"] = self.rest_until.isoformat()
        if self.easy_only_until:
            out["easyOnlyUntil"] = self.easy_only_until.isoformat()
        if self.no_increase_first_week:
            out["noIncreaseFirstWeek"] = True
        if self.progress_now:
            out["progressNow"] = True
        return out


@dataclass(frozen=True)
class PlanInput:
    """Everything the engine needs. Optional text fields left as None are omitted in to_dict."""

    start_date: date
    race_date: date
    race_name: str
    race_type: RaceType = "run"
    distance_km: float = 21.1
    race_id: str | None = None
    age: float = 30
    sex: str | None = None
    weight_kg: float | None = None
    weekly_km: float = 0
    longest_km: float = 0
    runs_per_week: float = 0
    recent_km: float | None = None
    recent_time: str | None = None
    goal: str | None = None
    goal_time: str | None = None
    days: tuple[int, ...] = DEFAULT_DAYS
    injury: str | None = None
    pain: str | None = None
    health: HealthAnswers = field(default_factory=HealthAnswers)
    doctor_cleared: bool | None = None
    env: Env = field(default_factory=Env)
    flags: Flags = field(default_factory=Flags)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlanInput:
        """Read the JS-shaped input and apply the reference's normalise() rules."""
        raw_days = data.get("days")
        return cls(
            start_date=_required_date(data.get("startDate"), "startDate"),
            race_date=_required_date(data.get("raceDate"), "raceDate"),
            race_name=str(data.get("raceName", "")),
            race_type=data.get("raceType", "run"),
            distance_km=num_or(data.get("distanceKm"), 21.1),
            race_id=data.get("raceId"),
            age=num_or(data.get("age"), 30),
            sex=data.get("sex"),
            weight_kg=num_or(data.get("weightKg"), 0) or None,
            weekly_km=max(0, num_or(data.get("weeklyKm"), 0)),
            longest_km=max(0, num_or(data.get("longestKm"), 0)),
            runs_per_week=max(0, num_or(data.get("runsPerWeek"), 0)),
            recent_km=_opt_float(data.get("recentKm")),
            recent_time=None if data.get("recentTime") is None else str(data["recentTime"]),
            goal=data.get("goal"),
            goal_time=None if data.get("goalTime") is None else str(data["goalTime"]),
            days=DEFAULT_DAYS if raw_days is None else tuple(int(js_plus(d)) for d in raw_days),
            injury=data.get("injury"),
            pain=data.get("pain"),
            health=HealthAnswers.from_dict(data.get("health")),
            doctor_cleared=data.get("doctorCleared"),
            env=Env.from_dict(data.get("env")),
            flags=Flags.from_dict(data.get("flags")),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "startDate": self.start_date.isoformat(),
            "age": self.age,
            "sex": self.sex,
            "weightKg": self.weight_kg,
            "weeklyKm": self.weekly_km,
            "longestKm": self.longest_km,
            "runsPerWeek": self.runs_per_week,
            "recentKm": self.recent_km,
            "recentTime": self.recent_time,
            "goal": self.goal,
            "goalTime": self.goal_time,
            "days": list(self.days),
            "injury": self.injury,
            "pain": self.pain,
            "health": self.health.to_dict(),
            "doctorCleared": self.doctor_cleared,
            "env": self.env.to_dict(),
            "raceId": self.race_id,
            "raceName": self.race_name,
            "raceType": self.race_type,
            "raceDate": self.race_date.isoformat(),
            "distanceKm": self.distance_km,
            "flags": self.flags.to_dict(),
        }
        always = {"weightKg"}
        return {k: v for k, v in out.items() if v is not None or k in always}


# ---------------------------------------------------------------- output


@dataclass
class StrengthExtra:
    title: str
    steps: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "steps": list(self.steps)}


@dataclass
class Workout:
    kind: str
    title: str
    intensity: int
    km: float
    steps: list[str]
    extra: StrengthExtra | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "title": self.title,
            "intensity": self.intensity,
            "km": self.km,
            "steps": list(self.steps),
            "extra": self.extra.to_dict() if self.extra else None,
        }


@dataclass
class Day:
    date: date
    day_name: str
    role: str
    workout: Workout | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date.isoformat(),
            "dayName": self.day_name,
            "role": self.role,
            "workout": self.workout.to_dict() if self.workout else None,
        }


@dataclass
class Week:
    index: int
    start: date
    phase: str
    phase_name: str
    target_km: int | None
    km: float
    days: list[Day]

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "start": self.start.isoformat(),
            "phase": self.phase,
            "phaseName": self.phase_name,
            "targetKm": self.target_km,
            "km": self.km,
            "days": [d.to_dict() for d in self.days],
        }


@dataclass(frozen=True)
class Alternative:
    kind: Literal["distance", "later"]
    text: str
    distance_km: float | None = None
    weeks: int | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": self.kind}
        if self.distance_km is not None:
            out["distanceKm"] = self.distance_km
        if self.weeks is not None:
            out["weeks"] = self.weeks
        out["text"] = self.text
        return out


@dataclass(frozen=True)
class PaceSummary:
    easy: str
    tempo: str
    interval: str
    race: str
    predicted: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "easy": self.easy,
            "tempo": self.tempo,
            "interval": self.interval,
            "race": self.race,
            "predicted": self.predicted,
        }


@dataclass
class GoalVerdict:
    ok: bool
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "text": self.text}


@dataclass
class Plan:
    input: PlanInput
    status: Status = "ok"
    messages: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    weeks: list[Week] = field(default_factory=list)
    alternatives: list[Alternative] = field(default_factory=list)
    block_kind: BlockKind | None = None
    level: Level | None = None
    level_name: str | None = None
    time_read: str | None = None
    paces: PaceSummary | None = None
    goal_verdict: GoalVerdict | None = None
    # Which builder ran ("run" sets peak_long/peak_weekly; "hyrox" sets peak_long to null).
    builder: RaceType | None = None
    peak_long: float | None = None
    peak_weekly: int | None = None
    race_day_tips: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "input": self.input.to_dict(),
            "status": self.status,
            "messages": list(self.messages),
            "warnings": list(self.warnings),
            "weeks": [w.to_dict() for w in self.weeks],
            "alternatives": [a.to_dict() for a in self.alternatives],
        }
        if self.block_kind is not None:
            out["blockKind"] = self.block_kind
        if self.level is not None:
            out["level"] = self.level
            out["levelName"] = self.level_name
        if self.time_read is not None:
            out["timeRead"] = self.time_read
        if self.goal_verdict is not None:
            out["goalVerdict"] = self.goal_verdict.to_dict()
        if self.paces is not None:
            out["paces"] = self.paces.to_dict()
        if self.builder is not None:
            out["peakLong"] = self.peak_long
        if self.peak_weekly is not None:
            out["peakWeekly"] = self.peak_weekly
        if self.race_day_tips is not None:
            out["raceDayTips"] = {"steps": list(self.race_day_tips)}
        return out


@dataclass(frozen=True)
class CheckInFeedback:
    """One week's check-in. `pain`/`feel`/`sick` None means the athlete did not answer."""

    done: int = 0
    feel: Literal["easy", "ok", "hard"] | None = None
    pain: Literal["none", "mild", "sharp"] | None = None
    sick: Literal["none", "head", "chest"] | None = None
    sick_days: int = 0
    long_done: bool = False
    new_time: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CheckInFeedback:
        return cls(
            done=int(num_or(data.get("done"), 0)),
            feel=data.get("feel"),
            pain=data.get("pain"),
            sick=data.get("sick"),
            sick_days=int(num_or(data.get("sickDays"), 0)),
            long_done=bool(data.get("longDone")),
            new_time=data.get("newTime") or None,
        )


@dataclass(frozen=True)
class CheckInResult:
    action: Literal["continue", "sick", "paused"]
    messages: list[str]
    input: PlanInput

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "messages": list(self.messages),
            "input": self.input.to_dict(),
        }
