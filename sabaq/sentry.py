"""Error tracking (Sentry), on only when SENTRY_DSN is set. Health data, phone numbers and
tokens must never leave the server, so events carry no request body, cookies, headers,
query strings, user, or local variables (docs/security.md, docs/architecture.md)."""

from __future__ import annotations

from typing import Any

import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration

_KEEP_REQUEST_KEYS = ("method", "url")


def scrub(event: dict[str, Any], hint: dict[str, Any] | None = None) -> dict[str, Any]:
    request = event.get("request")
    if isinstance(request, dict):
        event["request"] = {k: request[k] for k in _KEEP_REQUEST_KEYS if k in request}
    event.pop("user", None)
    event.pop("extra", None)
    for exc in (event.get("exception") or {}).get("values") or []:
        for frame in (exc.get("stacktrace") or {}).get("frames") or []:
            frame.pop("vars", None)
    for crumb in (event.get("breadcrumbs") or {}).get("values") or []:
        crumb.pop("data", None)
    return event


def init_sentry(dsn: str, *, environment: str, release: str = "") -> bool:
    if not dsn:
        return False
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release or None,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        traces_sample_rate=0.0,
        before_send=scrub,  # type: ignore[arg-type]
    )
    return True
