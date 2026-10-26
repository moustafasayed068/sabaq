import pytest
from django.core.exceptions import ImproperlyConfigured

from sabaq.env import env_bool, env_int, env_list, env_str


def test_env_str(monkeypatch):
    monkeypatch.setenv("X_STR", "hello")
    assert env_str("X_STR") == "hello"
    monkeypatch.delenv("X_STR")
    assert env_str("X_STR", "fallback") == "fallback"
    with pytest.raises(ImproperlyConfigured, match="X_STR"):
        env_str("X_STR")


@pytest.mark.parametrize(
    ("raw", "expected"), [("1", True), ("True", True), ("off", False), ("", False)]
)
def test_env_bool(monkeypatch, raw, expected):
    monkeypatch.setenv("X_BOOL", raw)
    assert env_bool("X_BOOL", not expected) is expected


def test_env_bool_default_and_error(monkeypatch):
    monkeypatch.delenv("X_BOOL", raising=False)
    assert env_bool("X_BOOL", True) is True
    monkeypatch.setenv("X_BOOL", "maybe")
    with pytest.raises(ImproperlyConfigured):
        env_bool("X_BOOL", False)


def test_env_int(monkeypatch):
    monkeypatch.delenv("X_INT", raising=False)
    assert env_int("X_INT", 3) == 3
    monkeypatch.setenv("X_INT", "42")
    assert env_int("X_INT", 3) == 42
    monkeypatch.setenv("X_INT", "four")
    with pytest.raises(ImproperlyConfigured):
        env_int("X_INT", 3)


def test_env_list(monkeypatch):
    monkeypatch.delenv("X_LIST", raising=False)
    assert env_list("X_LIST") == []
    assert env_list("X_LIST", ["a"]) == ["a"]
    monkeypatch.setenv("X_LIST", "a.com, b.com,,")
    assert env_list("X_LIST") == ["a.com", "b.com"]
