from django.urls import path

from apps.core import views

app_name = "core"
urlpatterns = [path("healthz", views.healthz, name="healthz")]
