import re
from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.accounts import services
from apps.accounts.models import LoginCode, User
from apps.accounts.phone import normalize_phone
from apps.athletes.models import Questionnaire
from apps.core.models import AuditEvent
from apps.core.services import AuditAction

pytestmark = pytest.mark.django_db
PHONE = "+201001234567"


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()


@pytest.fixture
def codes(caplog):
    """Read dev codes from the log (the console sender)."""

    def last() -> str:
        found = re.findall(r"DEV login code for \S+: (\d{6})", caplog.text)
        assert found, "no code logged"
        return str(found[-1])

    return last


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("01001234567", PHONE), ("010 0123 4567", PHONE), ("+20 100 123 4567", PHONE),
     ("00201001234567", PHONE), ("٠١٠٠١٢٣٤٥٦٧", PHONE), ("+971501234567", "+971501234567")],
)  # fmt: skip
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["0100123456", "01301234567", "+20130123456", "abc", "", "+1"])
def test_normalize_phone_rejects(raw):
    with pytest.raises(ValidationError):
        normalize_phone(raw)


def login(client, codes, phone="01001234567", next_url=None):
    url = "/login/" + (f"?next={next_url}" if next_url else "")
    client.get(url)
    response = client.post("/login/", {"phone": phone})
    assert response["Location"] == "/login/code/"
    return client.post("/login/code/", {"code": codes()})


def test_login_creates_a_verified_athlete_and_rotates_the_session(client, codes):
    client.get("/login/")
    before = client.session.session_key
    response = login(client, codes)
    assert response.status_code == 302
    user = User.objects.get(phone=PHONE)
    assert user.phone_verified_at is not None
    assert not user.has_usable_password()
    assert client.session.session_key != before
    assert int(client.session["_auth_user_id"].replace("-", ""), 16) == user.pk.int
    assert AuditEvent.objects.filter(action=AuditAction.LOGIN, actor=user).exists()


def test_codes_are_hashed_and_single_use(client, codes):
    client.post("/login/", {"phone": "01001234567"})
    code = codes()
    stored = LoginCode.objects.get()
    assert code not in stored.code_hash
    assert stored.outbox is None  # console sender keeps nothing readable
    assert client.post("/login/code/", {"code": code}).status_code == 302
    client.post("/logout/")
    client.post("/login/", {"phone": "01001234567"})
    assert services.verify_code(PHONE, code, None).outcome is services.VerifyOutcome.WRONG


def test_wrong_code_is_counted_and_locks_after_five(client, codes):
    client.post("/login/", {"phone": "01001234567"})
    good = codes()
    wrong = "000000" if good != "000000" else "111111"
    for _ in range(4):
        response = client.post("/login/code/", {"code": wrong})
        assert response.status_code == 422
        assert "الكود مش صح" in response.content.decode()
    response = client.post("/login/code/", {"code": wrong})
    assert response.status_code == 429
    assert (
        client.post("/login/code/", {"code": good}).status_code == 429
    )  # locked even with the right code
    assert AuditEvent.objects.filter(action=AuditAction.LOGIN_CODE_FAILED).count() == 5


def test_expired_code(client, codes):
    client.post("/login/", {"phone": "01001234567"})
    code = codes()
    LoginCode.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    assert "الكود خلص وقته" in client.post("/login/code/", {"code": code}).content.decode()


def test_only_the_newest_code_works(client, codes):
    client.post("/login/", {"phone": "01001234567"})
    first = codes()
    client.post("/login/", {"phone": "01001234567"})
    second = codes()
    if first != second:
        assert services.verify_code(PHONE, first, None).outcome is services.VerifyOutcome.WRONG
    assert services.verify_code(PHONE, second, None).outcome is services.VerifyOutcome.OK


def test_codes_are_rate_limited_per_phone_and_per_ip(client):
    for _ in range(3):
        assert client.post("/login/", {"phone": "01001234567"}).status_code == 302
    response = client.post("/login/", {"phone": "01001234567"})
    assert response.status_code == 429
    assert "طلبت أكواد كتير" in response.content.decode()
    for n in range(7):
        client.post("/login/", {"phone": f"0100123450{n}"})
    assert client.post("/login/", {"phone": "01001234599"}).status_code == 429  # 10 per IP per hour


def test_phone_lockout_after_many_failures(settings):
    settings.LOGIN_CODE_SENDER = "outbox"
    for i in range(services.FAILURES_PER_PHONE[0]):
        if i % 4 == 0:  # a fresh code before the per-code limit (5) is reached
            cache.delete(f"rl:code:phone:{PHONE}")
            services.request_code(PHONE, f"10.0.0.{i}")
        assert services.verify_code(PHONE, "999999", None).outcome is not services.VerifyOutcome.OK
    cache.delete(f"rl:code:phone:{PHONE}")
    services.request_code(PHONE, "10.0.1.1")
    right = LoginCode.objects.filter(used_at__isnull=True).get().outbox["code"]
    assert services.verify_code(PHONE, right, None).outcome is services.VerifyOutcome.LOCKED


def test_disabled_sender(client, settings):
    settings.LOGIN_CODE_SENDER = "disabled"
    response = client.post("/login/", {"phone": "01001234567"})
    assert response.status_code == 503
    assert "الدخول مش متاح دلوقتي" in response.content.decode()
    assert not LoginCode.objects.exists()


def test_invalid_phone_and_code_forms(client):
    assert client.post("/login/", {"phone": "123"}).status_code == 422
    assert client.get("/login/code/")["Location"] == "/login/"
    client.post("/login/", {"phone": "01001234567"})
    assert "الكود 6 أرقام" in client.post("/login/code/", {"code": "12"}).content.decode()
    assert "الكود أرقام بس" in client.post("/login/code/", {"code": "12345a"}).content.decode()


def test_next_is_kept_but_never_an_open_redirect(client, codes):
    assert login(client, codes, next_url="/questions/review/")["Location"] == "/questions/review/"
    client.post("/logout/")
    assert login(client, codes, next_url="https://evil.example/")["Location"] == "/"


def test_logout_needs_post_and_is_audited(client, codes):
    login(client, codes)
    assert client.get("/logout/").status_code == 405
    assert client.post("/logout/")["Location"] == "/"
    assert "_auth_user_id" not in client.session
    assert AuditEvent.objects.filter(action=AuditAction.LOGOUT).count() == 1


def test_signing_in_claims_the_anonymous_questionnaire(client, codes):
    client.post("/start/pyramids/")
    q = Questionnaire.objects.get()
    login(client, codes)
    q.refresh_from_db()
    assert q.user == User.objects.get(phone=PHONE)
    # Still reachable after the session key rotated.
    assert client.get("/questions/race/").status_code == 200


def test_a_claimed_questionnaire_is_not_stolen_by_another_login(client, codes):
    client.post("/start/pyramids/")
    q = Questionnaire.objects.get()
    login(client, codes)
    other = User.objects.create_user("+201001234568")
    from apps.athletes.services import claim_questionnaire  # noqa: PLC0415

    claim_questionnaire(str(q.pk), q.session_key, other)
    q.refresh_from_db()
    assert q.user is not None
    assert q.user.phone == PHONE


# ---------------------------------------------------------------- outbox (beta: staff send codes)


def test_outbox_code_is_visible_only_to_permitted_staff_and_audited(client, settings):
    settings.LOGIN_CODE_SENDER = "outbox"
    client.post("/login/", {"phone": "01001234567"})
    code = LoginCode.objects.get()
    assert len(code.outbox["code"]) == 6

    staff = User.objects.create_user(
        "+201001234500", password="a-long-staff-password", is_staff=True
    )
    client.force_login(staff)
    url = f"/{settings.ADMIN_URL}accounts/logincode/{code.pk}/change/"
    assert client.get(url).status_code in (302, 403)
    staff.user_permissions.add(Permission.objects.get(codename="send_login_codes"))
    staff = User.objects.get(pk=staff.pk)
    client.force_login(staff)
    html = client.get(url).content.decode()
    assert code.outbox["code"] in html
    assert AuditEvent.objects.filter(action=AuditAction.LOGIN_CODE_VIEWED).count() == 1

    assert (
        services.verify_code(PHONE, code.outbox["code"], None).outcome is services.VerifyOutcome.OK
    )
    code.refresh_from_db()
    assert code.outbox is None  # wiped once used
    assert "—" in client.get(url).content.decode()
    assert str(code) == "Login code for +2010******67"
