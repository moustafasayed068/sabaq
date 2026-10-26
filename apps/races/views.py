from dataclasses import dataclass

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from apps.core.formatting import days_until
from apps.races.models import Race
from apps.races.selectors import upcoming_races

# Test prices from docs/product.md (EGP). Payments (M2) will own the real price list.
PRICE_SHORT_EGP = 349
PRICE_LONG_EGP = 799


@dataclass(frozen=True)
class RaceCard:
    race: Race
    days_left: int


@require_GET
def landing(request: HttpRequest) -> HttpResponse:
    today = timezone.localdate()
    cards = [RaceCard(r, days_until(today, r.date)) for r in upcoming_races(today)]
    return render(
        request,
        "races/landing.html",
        {"cards": cards, "price_short": PRICE_SHORT_EGP, "price_long": PRICE_LONG_EGP},
    )
