from django.urls import path

from . import views

urlpatterns = [
    path("wallet/", views.wallet, name="wallet"),
    path("wallet/add/", views.wallet_add, name="wallet_add"),
]
