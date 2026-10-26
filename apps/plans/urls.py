from django.urls import path

from apps.plans import views

app_name = "plans"
urlpatterns = [
    path("plan/", views.mine, name="mine"),
    path("plan/result/", views.result, name="result"),
    path("plan/save/", views.save, name="save"),
]
