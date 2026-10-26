import pytest
from django.conf import settings

from apps.accounts.models import User
from apps.core.models import AuditEvent, FeatureFlag
from apps.core.services import AuditAction, record_audit

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff_client(client):
    admin = User.objects.create_superuser("+201001234500", password="a-long-staff-password")
    client.force_login(admin)
    return client


def test_audit_log_is_read_only_in_admin(staff_client):
    event = record_audit(AuditAction.LOGIN)
    base = f"/{settings.ADMIN_URL}core/auditevent/"
    assert staff_client.get(base).status_code == 200
    assert staff_client.get(f"{base}add/").status_code == 403
    assert staff_client.post(f"{base}{event.pk}/delete/").status_code == 403
    assert AuditEvent.objects.filter(pk=event.pk).exists()


def test_changing_a_flag_in_admin_is_audited(staff_client):
    url = f"/{settings.ADMIN_URL}core/featureflag/add/"
    response = staff_client.post(url, {"name": "payments", "enabled": "on", "description": ""})
    assert response.status_code == 302
    flag = FeatureFlag.objects.get(name="payments")
    event = AuditEvent.objects.get(action=AuditAction.FEATURE_FLAG_CHANGED)
    assert event.target_id == str(flag.pk)
    assert event.metadata == {"name": "payments", "enabled": True}
