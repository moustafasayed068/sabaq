from typing import Any

from django.core.management.base import BaseCommand

from apps.core.brand import TOKENS_CSS, build_tokens_css


class Command(BaseCommand):
    help = "Write static/css/tokens.css from brand/tokens.json."

    def handle(self, *args: Any, **options: Any) -> None:  # noqa: ANN401
        TOKENS_CSS.write_text(build_tokens_css(), encoding="utf-8")
        self.stdout.write(f"wrote {TOKENS_CSS}")
