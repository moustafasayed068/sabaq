"""Checkout page, the start button, the page Paymob sends the athlete back to, and the
server-to-server callback. Only the callback can unlock a plan."""

from __future__ import annotations

import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.core import ratelimit
from apps.core.request_context import client_ip
from apps.payments import services
from apps.plans.selectors import active_plan

log = logging.getLogger(__name__)

LAST_ORDER = "last_order_id"
CALLBACKS_PER_MINUTE_PER_IP = 120


@require_GET
@login_required
def checkout(request: HttpRequest) -> HttpResponse:
    plan = active_plan(request.user)  # type: ignore[arg-type]
    if plan is None:
        return redirect("races:landing")
    if plan.paid_at is not None:
        return redirect("plans:mine")
    return render(
        request,
        "payments/checkout.html",
        {
            "plan": plan,
            "price": services.price_for_plan(plan),
            "is_open": services.is_open(),
            "error": request.GET.get("error") == "1",
        },
    )


@require_POST
@login_required
def start(request: HttpRequest) -> HttpResponse:
    plan = active_plan(request.user)  # type: ignore[arg-type]
    if plan is None:
        return redirect("races:landing")
    if plan.paid_at is not None:
        return redirect("plans:mine")
    try:
        order, url = services.start_checkout(
            request.user,  # type: ignore[arg-type]
            plan,
            notification_url=request.build_absolute_uri(reverse("payments:callback")),
            redirection_url=request.build_absolute_uri(reverse("payments:done")),
        )
    except services.CheckoutError:
        return redirect(f"{reverse('payments:checkout')}?error=1")
    request.session[LAST_ORDER] = str(order.pk)
    return HttpResponseRedirect(url)


@require_GET
@login_required
def done(request: HttpRequest) -> HttpResponse:
    """Paymob's redirect back. Its query string is ignored: we show what the callback recorded."""
    order = services.order_for(request.user, request.session.get(LAST_ORDER))  # type: ignore[arg-type]
    if order is None:
        return redirect("plans:mine")
    return render(request, "payments/done.html", {"order": order})


@csrf_exempt  # Paymob posts server-to-server; the HMAC is the authentication.
@require_POST
def callback(request: HttpRequest) -> HttpResponse:
    ip = client_ip(request) or "unknown"
    if not ratelimit.hit(f"paymob:ip:{ip}", limit=CALLBACKS_PER_MINUTE_PER_IP, window_s=60):
        return HttpResponse(status=429)
    try:
        payload = json.loads(request.body or b"null")
    except ValueError:
        return HttpResponse(status=400)
    result = services.handle_callback(payload, request.GET.get("hmac", ""))
    log.info("payments.callback", extra={"result": result.value})
    if result is services.CallbackResult.REJECTED:
        return HttpResponse(status=401)
    return HttpResponse(status=200)
