from django.urls import path

from apps.payments import views

app_name = "payments"
urlpatterns = [
    path("pay/", views.checkout, name="checkout"),
    path("pay/start/", views.start, name="start"),
    path("pay/done/", views.done, name="done"),
    path("payments/paymob/callback/", views.callback, name="callback"),
]
