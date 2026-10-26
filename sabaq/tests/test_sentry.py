from sabaq.sentry import init_sentry, scrub


def test_scrub_removes_personal_and_health_data():
    event = {
        "request": {
            "method": "POST",
            "url": "https://sabaq.example/plan/check-in/",
            "data": {"pain": "sharp"},
            "cookies": {"sessionid": "s"},
            "headers": {"Cookie": "x"},
            "query_string": "hmac=abc",
        },
        "user": {"id": "u", "ip_address": "1.2.3.4"},
        "extra": {"phone": "+201001234567"},
        "exception": {
            "values": [{"stacktrace": {"frames": [{"function": "f", "vars": {"q": "secret"}}]}}]
        },
        "breadcrumbs": {"values": [{"message": "SELECT", "data": {"params": ["+20100"]}}]},
    }
    out = scrub(event)
    assert out["request"] == {"method": "POST", "url": "https://sabaq.example/plan/check-in/"}
    assert "user" not in out
    assert "extra" not in out
    assert "vars" not in out["exception"]["values"][0]["stacktrace"]["frames"][0]
    assert "data" not in out["breadcrumbs"]["values"][0]
    text = repr(out)
    for secret in ("sharp", "sessionid", "hmac", "+2010", "1.2.3.4", "secret"):
        assert secret not in text


def test_scrub_handles_sparse_events():
    assert scrub({}) == {}
    assert scrub({"exception": {"values": [{}]}, "breadcrumbs": {}}) is not None


def test_sentry_is_off_without_a_dsn():
    assert init_sentry("", environment="test") is False
