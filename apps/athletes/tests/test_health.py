import pytest
from cryptography.fernet import Fernet
from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ImproperlyConfigured
from django.db import connection

from apps.accounts.models import User
from apps.athletes.consent import HEALTH_CONSENT_TEXT, HEALTH_CONSENT_VERSION, text_sha256
from apps.athletes.models import Consent, HealthScreen, Questionnaire
from apps.athletes.services import plan_input
from apps.athletes.tests.test_questionnaire import ANSWERS, HEALTH_IDS, answer_all, start
from apps.core import crypto
from apps.core.models import AuditEvent
from apps.core.services import AuditAction
from engine import generate

pytestmark = pytest.mark.django_db

YES_CHEST = {**ANSWERS["health"], "chestActive": "yes"}


def finish(client, health=None):
    answers = dict(ANSWERS)
    if health is not None:
        answers["health"] = health
    q = start(client)
    answer_all(client, answers)
    q.refresh_from_db()
    return q


def test_health_answers_are_encrypted_at_rest(client):
    q = finish(client, YES_CHEST)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT data FROM athletes_healthscreen WHERE questionnaire_id = %s",
            [q.pk.hex if connection.vendor == "sqlite" else q.pk],
        )
        raw = cursor.fetchone()[0]
    assert raw.startswith("gAAAAA")  # Fernet token
    for word in ("chestActive", "true", "injury", "pain"):
        assert word not in raw
    assert HealthScreen.objects.get(questionnaire=q).data["answers"]["chestActive"] is True


def test_encrypted_fields_cannot_be_queried():
    with pytest.raises(NotImplementedError):
        HealthScreen.objects.filter(**{"data__contains": "x"}).count()
    assert HealthScreen.objects.filter(**{"data__isnull": True}).count() == 0


def test_consent_is_recorded_with_its_text_version(client):
    q = finish(client)
    consent = Consent.objects.get(questionnaire=q)
    assert consent.text_version == HEALTH_CONSENT_VERSION
    assert consent.text_sha256 == text_sha256(HEALTH_CONSENT_TEXT)
    client.post("/questions/consent/", {"agree": "on"})
    assert Consent.objects.filter(questionnaire=q).count() == 1  # not duplicated
    assert str(consent) == f"health consent {HEALTH_CONSENT_VERSION}"


def test_health_questions_need_consent_first(client):
    start(client)
    assert client.get("/questions/health/")["Location"] == "/questions/consent/"
    response = client.post("/questions/consent/", {})
    assert response.status_code == 422
    assert "لازم توافق عشان نكمّل." in response.content.decode()
    assert HEALTH_CONSENT_TEXT[:20] in response.content.decode()


def test_any_yes_blocks_the_plan_until_a_doctor_clears(client):
    q = finish(client, YES_CHEST)
    plan = generate(plan_input(q))
    assert (plan.status, plan.block_kind) == ("blocked", "health")
    assert "محتاج موافقة دكتور" in client.get("/questions/review/").content.decode()
    client.post("/questions/health/", {**YES_CHEST, "doctor_cleared": "on"})
    assert generate(plan_input(q)).status != "blocked"


def test_pain_now_and_knee_history_reach_the_engine(client):
    q = finish(client, {**ANSWERS["health"], "pain": "now", "injury": "knee"})
    inp = plan_input(q)
    assert (inp.pain, inp.injury) == ("now", "knee")
    assert generate(inp).block_kind == "pain"


def test_every_health_question_is_required(client):
    start(client)
    client.post("/questions/consent/", {"agree": "on"})
    response = client.post("/questions/health/", {"injury": "none", "pain": "none"})
    assert response.status_code == 422
    assert response.content.decode().count("جاوب بأيوه أو لأ.") == len(HEALTH_IDS)


def test_health_answers_prefill(client):
    finish(client, YES_CHEST)
    html = client.get("/questions/health/").content.decode()
    assert 'name="chestActive" value="yes" id="id_chestActive_1" checked' in html


# ---------------------------------------------------------------- staff access


@pytest.fixture
def screen(client):
    q = finish(client, YES_CHEST)
    return HealthScreen.objects.get(questionnaire=q)


def staff(phone: str, *, health_viewer: bool) -> User:
    user = User.objects.create_user(phone, password="a-long-staff-password", is_staff=True)
    if health_viewer:
        group, _ = Group.objects.get_or_create(name="health_viewer")
        group.permissions.add(Permission.objects.get(codename="view_health_answers"))
        user.groups.add(group)
    return user


def test_staff_without_the_role_cannot_see_health_answers(client, screen):
    support = staff("+201001234590", health_viewer=False)
    client.force_login(support)
    url = f"/{settings.ADMIN_URL}athletes/healthscreen/{screen.pk}/change/"
    assert client.get(url).status_code in (302, 403)
    assert not AuditEvent.objects.filter(action=AuditAction.HEALTH_DATA_VIEWED).exists()


def test_health_viewer_sees_answers_and_every_view_is_audited(client, screen):
    viewer = staff("+201001234591", health_viewer=True)
    client.force_login(viewer)
    url = f"/{settings.ADMIN_URL}athletes/healthscreen/{screen.pk}/change/"
    assert client.get(url).status_code == 200
    client.get(url)
    events = AuditEvent.objects.filter(action=AuditAction.HEALTH_DATA_VIEWED)
    assert events.count() == 2
    assert {e.actor for e in events} == {viewer}
    assert all(e.target_id == str(screen.pk) for e in events)
    assert client.get(f"/{settings.ADMIN_URL}athletes/healthscreen/add/").status_code == 403


# ---------------------------------------------------------------- keys


def test_key_rotation_keeps_old_data_readable(settings, screen):
    new_key = Fernet.generate_key().decode()
    settings.FIELD_ENCRYPTION_KEYS = [new_key, *settings.FIELD_ENCRYPTION_KEYS]
    crypto.reset_keys_cache()
    try:
        assert HealthScreen.objects.get(pk=screen.pk).data["answers"]["chestActive"] is True
        token = crypto.encrypt(b"x")
        assert crypto.decrypt(crypto.rotate(token)) == b"x"
    finally:
        crypto.reset_keys_cache()


def test_missing_or_bad_keys_fail_loudly(settings):
    settings.FIELD_ENCRYPTION_KEYS = []
    crypto.reset_keys_cache()
    with pytest.raises(ImproperlyConfigured):
        crypto.encrypt(b"x")
    settings.FIELD_ENCRYPTION_KEYS = ["not-a-key"]
    crypto.reset_keys_cache()
    with pytest.raises(ImproperlyConfigured):
        crypto.encrypt(b"x")
    crypto.reset_keys_cache()


def test_wrong_key_cannot_decrypt(settings):
    token = crypto.encrypt(b"secret")
    settings.FIELD_ENCRYPTION_KEYS = [Fernet.generate_key().decode()]
    crypto.reset_keys_cache()
    try:
        with pytest.raises(ImproperlyConfigured):
            crypto.decrypt(token)
    finally:
        crypto.reset_keys_cache()


def test_questionnaire_delete_removes_health_data(screen):
    Questionnaire.objects.filter(pk=screen.questionnaire_id).delete()
    assert not HealthScreen.objects.exists()
    assert not Consent.objects.exists()


def test_rotate_field_keys_reencrypts_with_the_newest_key(settings, screen, capsys):
    from django.core.management import call_command  # noqa: PLC0415

    old = list(settings.FIELD_ENCRYPTION_KEYS)
    new_key = Fernet.generate_key().decode()
    settings.FIELD_ENCRYPTION_KEYS = [new_key, *old]
    crypto.reset_keys_cache()
    try:
        call_command("rotate_field_keys")
        assert "re-encrypted 1 rows" in capsys.readouterr().out
        settings.FIELD_ENCRYPTION_KEYS = [new_key]  # old key removed
        crypto.reset_keys_cache()
        assert HealthScreen.objects.get(pk=screen.pk).data["answers"]["chestActive"] is True
    finally:
        settings.FIELD_ENCRYPTION_KEYS = old
        crypto.reset_keys_cache()
