from datetime import date

from django.urls import path, register_converter

from apps.plans import views


class IsoDateConverter:
    regex = r"\d{4}-\d{2}-\d{2}"

    def to_python(self, value: str) -> date:
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(value) from exc

    def to_url(self, value: date) -> str:
        return value.isoformat()


register_converter(IsoDateConverter, "isodate")

app_name = "plans"
urlpatterns = [
    path("plan/", views.mine, name="mine"),
    path("plan/result/", views.result, name="result"),
    path("plan/save/", views.save, name="save"),
    path("plan/day/<isodate:day>/", views.day, name="day"),
]
