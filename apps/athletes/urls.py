from django.urls import path

from apps.athletes import views

app_name = "athletes"
urlpatterns = [
    path("start/<slug:slug>/", views.start, name="start"),
    path("questions/review/", views.review, name="review"),
    path("questions/<slug:step>/", views.step, name="step"),
]
