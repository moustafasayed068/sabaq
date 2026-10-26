"""Key pages run a fixed, small number of queries however long the plan is (no N+1)."""

from datetime import timedelta

import pytest

from apps.plans.tests.test_check_in import WEEK1_START, make_plan, on

pytestmark = pytest.mark.django_db


@pytest.fixture
def plan(client, monkeypatch):
    p = make_plan(client, monkeypatch)
    on(monkeypatch, WEEK1_START + timedelta(days=5))  # check-in open
    return p


def test_plan_page(client, plan, django_assert_max_num_queries):
    with django_assert_max_num_queries(7):
        assert client.get("/plan/").status_code == 200


def test_day_page(client, plan, django_assert_max_num_queries):
    day = plan.days.exclude(kind="").first().date
    with django_assert_max_num_queries(6):
        assert client.get(f"/plan/day/{day.isoformat()}/").status_code == 200


def test_check_in_page(client, plan, django_assert_max_num_queries):
    with django_assert_max_num_queries(6):
        assert client.get("/plan/check-in/").status_code == 200
