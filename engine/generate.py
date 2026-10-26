"""generate(): a full race plan from the athlete's answers. A line-by-line port of
`generate`, `buildRun`, `buildHyrox`, `fillRunWeek` and `fillRaceWeek` in
reference/engine-js/sabaq-engine.js. Keep them in step: the golden tests compare both.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from datetime import date

from engine import workouts as w
from engine.data import DIST_NAME, LEVEL_NAME, PHASE_NAME, TARGET
from engine.dates import add_days, day_name, diff_days, eg_pos, js_weekday
from engine.health import screen
from engine.jsmath import fmt_num, js_round, js_sum, round1, round_half
from engine.layout import layout
from engine.paces import fmt_pace, fmt_time, pace_table, parse_duration, predict_time, vdot_from
from engine.types import (
    Alternative,
    Day,
    GoalVerdict,
    Level,
    PaceSummary,
    Plan,
    PlanInput,
    Week,
    Workout,
)
from engine.workouts import Ctx

MAX_WEEKS = 16


@dataclass
class WeekSpec:
    phase: str
    weekly: float = 0
    long: float = 0


def level_of(inp: PlanInput) -> Level:
    if inp.runs_per_week < 2 or inp.weekly_km < 10 or inp.longest_km < 5:
        return "beginner"
    if inp.weekly_km < 30 or inp.longest_km < 12:
        return "intermediate"
    return "advanced"


def normalise(inp: PlanInput) -> PlanInput:
    """The reference's normalise() for input built in Python (from_dict already applies it)."""
    return replace(
        inp,
        age=inp.age or 30,
        weekly_km=max(0, inp.weekly_km or 0),
        longest_km=max(0, inp.longest_km or 0),
        runs_per_week=max(0, inp.runs_per_week or 0),
        distance_km=inp.distance_km or 21.1,
        weight_kg=inp.weight_kg or None,
    )


def progression_rate(inp: PlanInput) -> float:
    if inp.age >= 50 or (inp.injury and inp.injury != "none"):
        return 1.07
    return 1.1


def generate(raw: PlanInput) -> Plan:
    inp = normalise(raw)
    out = Plan(input=inp)

    if not screen(inp.health).ok and not inp.doctor_cleared:
        out.status, out.block_kind = "blocked", "health"
        out.messages.append(
            "قبل ما نبدأ، لازم تكشف وتاخد موافقة دكتور على التمرين. لما الدكتور يوافق، "
            "علّم «الدكتور وافق» وهنعملك الخطة."
        )
        return out
    if inp.pain == "now":
        out.status, out.block_kind = "blocked", "pain"
        out.messages.append("عندك وجع دلوقتي. الخطة مش هتبدأ غير لما تكشف ويقولك تقدر تجري.")
        return out
    if inp.age < 18:
        out.status, out.block_kind = "blocked", "age"
        out.messages.append("سبق دلوقتي للي سنهم 18 سنة وأكبر.")
        return out

    level = level_of(inp)
    ctx = Ctx(env=inp.env, level=level, sex=inp.sex, injury=inp.injury)
    out.level, out.level_name = level, LEVEL_NAME[level]

    _set_paces(inp, ctx, out)

    total_days = diff_days(inp.start_date, inp.race_date)
    if total_days < 3:
        out.status, out.block_kind = "blocked", "date"
        out.messages.append("السباق قريب جدًا على خطة. ارتاح، ونام كويس، واجري على راحتك.")
        return out
    start = inp.start_date
    # Weeks are aligned to race day: the last week is the 7 days that end on race day.
    n = math.ceil((total_days + 1) / 7)
    if n > MAX_WEEKS:
        n = MAX_WEEKS
        start = add_days(inp.race_date, -MAX_WEEKS * 7 + 1)
        out.messages.append(
            f"السباق لسه بعيد. الخطة هتبدأ يوم {start.isoformat()}، "
            "ولحد ساعتها كمّل جري سهل 3 مرات في الأسبوع."
        )

    if inp.race_type == "hyrox":
        return _build_hyrox(inp, ctx, out, n, start)
    return _build_run(inp, ctx, out, n, start)


def _week_start(inp: PlanInput, n: int, i: int) -> date:
    return add_days(inp.race_date, -6 - 7 * (n - 1 - i))


def _set_paces(inp: PlanInput, ctx: Ctx, out: Plan) -> None:
    recent_km = inp.recent_km if inp.recent_km is not None else math.nan
    rt = parse_duration(inp.recent_time, recent_km)
    if inp.recent_time and inp.recent_time.strip() and not rt:
        out.warnings.append(
            f"الوقت «{inp.recent_time}» مش منطقي لـ {_num_text(inp.recent_km)} كم، "
            "فمشيناها بالإحساس. اكتبه دقايق:ثواني، زي 28:00."
        )
    if not (rt and inp.recent_km):
        out.warnings.append(
            "معندناش وقت حديث ليك، فالسرعات مكتوبة بالإحساس. بعد أول أسبوع اجري 5 كم "
            "بأحسن مجهود وسجّل الوقت، والخطة هتتظبط بالأرقام."
        )
        return
    km = inp.recent_km
    out.time_read = (
        f"فهمنا آخر وقت ليك: {fmt_time(rt)} في {fmt_num(km)} كم ({fmt_pace(rt / km)} /كم)."
    )
    vdot = vdot_from(km, rt)
    ctx.vdot = vdot
    ctx.paces = pace_table(vdot)
    hyrox = inp.race_type == "hyrox"
    race_km = 1 if hyrox else inp.distance_km
    ctx.predicted = None if hyrox else predict_time(vdot, race_km)
    ctx.race_pace = ctx.paces.tempo * 1.03 if hyrox else (ctx.predicted or 0) / race_km
    goal = parse_duration(inp.goal_time, race_km)
    if inp.goal == "time" and inp.goal_time and not goal and not hyrox:
        out.warnings.append(
            f"الهدف «{inp.goal_time}» مش منطقي لـ {fmt_num(race_km)} كم، فالخطة معمولة على "
            "سرعتك المتوقعة. اكتبه ساعات:دقايق:ثواني، زي 2:05:00."
        )
    if inp.goal == "time" and goal and not hyrox:
        weeks_left = math.ceil(diff_days(inp.start_date, inp.race_date) / 7)
        allowed = min(0.01 * weeks_left, 0.05)
        if vdot_from(race_km, goal) <= vdot * (1 + allowed):
            ctx.race_pace = goal / race_km
            out.goal_verdict = GoalVerdict(True, f"هدفك {fmt_time(goal)} واقعي.")
        else:
            realistic = predict_time(vdot * (1 + allowed), race_km)
            ctx.race_pace = realistic / race_km
            out.goal_verdict = GoalVerdict(
                False,
                f"هدفك {fmt_time(goal)} صعب في الوقت ده. الأقرب للواقع حوالي "
                f"{fmt_time(realistic)}، فالخطة معمولة عليه.",
            )
    out.paces = PaceSummary(
        easy=f"{fmt_pace(ctx.paces.easy_fast)}–{fmt_pace(ctx.paces.easy_slow)}",
        tempo=fmt_pace(ctx.paces.tempo),
        interval=fmt_pace(ctx.paces.interval),
        race=fmt_pace(ctx.race_pace),
        predicted=fmt_time(ctx.predicted) if ctx.predicted else None,
    )


def _num_text(x: float | None) -> str:
    return "undefined" if x is None else fmt_num(x)


def _week_days(inp: PlanInput, n: int, i: int, roles: dict[int, str], start: date) -> list[Day]:
    ws = _week_start(inp, n, i)
    days: list[Day] = []
    for d in range(7):
        dt = add_days(ws, d)
        days.append(Day(dt, day_name(dt), roles.get(eg_pos(js_weekday(dt)), "rest")))
    for x in days:
        if x.date < start or x.date > inp.race_date:
            x.role = "off"
    rest_until = inp.flags.rest_until
    if rest_until:
        for x in days:
            if x.date <= rest_until and x.role != "off":
                x.role = "rest-sick"
    return days


def _week_km(days: list[Day]) -> float:
    return round1(js_sum([x.workout.km for x in days if x.workout and x.workout.kind != "race"]))


# ---------------------------------------------------------------- running plans


def _build_run(inp: PlanInput, ctx: Ctx, out: Plan, n: int, start: date) -> Plan:
    d_km = inp.distance_km
    if d_km not in TARGET:
        raise ValueError(f"Unsupported running distance: {d_km} km")
    t = TARGET[d_km]
    lvl = ctx.level
    ctx.run_walk = lvl == "beginner" and (inp.weekly_km < 10 or inp.longest_km < 4)
    # The last week is always race week: very short plans drop the taper first, then build weeks.
    taper = (2 if n >= 8 else 1) if d_km == 42.2 else 1 if d_km == 21.1 and n >= 6 else 0
    taper = max(0, min(taper, n - 2))
    build_weeks = n - 1 - taper
    p = progression_rate(inp)
    long_step = 1.5 if lvl == "beginner" else 2
    days_count = len(inp.days)
    long_share = 0.5 if days_count <= 3 else 0.38 if days_count >= 5 else 0.45
    if ctx.run_walk:
        n_quality = 0
    elif lvl == "advanced" and days_count >= 5 and not inp.age >= 50:
        n_quality = 2
    else:
        n_quality = 1

    # Simulate weekly volume and long run.
    floor = {"beginner": 8, "intermediate": 15, "advanced": 25}[lvl]
    weekly = max(inp.weekly_km, min(floor, inp.weekly_km * 1.1 + 4))
    long = max(3 if ctx.run_walk else 4, inp.longest_km)
    long_cap = 32 if d_km == 42.2 else d_km
    plan: list[WeekSpec] = []
    peak_weekly = 0.0
    peak_long = 0.0
    for i in range(build_weeks):
        cutback = n >= 7 and 0 < i < build_weeks - 1 and (i + 1) % 4 == 0
        if i > 0 and not cutback and not (i == 1 and inp.flags.no_increase_first_week):
            weekly = min(weekly * p, t.peak_weekly[lvl])
            long = min(long + long_step, t.peak_long[lvl], long_cap)
        if i == 0 and inp.flags.progress_now:
            weekly = min(weekly * p, t.peak_weekly[lvl])
            long = min(long + long_step, t.peak_long[lvl], long_cap)
        wk = weekly * 0.8 if cutback else weekly
        lg = long * 0.8 if cutback else min(long, max(wk * long_share, inp.longest_km))
        phase = "cutback" if cutback else "peak" if i == build_weeks - 1 else "build"
        plan.append(WeekSpec(phase, wk, lg))
        if not cutback:
            peak_weekly = max(peak_weekly, wk)
            peak_long = max(peak_long, lg)
    if build_weeks == 0:  # race this week: judge it on current fitness
        peak_weekly = weekly
        peak_long = min(long, max(weekly * long_share, inp.longest_km))
    for k in range(taper):
        f = (0.8, 0.6)[k] if taper == 2 else 0.8
        lf = (0.75, 0.55)[k] if taper == 2 else 0.7
        plan.append(WeekSpec("taper", peak_weekly * f, peak_long * lf))
    plan.append(WeekSpec("race", peak_weekly * (0.45 if d_km >= 21.1 else 0.6), 0))

    # Feasibility.
    min_long = t.min_long
    out.builder = "run"
    out.peak_long = round1(peak_long)
    out.peak_weekly = js_round(peak_weekly)
    if (d_km == 42.2 and n < 8 and inp.longest_km < 24) or (
        lvl == "beginner" and d_km >= 21.1 and n < 8
    ):
        out.status = "blocked"
    elif peak_long >= min_long:
        out.status = "ok"
    elif peak_long >= min_long * 0.8:
        out.status = "risky"
    else:
        out.status = "blocked"

    if out.status != "ok":
        for alt in (5, 10, 21.1):
            if alt < d_km and peak_long >= TARGET[alt].min_long:
                out.alternatives.append(
                    Alternative("distance", f"ادخل {DIST_NAME[alt]} في نفس السباق", distance_km=alt)
                )
        weeks_needed = math.ceil(max(0, min_long - max(4, inp.longest_km)) / long_step) + 2 + taper
        out.alternatives.append(
            Alternative(
                "later",
                f"أو اختار سباق {DIST_NAME[d_km]} بعد {weeks_needed} أسبوع على الأقل",
                weeks=weeks_needed,
            )
        )
    if out.status == "blocked" and inp.flags.continuing:
        out.status = "risky"
        out.messages.append(
            f"بعد الأسبوع اللي فات، أطول جري هتوصله حوالي {fmt_num(round1(peak_long))} كم قبل "
            "السباق. خلي هدفك إنك تخلّص وبس، أو انقل لمسافة أقصر."
        )
    if out.status == "blocked":
        out.block_kind = "feasibility"
        out.messages.append(
            f"مش هننصحك تجري {DIST_NAME[d_km]} في {n} أسابيع من مستواك الحالي. أطول جري "
            f"هتوصله حوالي {fmt_num(round1(peak_long))} كم، والأمان إنك توصل "
            f"{fmt_num(min_long)} كم على الأقل قبل السباق."
        )
        return out
    if out.status == "risky" and out.goal_verdict and out.goal_verdict.ok:
        match = re.search(r"[0-9:]+", out.goal_verdict.text)
        goal_txt = match.group(0) if match else ""
        out.goal_verdict.text = (
            f"سرعتك تسمح بهدف {goal_txt}، بس المسافة هي المشكلة مش السرعة. خلي الوقت هدف "
            "إضافي، والأهم إنك تخلّص سليم."
        )
    if out.status == "risky" and not inp.flags.continuing:
        out.messages.append(
            f"ينفع، بس هيبقى صعب: أطول جري هيوصل حوالي {fmt_num(round1(peak_long))} كم. "
            "خلي هدفك إنك تخلّص، ومتجريش بسرعة."
        )
    if ctx.run_walk:
        out.messages.append(
            "هنبدأ بجري ومشي بالتبادل. ده مش ضعف: ده أأمن طريقة توصل بيها خط النهاية من غير إصابة."
        )

    positions = [eg_pos(x) for x in inp.days]
    for i in range(n):
        ctx.week_idx = i
        spec = plan[i]
        roles = layout(positions, 0 if spec.phase == "race" else n_quality)
        days = _week_days(inp, n, i, roles, start)
        if spec.phase == "race":
            _fill_race_week(inp, ctx, days, spec.weekly)
        else:
            _fill_run_week(inp, ctx, days, spec, i, d_km, n_quality)
        out.weeks.append(
            Week(
                index=i,
                start=_week_start(inp, n, i),
                phase=spec.phase,
                phase_name=PHASE_NAME[spec.phase],
                target_km=js_round(spec.weekly),
                km=_week_km(days),
                days=days,
            )
        )
    out.race_day_tips = race_day_tips(inp, ctx)
    return out


def _clamp(x: float, a: float, b: float) -> float:
    return max(a, min(b, x))


def _fill_run_week(
    inp: PlanInput, ctx: Ctx, days: list[Day], spec: WeekSpec, i: int, d_km: float, n_quality: int
) -> None:
    active = [x for x in days if x.role in ("long", "q1", "q2", "easy")]
    if not active:
        return
    lvl = ctx.level
    easy_only = inp.flags.easy_only_until
    # A partial first week (or sick days) gets a share of the volume.
    weekly = spec.weekly * min(1, len(active) / max(1, len(inp.days)))
    # The hard part of a quality session is about 18% of the week.
    budget = max(2.5, weekly * (0.15 if n_quality == 2 else 0.18))

    def tempo_mins() -> int:
        tp = w.pace_for(ctx, "tempo") or w.rough_pace(ctx, "tempo")
        return int(_clamp(js_round((budget * tp) / 60 / 5) * 5, 10, 40))

    def quality(role: str) -> Workout | None:
        if spec.phase in ("cutback", "taper"):
            if role == "q2":
                return None
            if d_km >= 21.1:
                return w.tempo(ctx, max(10, tempo_mins() - 5))
            return w.intervals(ctx, 4, 0.4 if d_km == 5 else 0.8, 2)
        if inp.injury == "knee" and role == "q1" and i % 3 == 0:
            return w.tempo(ctx, tempo_mins())
        if role == "q2":
            return w.intervals(ctx, int(_clamp(js_round(weekly * 0.1), 3, 6)), 1, 2)
        if d_km <= 10:
            rot = i % 3
            if rot == 0 and lvl != "advanced":
                return w.hills(ctx, int(_clamp(6 + i, 6, 10)))
            rk = 0.4 if d_km == 5 else 0.8
            if rot in (0, 1):
                reps = int(_clamp(js_round(budget / rk), 4, 10))
                return w.intervals(ctx, reps, rk, 1.5 if d_km == 5 else 2)
            return w.tempo(ctx, tempo_mins())
        if i % 2 == 0:
            return w.tempo(ctx, tempo_mins())
        return w.cruise(ctx, int(_clamp(js_round(budget / 1.6), 2, 6)), 1.6)

    quality_km = 0.0
    for x in active:
        if x.role in ("q1", "q2"):
            workout = None if easy_only and x.date <= easy_only else quality(x.role)
            if workout:
                x.workout = workout
                quality_km += workout.km
            else:
                x.role = "easy"

    long_day = next((x for x in active if x.role == "long"), None)
    long_km = round_half(spec.long)
    if long_day and easy_only and long_day.date <= easy_only:
        long_km = round_half(long_km * 0.7)
    if long_day:
        race_pace = (
            not ctx.run_walk
            and lvl != "beginner"
            and spec.phase == "build"
            and i > 0
            and i % 2 == 1
            and d_km >= 10
            and not (easy_only and long_day.date <= easy_only)
        )
        rp = min(js_round(long_km * 0.25), 5) if race_pace else 0
        long_day.workout = w.long_run(ctx, long_km, race_pace_km=rp)
    else:
        long_km = 0

    easy_days = [x for x in active if x.role == "easy"]
    min_easy = 2.5 if ctx.run_walk else 3
    share = (
        max(min_easy, min(12, (weekly - long_km - quality_km) / len(easy_days))) if easy_days else 0
    )
    # Strength: on up to 2 easy days that are not the day before the long run.
    long_idx = days.index(long_day) if long_day else -1
    strength_left = 1 if spec.phase in ("taper", "cutback") else 2
    for k, x in enumerate(easy_days):
        strides = not ctx.run_walk and k == 0 and spec.phase != "cutback"
        x.workout = w.easy(ctx, round_half(share), strides=strides)
        if strength_left > 0 and days.index(x) != long_idx - 1:
            x.workout.extra = w.strength_extra(ctx, spec.phase not in ("build", "peak"))
            strength_left -= 1
    for x in days:
        if x.role == "rest-sick":
            x.workout = w.rest(["متجريش. نام كويس واشرب مية كتير."])


# One race-effort session in race week (a run sharpener or a HYROX simulation).
_RACE_EFFORT_TITLES = ("تنشيط قبل السباق", "محاكاة السباق")


def _fill_race_week(inp: PlanInput, ctx: Ctx, days: list[Day], weekly: float) -> None:
    race_idx = next((k for k, x in enumerate(days) if x.date == inp.race_date), -1)
    hyrox = inp.race_type == "hyrox"
    for idx, x in enumerate(days):
        if idx > race_idx or x.role == "off":
            x.role = "off"
            continue
        if idx == race_idx:
            x.role = "race"
            title = inp.race_name if hyrox else f"{inp.race_name}: {DIST_NAME[inp.distance_km]}"
            x.workout = w.day("race", title, 5, 8 if hyrox else inp.distance_km, [])
            continue
        if x.role in ("rest", "rest-sick"):
            continue
        before = race_idx - idx
        if before == 1:
            x.role = "rest"
            x.workout = w.rest(["راحة كاملة. كُل أكل فيه نشويات كويس، ونام بدري."], title="راحة")
            continue
        has_sharpener = any(y.workout and y.workout.title in _RACE_EFFORT_TITLES for y in days)
        x.role = "q1" if 3 <= before <= 4 and not has_sharpener else "easy"
        if hyrox:
            x.workout = (
                w.compromised(ctx, 3, True)
                if x.role == "q1"
                else w.easy(ctx, 3, strides=before == 2)
            )
        elif x.role == "q1":
            x.workout = w.sharpener(ctx)
        elif before == 2:
            x.workout = w.shakeout(ctx)
        else:
            x.workout = w.easy(ctx, round_half(max(3, weekly / 4)))
    if race_idx < 0:
        return
    race_workout = days[race_idx].workout
    if race_workout:
        race_workout.steps = race_day_tips(inp, ctx)


def race_day_tips(inp: PlanInput, ctx: Ctx) -> list[str]:
    steps: list[str] = []
    if inp.race_type == "hyrox":
        steps.append(
            f"اجري الكيلوهات بسرعة حوالي {fmt_pace(ctx.race_pace)} /كم، وأول كيلو أبطأ شوية."
            if ctx.paces and ctx.race_pace
            else "أول كيلو أبطأ من إحساسك. السباق طويل."
        )
        steps.append("في المحطات: نفس ثابت، ومتقفش غير لو لازم.")
        steps.append(
            "أوزان فئة Open: كورة 6 كجم للرجالة و4 للستات، Farmers 2 × 24 و2 × 16، "
            "الشنطة 20 و10. اتأكد من القواعد الرسمية للسباق."
        )
    else:
        steps.append(
            f"سرعتك في السباق: {fmt_pace(ctx.race_pace)} /كم. أول 2 كم أبطأ 10 ثواني في الكيلو."
            if ctx.race_pace
            else "ابدأ أبطأ من إحساسك في أول 2 كم، وبعدين ثبّت."
        )
        if inp.distance_km >= 21.1:
            steps.append("اشرب مية في كل محطة، ولو هتجري أكتر من ساعة خد جل أو تمر كل 40 دقيقة.")
    if inp.weight_kg:
        steps.append(
            f"فطار قبل السباق بـ 2–3 ساعات: حوالي {js_round(inp.weight_kg)}–"
            f"{js_round(inp.weight_kg * 2)} جرام نشويات (عيش، شوفان، موز)، وأكل اتعودت عليه."
        )
    else:
        steps.append("فطار خفيف اتعودت عليه قبل السباق بـ 2–3 ساعات: عيش أو شوفان وموز.")
    steps.append("متجربش أي حاجة جديدة يوم السباق: لا جزمة، ولا لبس، ولا أكل.")
    return steps


# ---------------------------------------------------------------- HYROX plans

_HYROX_ROLE = {"long": "comp", "q1": "stations", "q2": "hint", "easy": "easy"}


def _build_hyrox(inp: PlanInput, ctx: Ctx, out: Plan, n: int, start: date) -> Plan:
    ctx.run_walk = False
    lvl = ctx.level
    out.builder = "hyrox"
    out.peak_long = None
    if inp.longest_km < 5:
        out.status = "risky"
        out.messages.append(
            "السباق فيه 8 كم جري بين المحطات. لو مش بتقدر تجري 5 كم ورا بعض، ادخل Doubles "
            "أو Relay، أو امشي جزء من الكيلوهات."
        )
    miss = w.missing_stations(ctx)
    if miss:
        out.warnings.append(
            f"مش عندك: {'، '.join(miss)}. حطينا تمارين بديلة، وحاول تتمرن على الأجهزة "
            "الحقيقية مرتين على الأقل قبل السباق."
        )
    days_count = len(inp.days)
    phases = [
        "cutback"
        if n >= 7 and 0 < i < n - 2 and (i + 1) % 4 == 0
        else "peak"
        if i == n - 2
        else "build"
        for i in range(n - 1)
    ]
    phases.append("race")
    pos = sorted(eg_pos(x) for x in inp.days)
    for i in range(n):
        ctx.week_idx = i
        phase = phases[i]
        r = layout(pos, min(2, days_count - 1))
        if days_count >= 3 and not any(r.get(x) == "q2" for x in pos):
            e = next((x for x in pos if r.get(x) == "easy"), None)
            if e is not None:
                r[e] = "q2"
        roles = {p: _HYROX_ROLE[role] for p, role in r.items()}
        days = _week_days(inp, n, i, roles, start)

        if phase == "race":
            _fill_race_week(inp, ctx, days, 12)
        else:
            light = phase == "cutback"
            rounds = 3 if light else min(3 + i, 5 if lvl == "beginner" else 7, 8)
            easy_only = inp.flags.easy_only_until
            for x in days:
                blocked = bool(easy_only and x.date <= easy_only)
                if x.role == "comp":
                    x.workout = w.easy(ctx, 4) if blocked else w.compromised(ctx, rounds, False)
                elif x.role == "stations":
                    sets = 2 if light else 3 if lvl == "beginner" else 4
                    x.workout = w.easy(ctx, 4) if blocked else w.stations(ctx, sets)
                elif x.role == "hint":
                    reps = 4 if light else min(4 + i, 8)
                    x.workout = w.easy(ctx, 4) if blocked else w.hyrox_intervals(ctx, reps)
                elif x.role == "easy":
                    x.workout = w.easy(ctx, round_half(4 if lvl == "beginner" else 6), strides=True)
                elif x.role == "rest-sick":
                    x.workout = w.rest(["متتمرنش. نام كويس واشرب مية كتير."])
        out.weeks.append(
            Week(
                index=i,
                start=_week_start(inp, n, i),
                phase=phase,
                phase_name=PHASE_NAME[phase],
                target_km=None,
                km=_week_km(days),
                days=days,
            )
        )
    out.race_day_tips = race_day_tips(inp, ctx)
    return out
