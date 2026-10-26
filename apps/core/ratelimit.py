"""Fixed-window rate limits on the shared cache (Redis in production)."""

from django.core.cache import cache


def _key(name: str) -> str:
    return f"rl:{name}"


def hit(name: str, *, limit: int, window_s: int) -> bool:
    """Count one attempt. False when the limit for this window is already used up."""
    key = _key(name)
    cache.add(key, 0, window_s)
    try:
        count = cache.incr(key)
    except ValueError:  # expired between add and incr
        cache.set(key, 1, window_s)
        count = 1
    return count <= limit


def is_limited(name: str, *, limit: int) -> bool:
    return int(cache.get(_key(name), 0)) >= limit


def reset(name: str) -> None:
    cache.delete(_key(name))
