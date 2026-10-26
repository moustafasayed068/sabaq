from django.urls import path

from apps.accounts import views

app_name = "accounts"
urlpatterns = [
    path("login/", views.login_phone, name="login"),
    path("login/code/", views.verify, name="verify"),
    path("logout/", views.logout_view, name="logout"),
]
