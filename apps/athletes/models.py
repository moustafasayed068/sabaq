"""The athlete's answers. Health answers (encrypted) come in their own model."""

from __future__ import annotations

from typing import ClassVar

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from django_stubs_ext import StrOrPromise

from apps.core.crypto import EncryptedJSONField
from apps.core.models import BaseModel
from apps.races.models import Race


class Sex(models.TextChoices):
    MALE = "m", _("راجل")
    FEMALE = "f", _("ست")


class Goal(models.TextChoices):
    FINISH = "finish", _("أخلّص")
    TIME = "time", _("وقت معيّن")


class Where(models.TextChoices):
    OUTDOOR = "outdoor", _("شارع أو نادي")
    TREADMILL = "treadmill", _("مشاية")
    TRACK = "track", _("تراك")
    MIXED = "mixed", _("الاتنين")


class Kit(models.TextChoices):
    DUMBBELLS = "dumbbells", _("دمبل")
    GYM = "gym", _("جيم")
    ROWER = "rower", _("تجديف")
    SKIERG = "skierg", "SkiErg"
    SLED = "sled", "Sled"
    WALLBALL = "wallball", "Wall ball"
    SANDBAG = "sandbag", "Sandbag"


# Egyptian week order for the day chips; values are JS weekdays (0 = Sunday) as the engine uses.
WEEKDAY_CHOICES: list[tuple[int, StrOrPromise]] = [
    (6, _("السبت")), (0, _("الأحد")), (1, _("الاتنين")), (2, _("التلات")),
    (3, _("الأربع")), (4, _("الخميس")), (5, _("الجمعة")),
]  # fmt: skip


class Questionnaire(BaseModel):
    """One athlete's answers for one race. Anonymous (by session) until they sign up."""

    session_key = models.CharField(max_length=64, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="questionnaires",
    )
    race = models.ForeignKey(Race, on_delete=models.PROTECT, related_name="+")
    distance_km = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)

    age = models.PositiveSmallIntegerField(null=True, blank=True)
    sex = models.CharField(max_length=1, choices=Sex.choices, blank=True)
    weight_kg = models.PositiveSmallIntegerField(null=True, blank=True)

    runs_per_week = models.PositiveSmallIntegerField(null=True, blank=True)
    weekly_km = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    longest_km = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)

    recent_km = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    recent_time_s = models.PositiveIntegerField(null=True, blank=True)
    goal = models.CharField(max_length=10, choices=Goal.choices, blank=True)
    goal_time_s = models.PositiveIntegerField(null=True, blank=True)

    days = models.JSONField(default=list, blank=True)
    where = models.CharField(max_length=10, choices=Where.choices, blank=True)
    gps = models.BooleanField(null=True, blank=True)
    kit = models.JSONField(default=list, blank=True)

    completed_steps = models.JSONField(default=list, blank=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["-created_at"]

    def __str__(self) -> str:
        return f"Questionnaire {self.pk} ({self.race.slug})"


class Consent(BaseModel):
    """Explicit consent, stored with the exact text version the athlete agreed to."""

    questionnaire = models.ForeignKey(
        Questionnaire, on_delete=models.CASCADE, related_name="consents"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    kind = models.CharField(max_length=20, default="health")
    text_version = models.CharField(max_length=40)
    text_sha256 = models.CharField(max_length=64)

    def __str__(self) -> str:
        return f"{self.kind} consent {self.text_version}"


class HealthScreen(BaseModel):
    """Health answers, injury history and current pain. Encrypted; staff views are audited."""

    questionnaire = models.OneToOneField(
        Questionnaire, on_delete=models.CASCADE, related_name="health"
    )
    # {"answers": {"heart": bool, ...}, "doctor_cleared": bool, "injury": str, "pain": str}
    data = EncryptedJSONField()

    class Meta:
        permissions = (
            ("view_health_answers", "Can view decrypted health answers (health_viewer role)"),
        )

    def __str__(self) -> str:
        return f"Health screen {self.pk}"
