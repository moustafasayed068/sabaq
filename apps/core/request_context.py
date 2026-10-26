"""Request id kept in a context variable, so logs and audit events can carry it."""

import re
import uuid
from collections.abc import Callable
from contextvars import ContextVar

from django.conf import settings
from django.http import HttpRequest, HttpResponse

request_id_var: ContextVar[str] = ContextVar("request_id", default="")
HEADER = "X-Request-ID"
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def get_request_id() -> str:
    return request_id_var.get()


class RequestIdMiddleware:
    """Reuse a safe incoming X-Request-ID (from Caddy) or make one; echo it on the response."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming = request.headers.get(HEADER, "")
        request_id = incoming if _SAFE_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        try:
            response = self.get_response(request)
        finally:
            request_id_var.reset(token)
        response[HEADER] = request_id
        return response


def client_ip(request: HttpRequest) -> str | None:
    """The client address. Behind our own proxy, trust only the hop the proxy appended."""
    if getattr(settings, "TRUST_X_FORWARDED_FOR", False):
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[-1].strip() or None
    return request.META.get("REMOTE_ADDR") or None
