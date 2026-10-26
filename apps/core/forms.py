"""Shared form widgets and fields that render the brand components."""

from __future__ import annotations

from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class ChipSelect(forms.RadioSelect):
    """One choice as pill chips. Works without JavaScript."""

    template_name = "components/chips.html"


class ChipSelectMultiple(forms.CheckboxSelectMultiple):
    template_name = "components/chips.html"


_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫,", "01234567890123456789..")


def latin_digits(value: Any) -> Any:  # noqa: ANN401
    """Arabic-Indic digits and decimal commas to Western ones ("٢١٫١" -> "21.1")."""
    return value.strip().translate(_ARABIC_DIGITS) if isinstance(value, str) else value


class NumberInput(forms.TextInput):
    """A text box with the numeric keypad (type=number misbehaves with RTL and Arabic digits)."""

    def __init__(self, attrs: dict[str, Any] | None = None, *, decimal: bool = False) -> None:
        base = {
            "inputmode": "decimal" if decimal else "numeric",
            "autocomplete": "off",
            "dir": "ltr",
        }
        super().__init__({**base, **(attrs or {})})


class LatinIntegerField(forms.IntegerField):
    widget = NumberInput

    def to_python(self, value: Any) -> int | None:  # noqa: ANN401
        return super().to_python(latin_digits(value))


class LatinDecimalField(forms.DecimalField):
    def __init__(self, **kwargs: Any) -> None:  # noqa: ANN401
        kwargs.setdefault("widget", NumberInput(decimal=True))
        super().__init__(**kwargs)

    def to_python(self, value: Any) -> Any:  # noqa: ANN401
        return super().to_python(latin_digits(value))


class HMSWidget(forms.MultiWidget):
    """Three numeric boxes (hours, minutes, seconds), never one text box with a colon."""

    template_name = "components/hms.html"
    use_fieldset = True
    UNITS = (_("ساعات"), _("دقايق"), _("ثواني"))

    def __init__(self, attrs: dict[str, Any] | None = None) -> None:
        super().__init__([forms.TextInput(), forms.TextInput(), forms.TextInput()], attrs)

    def decompress(self, value: int | None) -> list[int | None]:
        if value is None:
            return [None, None, None]
        return [value // 3600, (value % 3600) // 60, value % 60]

    def get_context(self, name: str, value: Any, attrs: dict[str, Any] | None) -> dict[str, Any]:  # noqa: ANN401
        context = super().get_context(name, value, attrs)
        for sub, unit in zip(context["widget"]["subwidgets"], self.UNITS, strict=True):
            sub["unit"] = unit
            sub["attrs"].setdefault("aria-label", unit)
        return context


class HMSField(forms.MultiValueField):
    """A duration in seconds, typed as hours / minutes / seconds. Empty boxes count as 0."""

    widget = HMSWidget
    default_error_messages = {  # noqa: RUF012
        "required": _("اكتب الوقت."),
        "incomplete": _("اكتب الوقت."),
        "empty": _("الوقت لازم يبقى أكتر من صفر."),
    }

    def __init__(self, *, max_hours: int = 9, **kwargs: Any) -> None:  # noqa: ANN401
        number = {"invalid": _("اكتب أرقام بس.")}
        fields = (
            LatinIntegerField(min_value=0, max_value=max_hours, error_messages=number),
            LatinIntegerField(min_value=0, max_value=59, error_messages=number),
            LatinIntegerField(min_value=0, max_value=59, error_messages=number),
        )
        super().__init__(fields=fields, require_all_fields=False, **kwargs)
        for f in self.fields:
            f.required = False

    def compress(self, data_list: list[Any]) -> int | None:
        if not data_list or all(v in (None, "") for v in data_list):
            return None
        h, m, s = (int(v or 0) for v in data_list)
        total = h * 3600 + m * 60 + s
        if total <= 0:
            raise ValidationError(self.error_messages["empty"], code="empty")
        return total
