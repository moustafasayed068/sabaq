"""Weekly check-in: turns how the week went into the input for the next generate().
A port of `checkIn` in reference/engine-js/sabaq-engine.js."""

from dataclasses import replace
from typing import Literal

from engine.dates import add_days
from engine.generate import normalise
from engine.jsmath import js_round
from engine.types import CheckInFeedback, CheckInResult, Flags, Plan, PlanInput


def check_in(
    raw_input: PlanInput, plan: Plan, week_index: int, fb: CheckInFeedback
) -> CheckInResult:
    inp = normalise(raw_input)
    wk = plan.weeks[week_index]
    messages: list[str] = []
    next_start = add_days(wk.start, 7)
    start_date = max(next_start, inp.start_date)
    planned = len([d for d in wk.days if d.workout and d.workout.kind != "rest"]) or 1
    ratio = max(0.0, min(1.0, fb.done / planned))
    km_done = wk.km * ratio
    long_planned = max(
        [0.0, *(d.workout.km for d in wk.days if d.workout and d.workout.kind == "long")]
    )
    long_done = long_planned if fb.long_done else 0

    if fb.pain == "sharp":
        messages.append(
            "الوجع اللي بيزيد مع الجري أو بيغيّر طريقة جريك ممكن يبقى إصابة. وقّف الجري "
            "واكشف عند دكتور أو أخصائي علاج طبيعي."
        )
        messages.append("الخطة واقفة لحد ما تقول إن الدكتور سمحلك. لما ترجع، هنبدأ أخف من الأول.")
        paused = replace(
            inp,
            start_date=start_date,
            flags=Flags(continuing=True),
            pain="now",
            injury=inp.injury if inp.injury and inp.injury != "none" else "other",
            weekly_km=js_round(km_done * 0.7),
        )
        return CheckInResult("paused", messages, paused)

    # Fitness does not vanish in one week: base the next week on at least 75% of the plan.
    weekly_km: float = js_round(wk.km * max(ratio, 0.75))
    longest_km = long_done or js_round(inp.longest_km * (0.9 if ratio < 0.5 else 1) * 10) / 10
    action: Literal["continue", "sick"] = "continue"
    rest_until = easy_only_until = None
    no_increase = False
    progress_now = False

    if fb.sick == "chest":
        rest_days = (fb.sick_days or 3) + 2
        rest_until = add_days(start_date, rest_days - 1)
        easy_only_until = add_days(start_date, rest_days + 6)
        weekly_km = js_round(weekly_km * (0.7 if rest_days > 7 else 0.85))
        messages.append(
            f"عندك حرارة أو كحة من الصدر أو تكسير: متجريش خالص. ريّح {rest_days} أيام "
            "(لحد ما تخف + يومين)، وبعدها أسبوع جري سهل بس قبل أي تمرين صعب."
        )
        messages.append("لو الحرارة مكملة أكتر من 3 أيام، أو حسيت بوجع في صدرك أو ضيق نفس، اكشف.")
        action = "sick"
    elif fb.sick == "head":
        easy_only_until = add_days(start_date, 2)
        no_increase = True
        messages.append(
            "برد خفيف (رشح أو زور بس): ينفع تجري سهل لو حاسس إنك كويس، ولو تعبان ريّح. "
            "أول 3 أيام جري سهل بس."
        )
        action = "sick"
    if fb.pain == "mild":
        no_increase = True
        messages.append(
            "وجع خفيف بيروح بعد الإحماء: مش هنزوّد المسافة الأسبوع ده. لو زاد أو بقى "
            "بيوجعك وانت ماشي، علّم «وجع بيزيد» في التسجيل الجاي."
        )
    if ratio < 0.5:
        no_increase = True
        messages.append("فوّت أكتر من نص التمارين: الأسبوع الجاي هيبقى بنفس الحجم، مش أكتر.")
    elif ratio < 1:
        messages.append("فوّت تمرين أو اتنين: مفيش مشكلة، كمّل عادي.")
    if fb.feel == "hard":
        no_increase = True
        messages.append("الأسبوع كان تقيل عليك، فهنثبّت الحجم أسبوع.")
    if fb.feel == "easy" and ratio == 1 and (not fb.pain or fb.pain == "none"):
        messages.append("أسبوع حلو. كمّل بنفس الخطة.")
    if (
        action == "continue"
        and ratio >= 0.75
        and fb.feel != "hard"
        and (not fb.pain or fb.pain == "none")
    ):
        progress_now = True
    recent_km, recent_time = inp.recent_km, inp.recent_time
    if fb.new_time:
        recent_km, recent_time = 5, fb.new_time
        messages.append("حدّثنا سرعاتك على وقت الـ 5 كم الجديد.")

    nxt = replace(
        inp,
        start_date=start_date,
        weekly_km=weekly_km,
        longest_km=longest_km,
        recent_km=recent_km,
        recent_time=recent_time,
        flags=Flags(
            continuing=True,
            progress_now=progress_now,
            no_increase_first_week=no_increase,
            rest_until=rest_until,
            easy_only_until=easy_only_until,
        ),
    )
    return CheckInResult(action, messages, nxt)
