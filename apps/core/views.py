import logging

from django import forms
from django.contrib.admin.views.decorators import staff_member_required
from django.core.cache import cache
from django.db import connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from apps.core.forms import ChipSelect, ChipSelectMultiple, HMSField

logger = logging.getLogger(__name__)


@never_cache
@require_GET
def healthz(request: HttpRequest) -> JsonResponse:
    """Load balancer check: database and cache reachable. Returns no data."""
    checks = {"database": True, "cache": True}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        logger.exception("healthz: database check failed")
        checks["database"] = False
    try:
        cache.set("core:healthz", "1", 5)
        checks["cache"] = cache.get("core:healthz") == "1"
    except Exception:
        logger.exception("healthz: cache check failed")
        checks["cache"] = False
    healthy = all(checks.values())
    return JsonResponse(
        {"status": "ok" if healthy else "fail", **checks}, status=200 if healthy else 503
    )


class StyleguideForm(forms.Form):
    """Demo form for the component gallery."""

    phone = forms.CharField(label=_("رقم الموبايل"), help_text=_("هنبعتلك كود عليه."))
    level = forms.ChoiceField(
        label=_("بتجري كام مرة في الأسبوع؟"),
        choices=[("1", "1"), ("2", "2"), ("3", "3"), ("4+", "4+")],
        widget=ChipSelect,
    )
    days = forms.MultipleChoiceField(
        label=_("الأيام اللي فاضي فيها"),
        choices=[("6", _("السبت")), ("1", _("الاتنين")), ("3", _("الأربع")), ("5", _("الجمعة"))],
        widget=ChipSelectMultiple,
        required=False,
    )
    recent_time = HMSField(label=_("آخر وقت ليك في 5 كم"), required=False)


@staff_member_required
@require_http_methods(["GET", "POST"])
def styleguide(request: HttpRequest) -> HttpResponse:
    """Every brand component on one page, for review (staff only, shows no data)."""
    form = StyleguideForm(request.POST or None)
    if request.method == "POST":
        form.is_valid()
    return render(request, "core/styleguide.html", {"form": form})
