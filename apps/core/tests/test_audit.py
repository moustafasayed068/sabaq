import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from apps.accounts.models import User
from apps.core.models import AppendOnlyError, AuditEvent, FeatureFlag
from apps.core.request_context import client_ip, request_id_var
from apps.core.services import AuditAction, record_audit

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return User.objects.create_user("+201001234567")


def test_record_audit_with_request_takes_actor_ip_and_request_id(user, rf: RequestFactory):
    request = rf.get("/", REMOTE_ADDR="203.0.113.7")
    request.user = user
    token = request_id_var.set("req-12345678")
    try:
        event = record_audit(AuditAction.LOGIN, request=request, metadata={"method": "code"})
    finally:
        request_id_var.reset(token)
    event.refresh_from_db()
    assert event.actor == user
    assert event.ip_address == "203.0.113.7"
    assert event.request_id == "req-12345678"
    assert event.metadata == {"method": "code"}


def test_record_audit_target_and_anonymous(rf: RequestFactory):
    flag = FeatureFlag.objects.create(name="x")
    request = rf.get("/")
    request.user = AnonymousUser()
    event = record_audit(AuditAction.FEATURE_FLAG_CHANGED, target=flag, request=request)
    assert event.actor is None
    assert event.target_type == "core.featureflag"
    assert event.target_id == str(flag.pk)
    assert str(event) == f"feature_flag_changed core.featureflag:{flag.pk}"


def test_record_audit_without_request(user):
    event = record_audit(AuditAction.ACCOUNT_DELETED, actor=user)
    assert event.ip_address is None
    assert event.actor == user


def test_audit_events_are_append_only(user):
    event = record_audit(AuditAction.LOGIN, actor=user)
    event.action = AuditAction.LOGOUT
    with pytest.raises(AppendOnlyError):
        event.save()
    with pytest.raises(AppendOnlyError):
        event.delete()
    with pytest.raises(AppendOnlyError):
        AuditEvent.objects.filter(pk=event.pk).update(action="logout")
    with pytest.raises(AppendOnlyError):
        AuditEvent.objects.all().delete()
    assert AuditEvent.objects.get(pk=event.pk).action == AuditAction.LOGIN


def test_trusted_proxy_ip(settings, rf: RequestFactory):
    request = rf.get("/", REMOTE_ADDR="10.0.0.2", HTTP_X_FORWARDED_FOR="1.1.1.1, 198.51.100.4")
    assert client_ip(request) == "10.0.0.2"
    settings.TRUST_X_FORWARDED_FOR = True
    assert client_ip(request) == "198.51.100.4"
