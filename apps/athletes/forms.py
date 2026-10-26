"""One short form per questionnaire step. All validation is server-side."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.athletes.models import WEEKDAY_CHOICES, Goal, Kit, Sex, Where
from apps.core.formatting import km_ar
from apps.core.forms import (
    ChipSelect,
    ChipSelectMultiple,
    HMSField,
    LatinDecimalField,
    LatinIntegerField,
)
from apps.races.models import SUPPORTED_DISTANCES_KM, Race, RaceKind
from engine import HEALTH_QUESTIONS

NUMBER = {"invalid": _("اكتب رقم.")}
CHOICE = _("اختار من الاختيارات اللي قدامك.")


def _distance_choices(distances: list[Decimal]) -> list[tuple[str, str]]:
    # One format ("5.0") for choices and stored values, so saved answers show as selected.
    return [(f"{d:.1f}", km_ar(float(d))) for d in distances]


class StepForm(forms.Form):
    """Egyptian Arabic message for a value that is not one of the chips."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field, forms.ChoiceField):
                field.error_messages["invalid_choice"] = CHOICE


class RaceStepForm(StepForm):
    distance_km = forms.TypedChoiceField(
        label=_("هتجري كام كيلو؟"), coerce=Decimal, widget=ChipSelect, required=False
    )
    start_date = forms.DateField(
        label=_("هتبدأ إمتى؟"),
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        error_messages={"required": _("اختار يوم البداية."), "invalid": _("اختار تاريخ صحيح.")},
    )

    def __init__(self, *args: Any, race: Race, today: date, **kwargs: Any) -> None:  # noqa: ANN401
        super().__init__(*args, **kwargs)
        self.race, self.today = race, today
        if race.kind == RaceKind.HYROX:
            del self.fields["distance_km"]
        else:
            field = self.fields["distance_km"]
            field.choices = _distance_choices([d.distance_km for d in race.distances.all()])  # type: ignore[attr-defined]
            field.required = True
            field.error_messages["required"] = _("اختار المسافة.")
        self.fields["start_date"].widget.attrs.update(
            {"min": today.isoformat(), "max": race.date.isoformat()}
        )

    def clean_start_date(self) -> date:
        start: date = self.cleaned_data["start_date"]
        if start < self.today:
            raise forms.ValidationError(_("اختار النهارده أو يوم بعده."))
        if start >= self.race.date:
            raise forms.ValidationError(_("لازم تبدأ قبل يوم السباق."))
        return start


class YouStepForm(StepForm):
    age = LatinIntegerField(
        label=_("سنك كام؟"),
        min_value=10,
        max_value=90,
        error_messages={**NUMBER, "required": _("اكتب سنك.")},
    )
    sex = forms.ChoiceField(
        label=_("انت"),
        choices=Sex.choices,
        widget=ChipSelect,
        help_text=_("بنستخدمها لأوزان محطات HYROX بس."),
        error_messages={"required": _("اختار واحدة.")},
    )
    weight_kg = LatinIntegerField(
        label=_("وزنك (اختياري)"),
        min_value=30,
        max_value=200,
        required=False,
        help_text=_("لأكل يوم السباق بس."),
        error_messages=NUMBER,
    )


class RunningStepForm(StepForm):
    runs_per_week = forms.TypedChoiceField(
        label=_("بتجري كام مرة في الأسبوع؟"),
        choices=[(str(n), str(n)) for n in range(8)],
        coerce=int,
        widget=ChipSelect,
        error_messages={"required": _("اختار رقم.")},
    )
    weekly_km = LatinDecimalField(
        label=_("كام كيلو في الأسبوع تقريبًا؟"),
        min_value=Decimal(0),
        max_value=Decimal(250),
        decimal_places=1,
        error_messages={**NUMBER, "required": _("اكتب رقم، ولو مش بتجري اكتب 0.")},
    )
    longest_km = LatinDecimalField(
        label=_("أطول جري الشهر ده (كم)"),
        min_value=Decimal(0),
        max_value=Decimal(60),
        decimal_places=1,
        error_messages={**NUMBER, "required": _("اكتب رقم، ولو مش بتجري اكتب 0.")},
    )

    def clean(self) -> dict[str, Any]:
        data = super().clean() or {}
        weekly, longest = data.get("weekly_km"), data.get("longest_km")
        if weekly is not None and longest is not None and longest > max(weekly, Decimal(0)) * 2 + 5:
            self.add_error(
                "longest_km", _("أطول جري أكبر من اللي بتجريه في الأسبوع بكتير. راجع الرقمين.")
            )
        return data


NO_TIME = ""


class TimeStepForm(StepForm):
    recent_km = forms.TypedChoiceField(
        label=_("آخر سباق أو تجربة جريتها"),
        choices=[(NO_TIME, _("مفيش")), *_distance_choices(list(SUPPORTED_DISTANCES_KM))],
        coerce=Decimal,
        empty_value=None,
        required=False,
        widget=ChipSelect,
        help_text=_("لو مفيش، التمارين هتبقى بالإحساس."),
    )
    recent_time = HMSField(label=_("خلّصتها في"), required=False)
    goal = forms.ChoiceField(
        label=_("هدفك"),
        choices=Goal.choices,
        widget=ChipSelect,
        error_messages={"required": _("اختار هدفك.")},
    )
    goal_time = HMSField(label=_("الوقت اللي عايزه"), required=False)

    def __init__(self, *args: Any, race: Race, **kwargs: Any) -> None:  # noqa: ANN401
        super().__init__(*args, **kwargs)
        self.race = race
        if race.kind == RaceKind.HYROX:
            del self.fields["goal_time"]
            self.fields["goal"].choices = [(Goal.FINISH, Goal.FINISH.label)]  # type: ignore[attr-defined]
            self.fields["goal"].initial = Goal.FINISH

    def clean(self) -> dict[str, Any]:
        data = super().clean() or {}
        if data.get("recent_km") and not data.get("recent_time"):
            self.add_error("recent_time", _("اكتب وقتك في السباق ده."))
        if not data.get("recent_km"):
            data["recent_time"] = None
        if (
            data.get("goal") == Goal.TIME
            and "goal_time" in self.fields
            and not data.get("goal_time")
        ):
            self.add_error("goal_time", _("اكتب الوقت اللي عايزه."))
        if data.get("goal") != Goal.TIME:
            data["goal_time"] = None
        return data


class DaysStepForm(StepForm):
    days = forms.TypedMultipleChoiceField(
        label=_("الأيام اللي فاضي تتمرن فيها"),
        choices=[(str(v), label) for v, label in WEEKDAY_CHOICES],
        coerce=int,
        widget=ChipSelectMultiple,
        help_text=_("من 3 لـ 6 أيام. الجري الطويل يوم الجمعة لو اخترتها."),
        error_messages={"required": _("اختار 3 أيام على الأقل.")},
    )
    where = forms.ChoiceField(
        label=_("بتجري فين؟"),
        choices=Where.choices,
        widget=ChipSelect,
        error_messages={"required": _("اختار مكان.")},
    )
    gps = forms.TypedChoiceField(
        label=_("بتقيس المسافة بإيه؟"),
        choices=[("yes", _("ساعة أو موبايل")), ("no", _("مفيش"))],
        coerce=lambda v: v == "yes",
        widget=ChipSelect,
        error_messages={"required": _("اختار واحدة.")},
    )
    kit = forms.MultipleChoiceField(
        label=_("الأدوات اللي عندك (اختياري)"),
        choices=Kit.choices,
        widget=ChipSelectMultiple,
        required=False,
    )

    def clean_days(self) -> list[int]:
        days: list[int] = self.cleaned_data["days"]
        if not 3 <= len(days) <= 6:
            raise forms.ValidationError(_("اختار من 3 لـ 6 أيام."))
        return days


class ConsentStepForm(StepForm):
    agree = forms.BooleanField(
        label=_("موافق، وفاهم إن الخطة مش نصيحة طبية"),
        error_messages={"required": _("لازم توافق عشان نكمّل.")},
    )


YES_NO = [("no", _("لأ")), ("yes", _("أيوه"))]


class HealthStepForm(StepForm):
    """PAR-Q style screen (engine HEALTH_QUESTIONS) plus injury history and pain now."""

    injury = forms.ChoiceField(
        label=_("اتصابت قبل كده من الجري أو الرياضة؟"),
        choices=[
            ("none", _("لأ")),
            ("knee", _("أيوه، في الركبة")),
            ("other", _("أيوه، حاجة تانية")),
        ],
        widget=ChipSelect,
        error_messages={"required": _("اختار واحدة.")},
    )
    pain = forms.ChoiceField(
        label=_("عندك وجع دلوقتي بيزيد لما تجري؟"),
        choices=[("none", _("لأ")), ("now", _("أيوه"))],
        widget=ChipSelect,
        error_messages={"required": _("اختار واحدة.")},
    )
    doctor_cleared = forms.BooleanField(
        label=_("كشفت والدكتور وافق إني أتمرن"),
        required=False,
        help_text=_("علّم هنا بس لو جاوبت «أيوه» على سؤال من اللي فوق وكشفت فعلًا."),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: ANN401
        super().__init__(*args, **kwargs)
        questions = {
            q.id: forms.TypedChoiceField(
                label=q.text,
                choices=YES_NO,
                coerce=lambda v: v == "yes",
                widget=ChipSelect,
                error_messages={"required": _("جاوب بأيوه أو لأ."), "invalid_choice": CHOICE},
            )
            for q in HEALTH_QUESTIONS
        }
        self.fields = {**questions, **self.fields}

    def health_data(self) -> dict[str, Any]:
        data = self.cleaned_data
        return {
            "answers": {q.id: bool(data[q.id]) for q in HEALTH_QUESTIONS},
            "doctor_cleared": bool(data["doctor_cleared"]),
            "injury": data["injury"],
            "pain": data["pain"],
        }
