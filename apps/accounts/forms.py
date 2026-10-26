from django import forms
from django.utils.translation import gettext_lazy as _

from apps.accounts.phone import normalize_phone
from apps.core.forms import latin_digits


class PhoneForm(forms.Form):
    phone = forms.CharField(
        label=_("رقم الموبايل"),
        max_length=20,
        widget=forms.TextInput(
            attrs={
                "inputmode": "tel",
                "autocomplete": "tel",
                "dir": "ltr",
                "placeholder": "01001234567",
            }
        ),
        error_messages={"required": _("اكتب رقم الموبايل.")},
    )

    def clean_phone(self) -> str:
        return normalize_phone(self.cleaned_data["phone"])


class CodeForm(forms.Form):
    code = forms.CharField(
        label=_("الكود"),
        max_length=6,
        min_length=6,
        widget=forms.TextInput(
            attrs={
                "inputmode": "numeric",
                "autocomplete": "one-time-code",
                "dir": "ltr",
                "pattern": "[0-9]*",
            }
        ),
        error_messages={
            "required": _("اكتب الكود اللي وصلك."),
            "min_length": _("الكود 6 أرقام."),
            "max_length": _("الكود 6 أرقام."),
        },
    )

    def clean_code(self) -> str:
        code = str(latin_digits(self.cleaned_data["code"]))
        if not code.isdigit():
            raise forms.ValidationError(_("الكود أرقام بس."))
        return code
