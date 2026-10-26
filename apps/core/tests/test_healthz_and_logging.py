import json
import logging
import sys
from unittest import mock

import pytest

from apps.core.logging import JsonFormatter, RequestIdFilter
from apps.core.request_context import request_id_var

pytestmark = pytest.mark.django_db


def test_healthz_ok_and_has_no_data(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": True, "cache": True}
    assert "no-cache" in response["Cache-Control"]


def test_healthz_fails_when_database_is_down(client):
    with mock.patch("apps.core.views.connection.cursor", side_effect=Exception("down")):
        response = client.get("/healthz")
    assert response.status_code == 503
    assert response.json()["database"] is False


def test_healthz_fails_when_cache_is_down(client):
    with mock.patch("apps.core.views.cache.set", side_effect=Exception("down")):
        response = client.get("/healthz")
    assert response.status_code == 503
    assert response.json()["cache"] is False


def test_healthz_get_only(client):
    assert client.post("/healthz").status_code == 405


def test_request_id_is_generated_or_reused(client):
    generated = client.get("/healthz")["X-Request-ID"]
    assert len(generated) == 32
    assert (
        client.get("/healthz", HTTP_X_REQUEST_ID="abc-12345678")["X-Request-ID"] == "abc-12345678"
    )
    unsafe = client.get("/healthz", HTTP_X_REQUEST_ID="<script>")["X-Request-ID"]
    assert unsafe != "<script>"


def _record(**extra):
    record = logging.LogRecord("sabaq.test", logging.INFO, __file__, 1, "hello %s", ("you",), None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_json_formatter_has_request_id_and_drops_unknown_extras():
    token = request_id_var.set("req-abcdefgh")
    try:
        record = _record(event="plan_generated", phone="+201001234567")
        RequestIdFilter().filter(record)
        payload = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)
    assert payload["message"] == "hello you"
    assert payload["request_id"] == "req-abcdefgh"
    assert payload["event"] == "plan_generated"
    assert "phone" not in payload
    assert "+201001234567" not in json.dumps(payload)


def test_json_formatter_includes_exceptions():
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord("x", logging.ERROR, __file__, 1, "failed", (), sys.exc_info())
    payload = json.loads(JsonFormatter().format(record))
    assert "ValueError: boom" in payload["exc"]
