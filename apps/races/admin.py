from django.contrib import admin

from apps.races.models import Race, RaceDistance


class RaceDistanceInline(admin.TabularInline):  # type: ignore[type-arg]
    model = RaceDistance
    extra = 0


@admin.register(Race)
class RaceAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    list_display = ("name", "kind", "date", "city", "is_active")
    list_filter = ("kind", "is_active")
    search_fields = ("name", "slug", "city")
    prepopulated_fields = {"slug": ("name",)}  # noqa: RUF012
    inlines = (RaceDistanceInline,)
