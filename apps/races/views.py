from dataclasses import dataclass

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from apps.core.formatting import days_until
from apps.payments import services as payments
from apps.races.models import Race
from apps.races.selectors import upcoming_races


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
        {
            "cards": cards,
            "price_short": payments.prices()["short"].amount,
            "price_long": payments.prices()["long"].amount,
        },
    )
