"""Seed the season's races from the engine reference (engine/data.py RACES).

The values are copied here on purpose: a migration must not change when the engine does.
"""

from datetime import date
from decimal import Decimal

from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor
from django.db.migrations.state import StateApps

RACES = [
    # slug, name, kind, date, city, note, [(distance, date override)]
    ("hyrox-cairo", "HYROX Cairo", "hyrox", date(2026, 11, 14), "القاهرة",
     "السباق يومين 14 و15 نوفمبر: اختار يوم موجتك.", []),
    ("gouna", "نص ماراثون الجونة", "run", date(2026, 11, 21), "الجونة", "",
     [("5", None), ("10", None), ("21.1", None)]),
    ("hyrox-dubai", "HYROX Dubai", "hyrox", date(2026, 11, 27), "دبي", "", []),
    ("sharm", "ماراثون شرم الشيخ", "run", date(2026, 11, 28), "شرم الشيخ", "",
     [("5", None), ("10", None), ("21.1", None), ("42.2", None)]),
    ("pyramids", "نص ماراثون الأهرامات", "run", date(2026, 12, 12), "الجيزة", "",
     [("5", date(2026, 12, 11)), ("10", None), ("21.1", None)]),
    ("luxor", "ماراثون الأقصر", "run", date(2027, 1, 8), "الأقصر", "",
     [("5", None), ("10", None), ("21.1", None), ("42.2", None)]),
]  # fmt: skip


def seed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    race_model = apps.get_model("races", "Race")
    distance_model = apps.get_model("races", "RaceDistance")
    for slug, name, kind, day, city, note, distances in RACES:
        race, _ = race_model.objects.get_or_create(
            slug=slug, defaults={"name": name, "kind": kind, "date": day, "city": city, "note": note}
        )
        for km, override in distances:
            distance_model.objects.get_or_create(
                race=race, distance_km=Decimal(km), defaults={"date": override}
            )


def unseed(apps: StateApps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    apps.get_model("races", "Race").objects.filter(slug__in=[r[0] for r in RACES]).delete()


class Migration(migrations.Migration):
    dependencies = [("races", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]
