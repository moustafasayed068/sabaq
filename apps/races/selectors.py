"""Read queries for races. Other apps use these (or services.py), never the models."""

from datetime import date

from django.db.models import QuerySet

from apps.races.models import Race


def upcoming_races(today: date) -> QuerySet[Race]:
    """Active races from today on, soonest first, with their distances in one extra query."""
    return Race.objects.filter(is_active=True, date__gte=today).prefetch_related("distances")


def race_by_slug(slug: str) -> Race | None:
    return Race.objects.filter(slug=slug, is_active=True).prefetch_related("distances").first()
