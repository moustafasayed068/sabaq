from django.urls import path

from apps.races import views

app_name = "races"
urlpatterns = [path("", views.landing, name="landing")]
