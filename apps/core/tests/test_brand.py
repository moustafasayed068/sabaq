import hashlib
import json
import re
from pathlib import Path

import pytest
from django import forms
from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.management import call_command

from apps.accounts.models import User
from apps.core.brand import EXTRA_COLORS, TOKENS_CSS, TOKENS_JSON, build_tokens_css
from apps.core.forms import ChipSelect, HMSField

STATIC = Path(settings.BASE_DIR) / "static"


def test_tokens_css_is_generated_from_tokens_json():
    assert TOKENS_CSS.read_text(encoding="utf-8") == build_tokens_css(), (
        "static/css/tokens.css is stale: run `python manage.py build_tokens`"
    )


def test_every_colour_token_has_light_and_dark_values():
    css = TOKENS_CSS.read_text(encoding="utf-8")
    data = json.loads(TOKENS_JSON.read_text(encoding="utf-8"))
    for token in data["color"]["tokens"]:
        assert f"--{token['name']}: {token['value']['light']};" in css
        assert css.count(f"--{token['name']}: {token['value']['dark']};") >= 2  # media + data-theme
    for name, values in EXTRA_COLORS.items():
        assert f"--{name}: {values['light']};" in css


def test_no_hard_coded_colours_outside_tokens():
    for path in STATIC.rglob("*.css"):
        if path.name == "tokens.css":
            continue
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(", path.read_text()), path
    for path in (Path(settings.BASE_DIR) / "templates").rglob("*.html"):
        text = path.read_text()
        assert not re.search(r"#[0-9a-fA-F]{6}\b", text), path
        assert "style=" not in text, f"{path}: inline styles break the CSP"


def test_fonts_are_self_hosted():
    css = (STATIC / "css" / "base.css").read_text()
    urls = re.findall(r'url\("([^"]+)"\)', css)
    assert len(urls) == 5
    for url in urls:
        assert finders.find(url.removeprefix("../")), url
    assert "googleapis" not in css


@pytest.mark.django_db
def test_base_layout_is_rtl_arabic_and_csp_safe(client):
    admin = User.objects.create_superuser("+201001234500", password="a-long-staff-password")
    client.force_login(admin)
    response = client.get("/styleguide/")
    html = response.content.decode()
    assert response.status_code == 200
    assert '<html lang="ar" dir="rtl">' in html
    assert "<script>" not in html  # no inline scripts (CSP)
    assert "htmx-2.0.11.min.js" in html
    assert 'class="num"' in html
    assert 'inputmode="numeric"' in html


@pytest.mark.django_db
def test_styleguide_is_staff_only(client):
    response = client.get("/styleguide/")
    assert response.status_code == 302
    assert settings.ADMIN_URL in response["Location"]


@pytest.mark.django_db
def test_styleguide_shows_form_errors(client):
    admin = User.objects.create_superuser("+201001234500", password="a-long-staff-password")
    client.force_login(admin)
    html = client.post("/styleguide/", {"recent_time_1": "75"}).content.decode()
    assert 'class="errors"' in html
    assert 'aria-invalid="true"' in html


class TimeForm(forms.Form):
    time = HMSField(label="t")
    optional = HMSField(label="o", required=False)


@pytest.mark.parametrize(
    ("h", "m", "s", "seconds"), [("", "28", "0", 1680), ("1", "55", "", 6900), ("0", "0", "45", 45)]
)
def test_hms_field_returns_seconds(h, m, s, seconds):
    form = TimeForm({"time_0": h, "time_1": m, "time_2": s})
    assert form.is_valid(), form.errors
    assert form.cleaned_data["time"] == seconds
    assert form.cleaned_data["optional"] is None


@pytest.mark.parametrize(
    ("data", "message"),
    [({}, "اكتب الوقت."), ({"time_1": "61"}, ""), ({"time_1": "ab"}, "اكتب أرقام بس."),
     ({"time_0": "0", "time_1": "0", "time_2": "0"}, "الوقت لازم يبقى أكتر من صفر.")],
)  # fmt: skip
def test_hms_field_rejects_bad_input(data, message):
    form = TimeForm(data)
    assert not form.is_valid()
    assert message in str(form.errors["time"])


def test_hms_widget_renders_three_numeric_boxes_with_initial_value():
    html = str(TimeForm(initial={"time": 6900})["time"])
    assert html.count('inputmode="numeric"') == 3
    assert 'value="1"' in html
    assert 'value="55"' in html
    assert "ساعات" in html


def test_chips_render_labelled_radios():
    class F(forms.Form):
        pick = forms.ChoiceField(choices=[("a", "أ"), ("b", "ب")], widget=ChipSelect)

    html = str(F(initial={"pick": "b"})["pick"])
    assert html.count('type="radio"') == 2
    assert 'value="b" id="id_pick_1" checked' in html


def test_build_tokens_command_is_idempotent(capsys):
    before = TOKENS_CSS.read_text(encoding="utf-8")
    call_command("build_tokens")
    assert TOKENS_CSS.read_text(encoding="utf-8") == before
    assert "tokens.css" in capsys.readouterr().out


def test_labels_have_no_colon_suffix():
    class F(forms.Form):
        phone = forms.CharField(label="رقم الموبايل")

    html = F()["phone"].as_field_group()
    assert '<label for="id_phone">رقم الموبايل</label>' in html


def test_vendored_htmx_is_unmodified():
    data = (STATIC / "vendor" / "htmx-2.0.11.min.js").read_bytes()
    assert (
        hashlib.sha256(data).hexdigest()
        == "d6fdc75f204e6bdefa99b69bf1e6d4ac69b8a364f77929f45c13476b4000f717"
    )
