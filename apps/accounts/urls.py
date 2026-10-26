from django.urls import path

from apps.accounts import views

app_name = "accounts"
urlpatterns = [
    path("login/", views.login_phone, name="login"),
    path("login/code/", views.verify, name="verify"),
    path("logout/", views.logout_view, name="logout"),
    path("account/", views.account, name="account"),
    path("account/export/", views.export, name="export"),
    path("account/delete/", views.delete, name="delete"),
]
