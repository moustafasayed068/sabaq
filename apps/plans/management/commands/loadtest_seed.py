"""Create signed-in test athletes with real plans for a load test, or remove them.

    python manage.py loadtest_seed --athletes 50 --out sessions.txt
    python manage.py loadtest_seed --cleanup

Each line of the output is "<session key> <a workout date>". Numbers start with +2010999, a
block no real athlete gets from this command. Refuses to run on production settings unless
--staging is given (staging uses the production settings module).
"""

from datetime import timedelta
from importlib import import_module
from pathlib import Path
from typing import Any

from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils import timezone

from apps.accounts.models import User
from apps.athletes import services as athletes
from apps.plans import services as plans
from apps.races.models import Race
from engine import HEALTH_QUESTIONS

PREFIX = "+2010999"


def _answers(start: str) -> dict[str, dict[str, Any]]:
    return {
        "race": {"distance_km": "21.1", "start_date": start},
        "you": {"age": "30", "sex": "m"},
        "running": {"runs_per_week": "3", "weekly_km": "20", "longest_km": "10"},
        "time": {"recent_km": "5.0", "recent_time_1": "28", "recent_time_2": "0", "goal": "finish"},
        "days": {"days": ["6", "1", "3", "5"], "where": "outdoor", "gps": "yes"},
        "consent": {"agree": "on"},
        "health": {**{q.id: "no" for q in HEALTH_QUESTIONS}, "injury": "none", "pain": "none"},
    }


class Command(BaseCommand):
    help = "Seed or remove load-test athletes (never on production)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--athletes", type=int, default=50)
        parser.add_argument("--out", type=Path, default=Path("loadtest-sessions.txt"))
        parser.add_argument("--race", default="pyramids")
        parser.add_argument("--cleanup", action="store_true")
        parser.add_argument("--staging", action="store_true", help="Allow production settings.")

    def handle(self, *args: Any, **options: Any) -> None:  # noqa: ANN401
        if settings.SETTINGS_MODULE.endswith(".prod") and not options["staging"]:
            raise CommandError("This is production. Use --staging only on a staging server.")
        if options["cleanup"]:
            count, _ = User.objects.filter(phone__startswith=PREFIX, is_staff=False).delete()
            self.stdout.write(f"removed {count} rows")
            return
        race = Race.objects.filter(slug=options["race"]).first()
        if race is None:
            raise CommandError(f"No race {options['race']!r}.")
        today = timezone.localdate()
        engine = import_module(settings.SESSION_ENGINE)
        lines = []
        for i in range(options["athletes"]):
            phone = f"{PREFIX}{i:05d}"
            user = User.objects.filter(phone=phone).first() or User.objects.create_user(phone)
            q = athletes.start_questionnaire(f"loadtest-{i}", race)
            q.user = user
            q.save(update_fields=["user"])
            for step, data in _answers(today.isoformat()).items():
                form = athletes.build_form(step, q, today, data)
                if not form.is_valid():
                    raise CommandError(f"{step}: {form.errors.as_text()}")
                athletes.save_step(q, step, form)
            plan = plans.create_plan(user, q)
            day = plan.days.filter(date__gte=today).exclude(kind="").order_by("date").first()
            session = engine.SessionStore()
            session[SESSION_KEY] = str(user.pk)
            session[BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]
            session[HASH_SESSION_KEY] = user.get_session_auth_hash()
            session.set_expiry(timedelta(days=1))
            session.create()
            lines.append(f"{session.session_key} {(day.date if day else today).isoformat()}")
        options["out"].write_text("\n".join(lines) + "\n")
        options["out"].chmod(0o600)
        self.stdout.write(f"seeded {len(lines)} athletes into {options['out']}")
