"""Weekly check-in and the doctor-cleared confirmation. All validation is server-side."""

from __future__ import annotations

from typing import Any

from django import forms
from django.utils.translation import gettext_lazy as _

from apps.core.forms import ChipSelect, HMSField, LatinIntegerField
from engine.types import CheckInFeedback

CHOICE = _("اختار من الاختيارات اللي قدامك.")
PICK = {"required": _("اختار واحدة."), "invalid_choice": CHOICE}


def _hms(seconds: int | None) -> str | None:
    if seconds is None:
        return None
    return f"{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


class CheckInForm(forms.Form):
    done = forms.TypedChoiceField(coerce=int, widget=ChipSelect, error_messages=PICK)
    long_done = forms.TypedChoiceField(
        label=_("عملت الجري الطويل؟"),
        choices=[("yes", _("أيوه")), ("no", _("لأ"))],
        coerce=lambda v: v == "yes",
        widget=ChipSelect,
        error_messages=PICK,
    )
    feel = forms.ChoiceField(
        label=_("الأسبوع كان إزاي؟"),
        choices=[("easy", _("سهل")), ("ok", _("عادي")), ("hard", _("تقيل"))],
        widget=ChipSelect,
        error_messages=PICK,
    )
    pain = forms.ChoiceField(
        label=_("في وجع؟"),
        choices=[
            ("none", _("لأ")),
            ("mild", _("خفيف وبيروح بعد الإحماء")),
            ("sharp", _("بيزيد مع الجري أو بيغيّر طريقة جريي")),
        ],
        widget=ChipSelect,
        error_messages=PICK,
    )
    sick = forms.ChoiceField(
        label=_("كنت عيّان؟"),
        choices=[
            ("none", _("لأ")),
            ("head", _("برد خفيف (رشح أو زور)")),
            ("chest", _("حرارة أو كحة صدر أو تكسير")),
        ],
        widget=ChipSelect,
        error_messages=PICK,
    )
    sick_days = LatinIntegerField(
        label=_("عيّان بقالك كام يوم؟"),
        min_value=0,
        max_value=30,
        required=False,
        help_text=_("لو حرارة أو كحة صدر أو تكسير بس."),
        error_messages={"invalid": _("اكتب رقم.")},
    )
    new_time = HMSField(
        label=_("جريت 5 كم بوقت جديد؟ (اختياري)"),
        max_hours=1,
        required=False,
        help_text=_("لو جريت 5 كم على أد ما تقدر، اكتب وقتك ونحدّث سرعاتك."),
    )

    def __init__(self, *args: Any, planned: int, has_long: bool, **kwargs: Any) -> None:  # noqa: ANN401
        super().__init__(*args, **kwargs)
        done = self.fields["done"]
        done.label = _("عملت كام تمرين من %(n)s؟") % {"n": planned}
        done.choices = [(str(n), str(n)) for n in range(planned + 1)]  # type: ignore[attr-defined]
        if not has_long:
            del self.fields["long_done"]

    def feedback(self) -> CheckInFeedback:
        data = self.cleaned_data
        return CheckInFeedback(
            done=data["done"],
            long_done=bool(data.get("long_done")),
            feel=data["feel"],
            pain=data["pain"],
            sick=data["sick"],
            sick_days=(data.get("sick_days") or 0) if data["sick"] == "chest" else 0,
            new_time=_hms(data.get("new_time")),
        )


class ResumeForm(forms.Form):
    cleared = forms.BooleanField(
        label=_("كشفت والدكتور وافق إني أتمرن"),
        error_messages={"required": _("علّم إن الدكتور وافق الأول.")},
    )
