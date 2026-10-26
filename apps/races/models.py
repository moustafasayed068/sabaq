"""Races the athlete can train for, and their distances."""

from __future__ import annotations

from decimal import Decimal
from typing import ClassVar

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel

# Running distances the plan engine supports (engine/data.py TARGET).
SUPPORTED_DISTANCES_KM: tuple[Decimal, ...] = (
    Decimal("5"),
    Decimal("10"),
    Decimal("21.1"),
    Decimal("42.2"),
)


class RaceKind(models.TextChoices):
    RUN = "run", _("جري")
    HYROX = "hyrox", _("HYROX")


class Race(BaseModel):
    slug = models.SlugField(max_length=60, unique=True)
    name = models.CharField(_("اسم السباق"), max_length=120)
    kind = models.CharField(max_length=10, choices=RaceKind.choices)
    date = models.DateField(_("التاريخ"), db_index=True)
    city = models.CharField(_("المدينة"), max_length=60, blank=True)
    note = models.CharField(_("ملحوظة"), max_length=200, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["date", "name"]
        verbose_name = _("سباق")
        verbose_name_plural = _("سباقات")

    def __str__(self) -> str:
        return f"{self.name} ({self.date.isoformat()})"


class RaceDistance(BaseModel):
    race = models.ForeignKey(Race, on_delete=models.CASCADE, related_name="distances")
    distance_km = models.DecimalField(
        _("المسافة (كم)"),
        max_digits=4,
        decimal_places=1,
        choices=[(d, f"{d} كم") for d in SUPPORTED_DISTANCES_KM],
    )
    # Some races run a distance on another day (Pyramids 5K is the day before).
    date = models.DateField(_("تاريخ مختلف"), null=True, blank=True)

    class Meta:
        ordering: ClassVar[list[str]] = ["distance_km"]
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(fields=["race", "distance_km"], name="races_unique_distance"),
        ]

    def __str__(self) -> str:
        return f"{self.race.name}: {self.distance_km} كم"

    def clean(self) -> None:
        if self.race_id and self.race.kind == RaceKind.HYROX:
            raise ValidationError(_("سباقات HYROX مالهاش مسافات."))
