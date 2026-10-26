"""Data retention (docs/security.md): health answers, injuries, pain and sickness check-ins are
kept until the athlete's last plan ends plus 12 months, then deleted. Answers from people who
never signed up are deleted once their session can no longer reach them."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import DateField, Max, OuterRef, Subquery
from django.db.models.functions import Coalesce, Greatest, TruncDate
from django.utils import timezone

from apps.accounts.models import User
from apps.athletes.models import HealthScreen, Questionnaire
from apps.plans.models import CheckIn, DayLog, Plan

log = logging.getLogger(__name__)

HEALTH_KEPT_FOR = timedelta(days=365)


@dataclass(frozen=True)
class RetentionResult:
    athletes: int
    health_screens: int
    check_ins: int
    day_logs: int
    plan_inputs: int
    anonymous_questionnaires: int


def expired_athletes(today: date) -> list[object]:
    """Athletes whose last plan ended (or, with no plan, whose last answers were given)
    more than 12 months ago."""
    last_race = (
        Plan.objects.filter(user=OuterRef("pk"))
        .values("user")
        .annotate(last=Max("race_date"))
        .values("last")
    )
    last_answers = (
        Questionnaire.objects.filter(user=OuterRef("pk"))
        .values("user")
        .annotate(last=Max(TruncDate("created_at")))
        .values("last")
    )
    cutoff = today - HEALTH_KEPT_FOR
    race = Subquery(last_race, output_field=DateField())
    answers = Subquery(last_answers, output_field=DateField())
    # The later of the two; NULL-safe on both PostgreSQL and SQLite.
    users = User.objects.annotate(
        last_seen=Greatest(Coalesce(race, answers), Coalesce(answers, race))
    ).filter(last_seen__lt=cutoff)
    return list(users.values_list("pk", flat=True))


@transaction.atomic
def apply_retention(today: date | None = None) -> RetentionResult:
    today = today or timezone.localdate()
    ids = expired_athletes(today)
    health, _ = HealthScreen.objects.filter(questionnaire__user_id__in=ids).delete()
    check_ins, _ = CheckIn.objects.filter(plan__user_id__in=ids).delete()
    day_logs, _ = DayLog.objects.filter(plan__user_id__in=ids).delete()
    # The stored engine input holds the health answers too; the plan summary stays.
    inputs = 0
    for plan in Plan.objects.filter(user_id__in=ids):
        if plan.engine_input:
            plan.engine_input = {}
            plan.save(update_fields=["engine_input", "updated_at"])
            inputs += 1
    stale = timezone.now() - timedelta(seconds=settings.SESSION_COOKIE_AGE)
    _, removed = Questionnaire.objects.filter(user__isnull=True, created_at__lt=stale).delete()
    anonymous = removed.get("athletes.Questionnaire", 0)
    result = RetentionResult(len(ids), health, check_ins, day_logs, inputs, anonymous)
    log.info("retention.applied", extra=result.__dict__)
    return result
