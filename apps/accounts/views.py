"""Phone login: ask for the number, then the one-time code."""

from django.contrib.auth import login, logout
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts import services
from apps.accounts.forms import CodeForm, PhoneForm
from apps.accounts.models import mask_phone
from apps.athletes.services import claim_questionnaire
from apps.core.request_context import client_ip
from apps.core.services import AuditAction, record_audit

PENDING_PHONE = "login_phone"
NEXT = "login_next"
QUESTIONNAIRE = "questionnaire_id"


def _safe_next(request: HttpRequest, url: str | None) -> str:
    if url and url_has_allowed_host_and_scheme(
        url, {request.get_host()}, require_https=request.is_secure()
    ):
        return url
    return "/"


@require_http_methods(["GET", "POST"])
def login_phone(request: HttpRequest) -> HttpResponse:
    form = PhoneForm(request.POST or None)
    status = 200
    if request.method == "GET":
        request.session[NEXT] = _safe_next(request, request.GET.get("next"))
    elif form.is_valid():
        phone = form.cleaned_data["phone"]
        outcome = services.request_code(phone, client_ip(request))
        if outcome is services.RequestOutcome.SENT:
            request.session[PENDING_PHONE] = phone
            return redirect("accounts:verify")
        form.add_error(
            None,
            _("الدخول مش متاح دلوقتي. جرّب تاني بعد شوية.")
            if outcome is services.RequestOutcome.DISABLED
            else _("طلبت أكواد كتير. استنى ربع ساعة وجرّب تاني."),
        )
        status = 429 if outcome is services.RequestOutcome.RATE_LIMITED else 503
    else:
        status = 422
    return render(request, "accounts/login.html", {"form": form}, status=status)


@require_http_methods(["GET", "POST"])
def verify(request: HttpRequest) -> HttpResponse:
    phone = request.session.get(PENDING_PHONE)
    if not phone:
        return redirect("accounts:login")
    form = CodeForm(request.POST or None)
    status = 200
    if request.method == "POST":
        status = 422
        if form.is_valid():
            result = services.verify_code(phone, form.cleaned_data["code"], client_ip(request))
            if result.outcome is services.VerifyOutcome.OK and result.user is not None:
                next_url = request.session.get(NEXT, "/")
                questionnaire_id = request.session.get(QUESTIONNAIRE)
                claim_questionnaire(questionnaire_id, request.session.session_key, result.user)
                login(request, result.user)  # rotates the session key
                request.session[QUESTIONNAIRE] = questionnaire_id
                record_audit(AuditAction.LOGIN, actor=result.user, request=request)
                return redirect(_safe_next(request, next_url))
            form.add_error(
                "code",
                {
                    services.VerifyOutcome.WRONG: _("الكود مش صح. راجعه وجرّب تاني."),
                    services.VerifyOutcome.EXPIRED: _("الكود خلص وقته. اطلب كود جديد."),
                    services.VerifyOutcome.LOCKED: _("محاولات كتير غلط. اطلب كود جديد بعد شوية."),
                }[result.outcome],
            )
            if result.outcome is services.VerifyOutcome.LOCKED:
                status = 429
    return render(
        request,
        "accounts/verify.html",
        {
            "form": form,
            "masked_phone": mask_phone(phone),
            "outbox": services.sender() is services.Sender.OUTBOX,
        },
        status=status,
    )


@require_POST
def logout_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        record_audit(AuditAction.LOGOUT, request=request)
    logout(request)
    return redirect("races:landing")
