import pytest
from django.core.cache import cache

from apps.core.models import FeatureFlag
from apps.core.services import is_enabled

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()


def test_unknown_flag_uses_default():
    assert is_enabled("nope") is False
    assert is_enabled("nope2", default=True) is True


def test_flag_value_and_cache_cleared_on_save(django_assert_num_queries):
    flag = FeatureFlag.objects.create(name="new-checkin", enabled=False)
    assert is_enabled("new-checkin") is False
    with django_assert_num_queries(0):
        assert is_enabled("new-checkin") is False  # served from cache
    flag.enabled = True
    flag.save()
    assert is_enabled("new-checkin") is True
    assert str(flag) == "new-checkin=on"
    flag.delete()
    assert is_enabled("new-checkin") is False
