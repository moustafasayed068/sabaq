"""Staff view of athletes' plans, with the ones that need a look first: paused plans, then
pain or sickness flagged in the last 14 days. The list never shows health details; the
check-in and day-log answers are shown only to the health_viewer role, and every view of
them is audited (docs/security.md)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.contrib import admin
from django.db.models import Case, Exists, IntegerField, OuterRef, Q, QuerySet, Value, When
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from apps.core.services import AuditAction, record_audit
from apps.plans.models import CheckIn, DayLog, Plan

HEALTH_PERMISSION = "athletes.view_health_answers"
RECENT = timedelta(days=14)

NEEDS_LOOK_PAUSED = 2
NEEDS_LOOK_FLAGGED = 1


class NeedsLookFilter(admin.SimpleListFilter):
    title = "needs a look"
    parameter_name = "look"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:  # noqa: ANN401
        return [("paused", "Paused (sharp pain)"), ("flagged", "Pain or sickness, last 14 days")]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Any]) -> QuerySet[Any]:
        if self.value() == "paused":
            return queryset.filter(needs_look=NEEDS_LOOK_PAUSED)
        if self.value() == "flagged":
            return queryset.filter(needs_look=NEEDS_LOOK_FLAGGED)
        return queryset


@admin.register(Plan)
class AthletePlanAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = (
        "look",
        "user",
        "race",
        "distance_km",
        "week_now",
        "paid",
        "race_date",
        "created_at",
    )
    list_filter = (NeedsLookFilter, "is_active", "race", "status")
    list_select_related = ("user", "race")
    search_fields = ("=user__phone",)
    fields = (
        "user",
        "race",
        "distance_km",
        "race_date",
        "starts_on",
        "status",
        "level",
        "engine_version",
        "is_active",
        "paid_at",
        "paused_at",
        "created_at",
    )
    readonly_fields = fields

    def get_queryset(self, request: HttpRequest) -> QuerySet[Plan]:
        since = timezone.now() - RECENT
        flagged_check_in = CheckIn.objects.filter(
            plan=OuterRef("pk"), flagged=True, created_at__gte=since
        )
        flagged_day = DayLog.objects.filter(
            plan=OuterRef("pk"), flagged=True, created_at__gte=since
        )
        plans: QuerySet[Plan] = super().get_queryset(request)
        return (
            plans.annotate(
                has_check_in_flag=Exists(flagged_check_in), has_day_flag=Exists(flagged_day)
            )
            .annotate(
                needs_look=Case(
                    When(paused_at__isnull=False, then=Value(NEEDS_LOOK_PAUSED)),
                    When(
                        Q(has_check_in_flag=True) | Q(has_day_flag=True),
                        then=Value(NEEDS_LOOK_FLAGGED),
                    ),
                    default=Value(0),
                    output_field=IntegerField(),
                )
            )
            .order_by("-needs_look", "race_date", "-created_at")
        )

    @admin.display(description="Needs a look", ordering="needs_look")
    def look(self, obj: Plan) -> str:
        level = getattr(obj, "needs_look", 0)
        if level == NEEDS_LOOK_PAUSED:
            return "Paused"
        if level == NEEDS_LOOK_FLAGGED:
            return "Flagged"
        return "—"

    @admin.display(description="Week")
    def week_now(self, obj: Plan) -> int | None:
        days = (timezone.localdate() - obj.starts_on).days
        return days // 7 + 1 if days >= 0 else None

    @admin.display(description="Paid", boolean=True)
    def paid(self, obj: Plan) -> bool:
        return obj.paid_at is not None

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False


class _HealthAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Read-only, visible only to the health_viewer role, every detail view audited."""

    def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return request.user.has_perm(HEALTH_PERMISSION)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:  # noqa: ANN401
        return False

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: Any = None,  # noqa: ANN401
    ) -> HttpResponse:
        response = super().change_view(request, object_id, form_url, extra_context)
        if response.status_code == 200:
            record_audit(
                AuditAction.HEALTH_DATA_VIEWED,
                target=self.get_object(request, object_id),
                request=request,
            )
        return response


@admin.register(CheckIn)
class CheckInAdmin(_HealthAdmin):
    list_display = ("created_at", "plan", "week", "flagged")
    list_filter = ("flagged",)
    list_select_related = ("plan__race", "week")
    fields = ("plan", "week", "flagged", "data", "created_at")
    readonly_fields = fields


@admin.register(DayLog)
class DayLogAdmin(_HealthAdmin):
    list_display = ("created_at", "plan", "flagged")
    list_filter = ("flagged",)
    list_select_related = ("plan__race",)
    fields = ("plan", "day", "flagged", "data", "created_at")
    readonly_fields = fields
