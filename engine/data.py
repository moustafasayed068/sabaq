"""Fixed tables from the JS reference: races, targets, health questions."""

import datetime as dt
from dataclasses import dataclass, field

from engine.types import Level, RaceType


@dataclass(frozen=True)
class Race:
    id: str
    name: str
    type: RaceType
    date: dt.date
    distances: tuple[float, ...] = ()
    date_by_distance: dict[float, dt.date] = field(default_factory=dict)
    note: str | None = None

    def date_for(self, distance_km: float | None) -> dt.date:
        if distance_km is not None and distance_km in self.date_by_distance:
            return self.date_by_distance[distance_km]
        return self.date


RACES: tuple[Race, ...] = (
    Race(
        "hyrox-cairo",
        "HYROX Cairo",
        "hyrox",
        dt.date(2026, 11, 14),
        note="السباق يومين 14 و15 نوفمبر: اختار يوم موجتك.",
    ),
    Race("gouna", "نص ماراثون الجونة", "run", dt.date(2026, 11, 21), (5, 10, 21.1)),
    Race("hyrox-dubai", "HYROX Dubai", "hyrox", dt.date(2026, 11, 27)),
    Race("sharm", "ماراثون شرم الشيخ", "run", dt.date(2026, 11, 28), (5, 10, 21.1, 42.2)),
    Race(
        "pyramids",
        "نص ماراثون الأهرامات",
        "run",
        dt.date(2026, 12, 12),
        (5, 10, 21.1),
        {5: dt.date(2026, 12, 11)},
    ),
    Race("luxor", "ماراثون الأقصر", "run", dt.date(2027, 1, 8), (5, 10, 21.1, 42.2)),
)


def race_by_id(race_id: str) -> Race:
    for race in RACES:
        if race.id == race_id:
            return race
    raise KeyError(race_id)


DIST_NAME: dict[float, str] = {
    5: "5 كم",
    10: "10 كم",
    21.1: "نص ماراثون (21.1 كم)",
    42.2: "ماراثون (42.2 كم)",
}


@dataclass(frozen=True)
class Target:
    peak_long: dict[Level, float]
    min_long: float
    peak_weekly: dict[Level, float]


TARGET: dict[float, Target] = {
    5: Target({"beginner": 5, "intermediate": 7, "advanced": 10}, 4,
              {"beginner": 15, "intermediate": 25, "advanced": 40}),
    10: Target({"beginner": 8, "intermediate": 11, "advanced": 14}, 7,
               {"beginner": 20, "intermediate": 32, "advanced": 50}),
    21.1: Target({"beginner": 15, "intermediate": 18, "advanced": 20}, 13,
                 {"beginner": 28, "intermediate": 40, "advanced": 60}),
    42.2: Target({"beginner": 28, "intermediate": 30, "advanced": 32}, 24,
                 {"beginner": 45, "intermediate": 55, "advanced": 75}),
}  # fmt: skip

LEVEL_NAME: dict[Level, str] = {"beginner": "مبتدئ", "intermediate": "متوسط", "advanced": "متقدم"}

PHASE_NAME: dict[str, str] = {
    "build": "بناء",
    "peak": "أعلى أسبوع",
    "cutback": "أسبوع أخف",
    "taper": "تخفيف قبل السباق",
    "race": "أسبوع السباق",
}


@dataclass(frozen=True)
class HealthQuestion:
    id: str
    text: str


HEALTH_QUESTIONS: tuple[HealthQuestion, ...] = (
    HealthQuestion("heart", "دكتور قالك قبل كده إن عندك مشكلة في القلب، أو إنك تتمرن تحت إشراف طبي بس؟"),
    HealthQuestion("chestActive", "بتحس بوجع في صدرك وانت بتتمرن أو بتعمل مجهود؟"),
    HealthQuestion("chestRest", "حسيت بوجع في صدرك وانت مرتاح في آخر شهر؟"),
    HealthQuestion("dizzy", "بتدوخ لدرجة إنك تفقد توازنك، أو أغمى عليك قبل كده؟"),
    HealthQuestion("joint", "عندك وجع دلوقتي في عضمة أو مفصل بيزيد مع الحركة؟"),
    HealthQuestion("meds", "بتاخد دوا للضغط أو للقلب؟"),
    HealthQuestion("pregnant", "حامل أو ولدتي في آخر 6 شهور؟"),
    HealthQuestion("other", "في أي سبب تاني تعرفه يخليك متتمرنش؟"),
)  # fmt: skip
