"""Public API of the races app."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from apps.races.models import Race, RaceKind
from apps.races.selectors import race_by_slug, upcoming_races

__all__ = ["EngineRace", "engine_race", "race_by_slug", "upcoming_races"]


class UnknownDistanceError(ValueError):
    """The race does not have this distance."""


@dataclass(frozen=True)
class EngineRace:
    """The race fields the plan engine needs (PlanInput race_* and distance_km)."""

    race_id: str
    race_name: str
    race_type: str
    race_date: date
    distance_km: float | None


def engine_race(race: Race, distance_km: Decimal | None = None) -> EngineRace:
    if race.kind == RaceKind.HYROX:
        return EngineRace(race.slug, race.name, race.kind, race.date, None)
    distance = next((d for d in race.distances.all() if d.distance_km == distance_km), None)
    if distance is None:
        raise UnknownDistanceError(f"{race.slug} has no {distance_km} km distance")
    return EngineRace(
        race_id=race.slug,
        race_name=race.name,
        race_type=race.kind,
        race_date=distance.date or race.date,
        distance_km=float(distance.distance_km),
    )
