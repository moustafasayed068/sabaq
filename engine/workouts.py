"""The workout library: each function returns a Workout written for where and how the athlete runs."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from engine.jsmath import fmt_num, js_round, round1
from engine.paces import PaceTable, fmt_pace
from engine.types import Env, Level, StrengthExtra, Workout


@dataclass
class Ctx:
    """Per-plan state shared by the workout builders (mirrors `ctx` in the JS reference)."""

    env: Env
    level: Level
    sex: str | None
    injury: str | None
    week_idx: int = 0
    vdot: float | None = None
    paces: PaceTable | None = None
    predicted: float | None = None
    race_pace: float | None = None
    run_walk: bool = False
    # Warm-up and cool-down km of quality sessions; smaller in small weeks.
    wu: float = 2
    cd: float = 1.5


def has(env: Env, kit: str) -> bool:
    """Does the athlete have this kit? A gym implies dumbbells; treadmill/mixed implies a treadmill."""
    if kit in env.kit:
        return True
    if kit == "treadmill" and env.where in ("treadmill", "mixed"):
        return True
    return kit == "dumbbells" and "gym" in env.kit


EFFORT: dict[str, str] = {
    "easy": "سهل: تقدر تتكلم جمل كاملة",
    "long": "سهل: تقدر تتكلم جمل كاملة",
    "marathon": "ثابت ومريح: تقدر تتكلم جمل قصيرة",
    "tempo": "صعب بس متحكم فيه: تقدر تقول كلمتين",
    "interval": "صعب: الكلام صعب",
    "race": "سرعة السباق",
    "rep": "سريع ومرتاح، مش سباق",
}
# Fallback paces (sec/km) when there is no race time: used only to turn km into minutes.
DEFAULT_EASY: dict[Level, float] = {"beginner": 465, "intermediate": 405, "advanced": 345}
REL: dict[str, float] = {
    "easy": 1,
    "long": 1.02,
    "marathon": 0.9,
    "tempo": 0.85,
    "interval": 0.79,
    "rep": 0.75,
    "race": 0.88,
}


def pace_for(ctx: Ctx, key: str) -> float | None:
    if ctx.paces is None:
        return None
    if key == "race":
        return ctx.race_pace
    if key == "long":
        return ctx.paces.easy * 1.02
    return ctx.paces.get(key)


def rough_pace(ctx: Ctx, key: str) -> float:
    return pace_for(ctx, key) or DEFAULT_EASY[ctx.level] * REL.get(key, 1)


def seg(ctx: Ctx, km: float, key: str) -> str:
    """One run segment as text: km/h on a treadmill, laps on a track, minutes without GPS."""
    env, p = ctx.env, pace_for(ctx, key)
    km_txt = f"{fmt_num(round1(km))} كم" if km >= 1 else f"{js_round(km * 1000)} م"
    if env.where == "treadmill":
        if p:
            return f"{km_txt} على المشاية بسرعة {fmt_num(round1(3600 / p))} كم/س، ميل 1%"
        return f"{km_txt} على المشاية، {EFFORT[key]}، ميل 1%"
    if env.where == "track" and km < 2:
        laps = (km * 1000) / 400
        lap_txt = "لفة" if laps == 1 else f"{fmt_num(round1(laps))} لفة"
        metres = js_round(km * 1000)
        if p:
            return f"{lap_txt} ({metres} م) في {fmt_pace(p * km)}"
        return f"{lap_txt} ({metres} م)، {EFFORT[key]}"
    if not env.gps and env.where == "outdoor":
        mins = max(1, js_round((rough_pace(ctx, key) * km) / 60))
        if p:
            return f"{mins} دقيقة بسرعة {fmt_pace(p)} /كم تقريبًا"
        return f"{mins} دقيقة، {EFFORT[key]}"
    return f"{km_txt} بسرعة {fmt_pace(p)} /كم" if p else f"{km_txt}، {EFFORT[key]}"


# ---------------------------------------------------------------- strength

_LUNGES = re.compile(r"لانجز.*", re.DOTALL)


def strength_session(ctx: Ctx, light: bool) -> list[str]:
    sets = 2 if light else 3
    if has(ctx.env, "gym"):
        moves = [
            f"سكوات بالبار أو ليج بريس {sets} × 8",
            f"رفعة رومانية {sets} × 8",
            f"ستيب أب {sets} × 8 لكل رجل",
            f"رفع سمانة على الجهاز {sets} × 15",
            f"بلانك {sets} × 45 ثانية",
        ]
    elif has(ctx.env, "dumbbells"):
        moves = [
            f"جوبلت سكوات بدمبل {sets} × 10",
            f"رفعة رومانية بالدمبل {sets} × 10",
            f"ستيب أب على كرسي بدمبل {sets} × 8 لكل رجل",
            f"رفع سمانة بدمبل {sets} × 15",
            f"بلانك جانبي {sets} × 30 ثانية لكل ناحية",
        ]
    else:
        moves = [
            f"سكوات {sets} × 15",
            f"لانجز {sets} × 10 لكل رجل",
            f"رفع سمانة على رجل واحدة {sets} × 15",
            f"جسر (Glute bridge) {sets} × 15",
            f"بلانك {sets} × 40 ثانية",
        ]
    if ctx.injury == "knee":
        bridge = f"جسر على رجل واحدة {sets} × 10 لكل رجل"
        moves = [_LUNGES.sub(lambda _m: bridge, m, count=1) for m in moves]
    return moves


# ---------------------------------------------------------------- HYROX stations


@dataclass(frozen=True)
class Substitute:
    kit: str | None
    text: Callable[[int], str]


@dataclass(frozen=True)
class Station:
    id: str
    name: str
    race: str
    kit: str | None
    work: Callable[[int, str | None], str]
    subs: tuple[Substitute, ...] = ()


def _w(sex: str | None, female: str, male: str) -> str:
    return female if sex == "f" else male


STATIONS: tuple[Station, ...] = (
    Station("ski", "SkiErg", "1000 م", "skierg", lambda r, _s: f"SkiErg {r * 250} م", (
        Substitute("rower", lambda r: f"تجديف {r * 250} م (بدل SkiErg)"),
        Substitute(None, lambda _r: "أستك أو حبل: سحب لتحت بدراع مفرود 4 × 40 ثانية (بدل SkiErg)"),
    )),
    Station("push", "Sled Push", "50 م", "sled", lambda r, _s: f"Sled Push {r} × 12.5 م تقيل", (
        Substitute("treadmill", lambda _r: "زق المشاية وهي مقفولة 4 × 20 ثانية (بدل Sled Push)"),
        Substitute(None, lambda _r: "زق الحيطة بكل قوتك 4 × 20 ثانية + لانجز ماشي 4 × 10 م (بدل Sled Push)"),
    )),
    Station("pull", "Sled Pull", "50 م", "sled", lambda r, _s: f"Sled Pull {r} × 12.5 م", (
        Substitute("dumbbells", lambda _r: "تجديف بدمبل تقيل 4 × 10 لكل إيد + مشي لورا 4 × 20 م (بدل Sled Pull)"),
        Substitute(None, lambda _r: "حبل أو أستك مربوط: سحب وانت ماشي لورا 4 × 20 م (بدل Sled Pull)"),
    )),
    Station("bbj", "Burpee Broad Jumps", "80 م", None, lambda r, _s: f"Burpee Broad Jumps {r * 20} م"),
    Station("row", "Rowing", "1000 م", "rower", lambda r, _s: f"تجديف {r * 250} م", (
        Substitute("skierg", lambda r: f"SkiErg {r * 250} م (بدل التجديف)"),
        Substitute("dumbbells", lambda _r: "سوينج بالكيتل أو الدمبل 4 × 20 (بدل التجديف)"),
        Substitute(None, lambda _r: "بيربي 4 × 10 + سكوات 4 × 20 (بدل التجديف)"),
    )),
    Station("farm", "Farmers Carry", "200 م", "dumbbells",
            lambda r, s: f"Farmers Carry {r * 50} م بـ {_w(s, '2 × 16', '2 × 24')} كجم", (
        Substitute(None, lambda r: f"شيل شنطتين مليانين أزايز مية وامشي {r * 50} م (بدل Farmers Carry)"),
    )),
    Station("lunge", "Sandbag Lunges", "100 م", "sandbag",
            lambda r, s: f"Sandbag Lunges {r * 25} م بـ {_w(s, '10', '20')} كجم", (
        Substitute(None, lambda r: f"لانجز ماشي بشنطة ضهر فيها كتب أو أزايز {r * 25} م (بدل Sandbag Lunges)"),
    )),
    Station("wb", "Wall Balls", "100 رمية", "wallball",
            lambda r, s: f"Wall Balls {r * 25} رمية بكورة {_w(s, '4', '6')} كجم", (
        Substitute("dumbbells", lambda r: f"Thrusters بالدمبل {r * 15} عدة (بدل Wall Balls)"),
        Substitute(None, lambda r: f"سكوات + رمي شنطة رمل لفوق {r * 20} عدة (بدل Wall Balls)"),
    )),
)  # fmt: skip


def station_by_id(station_id: str) -> Station:
    return next(s for s in STATIONS if s.id == station_id)


def station_text(ctx: Ctx, st: Station, r: int) -> str:
    if st.kit is None or has(ctx.env, st.kit):
        return st.work(r, ctx.sex)
    sub = next(s for s in st.subs if s.kit is None or has(ctx.env, s.kit))
    return sub.text(r)


def missing_stations(ctx: Ctx) -> list[str]:
    return [s.name for s in STATIONS if s.kit and not has(ctx.env, s.kit)]


# ---------------------------------------------------------------- workouts


def day(kind: str, title: str, intensity: int, km: float, steps: list[str]) -> Workout:
    return Workout(kind=kind, title=title, intensity=intensity, km=round1(km), steps=steps)


def rest(steps: list[str], title: str = "راحة لحد ما تخف") -> Workout:
    return day("rest", title, 0, 0, steps)


def easy(ctx: Ctx, km: float, *, strides: bool = False) -> Workout:
    if ctx.run_walk:
        run = min(2 + ctx.week_idx, 6)
        sets = max(4, js_round((rough_pace(ctx, "easy") * km) / 60 / (run + 1)))
        return day("easy", "جري ومشي", 1, km, [
            "إحماء: مشي سريع 5 دقايق",
            f"جري {run} دقايق + مشي دقيقة، كرر {sets} مرات",
            "جري الجزء ده سهل جدًا، المهم تكمّل.",
        ])  # fmt: skip
    steps = [seg(ctx, km, "easy")]
    if strides:
        steps.append("في الآخر: 6 × 20 ثانية أسرع شوية، ومشي دقيقة بينهم")
    return day("easy", "جري سهل + تسارعات" if strides else "جري سهل", 1, km, steps)


def long_run(ctx: Ctx, km: float, *, race_pace_km: float = 0) -> Workout:
    steps: list[str] = []
    if ctx.run_walk:
        run = min(3 + ctx.week_idx, 8)
        sets = max(4, js_round((rough_pace(ctx, "long") * km) / 60 / (run + 1)))
        steps.append(f"جري {run} دقايق + مشي دقيقة، كرر {sets} مرات")
    elif race_pace_km:
        steps.append(seg(ctx, km - race_pace_km, "long"))
        steps.append(
            f"آخر {fmt_num(race_pace_km)} كم بسرعة السباق: {seg(ctx, race_pace_km, 'race')}"
        )
    else:
        steps.append(seg(ctx, km, "long"))
    if km >= 14:
        steps.append("خد مية معاك، ولو الجري أكتر من ساعة جرّب جل أو تمر كل 40 دقيقة زي يوم السباق.")
    return day("long", "الجري الطويل", 2, km, steps)


def tempo(ctx: Ctx, mins: int) -> Workout:
    tp = pace_for(ctx, "tempo") or rough_pace(ctx, "tempo")
    km = round1((mins * 60) / tp)
    return day("quality", "تيمبو", 3, round1(km + (ctx.wu + ctx.cd)), [
        f"إحماء: {seg(ctx, ctx.wu, 'easy')}",
        f"{mins} دقيقة تيمبو: {seg(ctx, km, 'tempo')}",
        f"تهدئة: {seg(ctx, ctx.cd, 'easy')}",
    ])  # fmt: skip


def cruise(ctx: Ctx, reps: int, km: float) -> Workout:
    return day("quality", "تيمبو متقطع", 3, round1(reps * km + (ctx.wu + ctx.cd)), [
        f"إحماء: {seg(ctx, ctx.wu, 'easy')}",
        f"{reps} × ({seg(ctx, km, 'tempo')})، وراحة دقيقة جري خفيف",
        f"تهدئة: {seg(ctx, ctx.cd, 'easy')}",
    ])  # fmt: skip


def intervals(ctx: Ctx, reps: int, km: float, rest_min: float) -> Workout:
    return day("quality", "إنترفال", 4, round1(reps * km + (ctx.wu + ctx.cd)), [
        f"إحماء: {seg(ctx, ctx.wu, 'easy')} + 4 تسارعات قصيرة",
        f"{reps} × ({seg(ctx, km, 'interval')})، وراحة {fmt_num(rest_min)} دقيقة جري خفيف أو مشي",
        f"تهدئة: {seg(ctx, ctx.cd, 'easy')}",
    ])  # fmt: skip


def hills(ctx: Ctx, reps: int) -> Workout:
    if ctx.env.where == "treadmill":
        work = f"{reps} × 60 ثانية جري على ميل 5% بمجهود صعب، ونزّل الميل وامشي 90 ثانية بينهم"
    else:
        work = f"{reps} × 60 ثانية طلوع على طلعة أو كوبري بمجهود صعب، وانزل ماشي"
    return day("quality", "طلعات", 3, round1((ctx.wu + ctx.cd) + reps * 0.25), [
        f"إحماء: {seg(ctx, ctx.wu, 'easy')}",
        work,
        f"تهدئة: {seg(ctx, ctx.cd, 'easy')}",
    ])  # fmt: skip


def sharpener(ctx: Ctx) -> Workout:
    if ctx.run_walk or ctx.level == "beginner":
        return easy(ctx, 3, strides=True)
    return day("quality", "تنشيط قبل السباق", 2, 6, [
        f"إحماء: {seg(ctx, 2, 'easy')}",
        f"3 × ({seg(ctx, 1, 'race')})، وراحة دقيقتين",
        f"تهدئة: {seg(ctx, 1, 'easy')}",
        "خفيف ومريح. الهدف إن رجلك تفتكر سرعة السباق، مش إنك تتعب.",
    ])  # fmt: skip


def shakeout(ctx: Ctx) -> Workout:
    return day("easy", "جري خفيف جدًا", 1, 2.5, [
        seg(ctx, 2.5, "easy"),
        "جهّز لبسك ورقمك والأكل اللي هتاكله الصبح من النهارده.",
    ])  # fmt: skip


def compromised(ctx: Ctx, rounds: int, race_effort: bool) -> Workout:
    steps = [f"إحماء: {seg(ctx, 1.5, 'easy')}"]
    for i, st in enumerate(STATIONS[:rounds]):
        run = seg(ctx, 1, "race" if race_effort else "tempo")
        steps.append(f"{i + 1}. {run} ← ثم {station_text(ctx, st, 2 if race_effort else 3)}")
    steps.append("بعد كل محطة اطلع تجري على طول، ده أهم جزء في التمرين.")
    title = "محاكاة السباق" if race_effort else "جري + محطات"
    return day("quality", title, 4, rounds + 1.5, steps)


def stations(ctx: Ctx, sets: int) -> Workout:
    picks = (
        ("push", "pull", "farm", "wb") if ctx.week_idx % 2 == 0 else ("ski", "row", "lunge", "bbj")
    )
    steps = [f"{sets} جولات، راحة دقيقتين بين كل جولة:"]
    steps += [station_text(ctx, station_by_id(i), sets) for i in picks]
    steps += [f"قوة: {m}" for m in strength_session(ctx, sets < 3)[:2]]
    return day("strength", "محطات وقوة", 3, 0, steps)


def hyrox_intervals(ctx: Ctx, reps: int) -> Workout:
    return day("quality", "إنترفال كيلومترات", 4, reps + 3.5, [
        f"إحماء: {seg(ctx, 2, 'easy')}",
        f"{reps} × ({seg(ctx, 1, 'tempo')})، وراحة 90 ثانية",
        f"تهدئة: {seg(ctx, 1.5, 'easy')}",
        "دي نفس سرعة الكيلوهات اللي هتجريها في السباق.",
    ])  # fmt: skip


def strength_extra(ctx: Ctx, light: bool) -> StrengthExtra:
    return StrengthExtra(title="قوة 20 دقيقة بعد الجري", steps=strength_session(ctx, light))
