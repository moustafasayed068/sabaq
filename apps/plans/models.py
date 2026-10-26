"""Plans are stored as generated: weeks and days as rows, plus the exact (encrypted)
engine input and engine version. Old plans never change when the engine does."""

from __future__ import annotations

from typing import ClassVar

from django.conf import settings
from django.db import models

from apps.athletes.models import Questionnaire
from apps.core.crypto import EncryptedJSONField
from apps.core.models import BaseModel
from apps.races.models import Race


class PlanStatus(models.TextChoices):
    OK = "ok"
    RISKY = "risky"


class Plan(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="plans"
    )
    questionnaire = models.ForeignKey(Questionnaire, on_delete=models.CASCADE, related_name="plans")
    race = models.ForeignKey(Race, on_delete=models.PROTECT, related_name="+")
    distance_km = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    race_date = models.DateField()
    starts_on = models.DateField()
    engine_version = models.CharField(max_length=20)
    # PlanInput.to_dict(): includes health answers, so it is encrypted.
    engine_input = EncryptedJSONField()
    status = models.CharField(max_length=10, choices=PlanStatus.choices)
    level = models.CharField(max_length=20)
    messages = models.JSONField(default=list)
    warnings = models.JSONField(default=list)
    # Paces, peak long run, goal verdict, time read, race-day tips: shown, never queried.
    summary = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    # Set only by a verified payment webhook (M2). Until then only week 1 is open.
    paid_at = models.DateTimeField(null=True, blank=True)
    # Set by a check-in with sharp pain; cleared when the athlete says a doctor cleared them.
    paused_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]
        indexes: ClassVar[list[models.Index]] = [
            models.Index(fields=["user", "is_active"], name="plans_user_active_idx"),
        ]

    def __str__(self) -> str:
        return f"Plan {self.pk} ({self.race.slug}, engine {self.engine_version})"


class PlanWeek(BaseModel):
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="weeks")
    index = models.PositiveSmallIntegerField()
    start = models.DateField()
    phase = models.CharField(max_length=10)
    phase_name = models.CharField(max_length=40)
    target_km = models.PositiveSmallIntegerField(null=True, blank=True)
    km = models.DecimalField(max_digits=5, decimal_places=1)

    class Meta:
        ordering: ClassVar[list[str]] = ["index"]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(fields=["plan", "index"], name="plans_unique_week"),
        ]

    def __str__(self) -> str:
        return f"Week {self.index + 1}"


class PlanDay(BaseModel):
    week = models.ForeignKey(PlanWeek, on_delete=models.CASCADE, related_name="days")
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="days")
    date = models.DateField()
    day_name = models.CharField(max_length=10)
    role = models.CharField(max_length=12)
    kind = models.CharField(max_length=10, blank=True)
    title = models.CharField(max_length=120, blank=True)
    intensity = models.PositiveSmallIntegerField(default=0)
    km = models.DecimalField(max_digits=4, decimal_places=1, default=0)
    steps = models.JSONField(default=list)
    extra = models.JSONField(null=True, blank=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["date"]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(fields=["plan", "date"], name="plans_unique_day"),
        ]

    def __str__(self) -> str:
        return f"{self.date.isoformat()} {self.title or self.role}"

    @property
    def has_workout(self) -> bool:
        return bool(self.kind)


class CheckInAction(models.TextChoices):
    CONTINUE = "continue"
    SICK = "sick"
    PAUSED = "paused"


class CheckIn(BaseModel):
    """One weekly check-in. Pain and sickness answers, the engine's action and its messages are
    health data, so they are encrypted; `flagged` (pain, sickness or a pause) is the only plain
    signal, so staff can list athletes who need a look first."""

    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="check_ins")
    week = models.OneToOneField(PlanWeek, on_delete=models.CASCADE, related_name="check_in")
    # {"feedback": CheckInFeedback fields, "action": ..., "messages": [...]}
    data = EncryptedJSONField()
    flagged = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]

    def __str__(self) -> str:
        return f"Check-in {self.pk}"


class DayStatus(models.TextChoices):
    DONE = "done", "خلّصته"
    MISSED = "missed", "فوّته"
    FEEL = "feel", "حاسس بحاجة"


class DayLog(BaseModel):
    """What the athlete marked on a day. "حاسس بحاجة" is health data, so the status is
    encrypted like check-ins; `flagged` is the only plain signal."""

    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="day_logs")
    day = models.OneToOneField(PlanDay, on_delete=models.CASCADE, related_name="log")
    data = EncryptedJSONField()  # {"status": DayStatus}
    flagged = models.BooleanField(default=False, db_index=True)

    def __str__(self) -> str:
        return f"Day log {self.pk}"

    @property
    def status(self) -> str:
        return str(self.data.get("status", "")) if isinstance(self.data, dict) else ""
