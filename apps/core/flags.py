"""Feature flags: `is_enabled("new_checkin")`. Cached briefly; saving a flag clears its cache."""

from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.core.models import FeatureFlag

CACHE_SECONDS = 30
_MISSING = "missing"


def _key(name: str) -> str:
    return f"core:flag:{name}"


def is_enabled(name: str, *, default: bool = False) -> bool:
    cached = cache.get(_key(name))
    if cached is None:
        flag = FeatureFlag.objects.filter(name=name).values_list("enabled", flat=True).first()
        cached = _MISSING if flag is None else flag
        cache.set(_key(name), cached, CACHE_SECONDS)
    if cached == _MISSING:
        return default
    return bool(cached)


@receiver([post_save, post_delete], sender=FeatureFlag)
def _clear_flag_cache(sender: type[FeatureFlag], instance: FeatureFlag, **kwargs: object) -> None:
    cache.delete(_key(instance.name))
