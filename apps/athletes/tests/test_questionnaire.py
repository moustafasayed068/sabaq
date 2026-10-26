from datetime import date
from decimal import Decimal

import pytest
from django.test import Client
from django.utils import timezone

from apps.athletes.models import Questionnaire
from apps.athletes.services import plan_input
from engine import HEALTH_QUESTIONS, generate

HEALTH_IDS = [q.id for q in HEALTH_QUESTIONS]

pytestmark = pytest.mark.django_db

TODAY = date(2026, 10, 27)
ANSWERS: dict[str, dict[str, object]] = {
    "race": {"distance_km": "21.1", "start_date": "2026-10-27"},
    "you": {"age": "28", "sex": "m", "weight_kg": "72"},
    "running": {"runs_per_week": "3", "weekly_km": "20", "longest_km": "10"},
    "time": {"recent_km": "5.0", "recent_time_0": "", "recent_time_1": "28", "recent_time_2": "0", "goal": "finish"},
    "days": {"days": ["6", "1", "3", "5"], "where": "outdoor", "gps": "yes"},
    "consent": {"agree": "on"},
    "health": {**dict.fromkeys(HEALTH_IDS, "no"), "injury": "none", "pain": "none"},
}  # fmt: skip


@pytest.fixture(autouse=True)
def _today(monkeypatch):
    monkeypatch.setattr(timezone, "localdate", lambda: TODAY)


def start(client: Client, slug: str = "pyramids") -> Questionnaire:
    response = client.post(f"/start/{slug}/")
    assert response.status_code == 302
    assert response["Location"] == "/questions/race/"
    return Questionnaire.objects.latest("created_at")


def answer_all(client: Client, answers: dict[str, dict[str, object]] = ANSWERS) -> None:
    for step, data in answers.items():
        response = client.post(f"/questions/{step}/", data)
        assert response.status_code == 302, (step, response.content.decode()[-2000:])


def test_full_questionnaire_produces_the_golden_half_plan(client):
    q = start(client)
    answer_all(client)
    q.refresh_from_db()
    assert q.completed_steps == ["race", "you", "running", "time", "days", "consent", "health"]
    assert client.get("/questions/review/").status_code == 200
    inp = plan_input(q)
    assert inp.recent_time == "0:28:00"
    assert inp.distance_km == 21.1
    assert inp.days == (6, 1, 3, 5)
    plan = generate(inp)
    # Same answers as reference/engine-js/golden/half-intermediate.json.
    assert plan.status == "risky"
    assert plan.weeks[1].km == 22.7


def test_each_step_redirects_to_the_next_and_back_link_works(client):
    start(client)
    response = client.post("/questions/race/", ANSWERS["race"])
    assert response["Location"] == "/questions/you/"
    html = client.get("/questions/you/").content.decode()
    assert "خطوة" in html
    assert 'href="/questions/race/"' in html
    assert (
        'value="21.1" id="id_distance_km_2" checked'
        in client.get("/questions/race/").content.decode()
    )


def test_unfinished_review_goes_back_to_the_missing_step(client):
    start(client)
    client.post("/questions/race/", ANSWERS["race"])
    assert client.get("/questions/review/")["Location"] == "/questions/you/"


@pytest.mark.parametrize(
    ("step", "data", "error"),
    [
        ("race", {"start_date": "2026-10-27"}, "اختار المسافة."),
        (
            "race",
            {"distance_km": "42.2", "start_date": "2026-10-27"},
            "اختار من الاختيارات اللي قدامك.",
        ),
        ("race", {"distance_km": "10", "start_date": "2026-10-01"}, "اختار النهارده أو يوم بعده."),
        ("race", {"distance_km": "10", "start_date": "2026-12-12"}, "لازم تبدأ قبل يوم السباق."),
        ("you", {"age": "abc", "sex": "m"}, "اكتب رقم."),
        ("you", {"age": "5", "sex": "m"}, ""),
        ("running", {"runs_per_week": "3", "weekly_km": "10", "longest_km": "40"}, "راجع الرقمين"),
        ("time", {"recent_km": "5.0", "goal": "finish"}, "اكتب وقتك في السباق ده."),
        ("time", {"goal": "time"}, "اكتب الوقت اللي عايزه."),
        ("days", {"days": ["6", "1"], "where": "outdoor", "gps": "yes"}, "اختار من 3 لـ 6 أيام."),
    ],
)
def test_server_side_validation(client, step, data, error):
    start(client)
    response = client.post(f"/questions/{step}/", data)
    assert response.status_code == 422
    html = response.content.decode()
    assert 'class="errors"' in html
    assert error in html


def test_arabic_digits_are_accepted(client):
    q = start(client)
    client.post("/questions/you/", {"age": "٢٨", "sex": "f", "weight_kg": ""})
    client.post(
        "/questions/running/", {"runs_per_week": "3", "weekly_km": "٢١٫٥", "longest_km": "١٠"}
    )
    q.refresh_from_db()
    assert q.age == 28
    assert q.weekly_km == Decimal("21.5")
    assert q.weight_kg is None


def test_hyrox_has_no_distance_and_no_goal_time(client):
    q = start(client, "hyrox-dubai")
    html = client.get("/questions/race/").content.decode()
    assert "distance_km" not in html
    answers: dict[str, dict[str, object]] = {
        **ANSWERS,
        "race": {"start_date": "2026-10-27"},
        "time": {"recent_km": "", "goal": "finish"},
    }
    answer_all(client, answers)
    q.refresh_from_db()
    inp = plan_input(q)
    assert inp.race_type == "hyrox"
    assert inp.recent_time is None
    assert generate(inp).weeks


def test_starting_needs_post_and_an_upcoming_race(client, monkeypatch):
    assert client.get("/start/pyramids/").status_code == 405
    assert client.post("/start/nope/").status_code == 404
    assert client.post("/start/hyrox-cairo/").status_code == 302
    monkeypatch.setattr(timezone, "localdate", lambda: date(2026, 11, 14))
    assert client.post("/start/hyrox-cairo/").status_code == 404


def test_without_a_questionnaire_you_go_to_the_landing(client):
    assert client.get("/questions/race/")["Location"] == "/"
    assert client.get("/questions/review/")["Location"] == "/"
    start(client)
    assert client.get("/questions/nope/").status_code == 404


def test_athlete_b_cannot_see_or_change_athlete_a_answers(client):
    a = start(client)
    client.post("/questions/you/", {"age": "28", "sex": "m"})
    other = Client()
    other.cookies.load({})
    # B has their own session; even if they plant A's id in their session they get nothing.
    session = other.session
    session["questionnaire_id"] = str(a.pk)
    session.save()
    assert other.get("/questions/you/")["Location"] == "/"
    assert other.post("/questions/you/", {"age": "60", "sex": "f"})["Location"] == "/"
    a.refresh_from_db()
    assert (a.age, a.sex) == (28, "m")


def test_landing_card_starts_the_questionnaire(client):
    html = client.get("/").content.decode()
    assert 'action="/start/pyramids/"' in html


def test_signed_in_user_sees_only_their_own_questionnaire():
    from apps.accounts.models import User  # noqa: PLC0415
    from apps.athletes.selectors import questionnaire_for  # noqa: PLC0415
    from apps.races.models import Race  # noqa: PLC0415

    alice = User.objects.create_user("+201001234567")
    bob = User.objects.create_user("+201001234568")
    race = Race.objects.get(slug="pyramids")
    q = Questionnaire.objects.create(session_key="s-alice", race=race, user=alice)
    assert questionnaire_for(q.pk, session_key="other", user=alice) == q
    assert (
        questionnaire_for(q.pk, session_key="s-alice", user=bob) is None
    )  # claimed: session no longer enough
    assert questionnaire_for(q.pk, session_key=None, user=None) is None
    assert questionnaire_for(None, session_key="s-alice") is None
    assert str(q) == f"Questionnaire {q.pk} (pyramids)"


def test_plan_input_needs_a_finished_questionnaire():
    from apps.races.models import Race  # noqa: PLC0415

    q = Questionnaire.objects.create(session_key="s", race=Race.objects.get(slug="hyrox-dubai"))
    with pytest.raises(ValueError, match="not finished"):
        plan_input(q)


def test_answers_are_prefilled_when_coming_back(client):
    start(client)
    answer_all(client)
    time_html = client.get("/questions/time/").content.decode()
    assert 'value="5.0" id="id_recent_km_1" checked' in time_html
    assert 'value="28"' in time_html
    days_html = client.get("/questions/days/").content.decode()
    assert 'value="yes" id="id_gps_0" checked' in days_html
