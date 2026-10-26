import pytest
from django.conf import settings


@pytest.mark.django_db
def test_admin_is_at_a_non_default_path(client):
    assert client.get("/admin/").status_code == 404
    response = client.get(f"/{settings.ADMIN_URL}login/")
    assert response.status_code == 200
