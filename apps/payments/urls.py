from django.urls import path

from . import views

urlpatterns = [
    path("stripe/", views.stripe_webhook, name="stripe_webhook"),
    path("nowpayments/ipn/", views.nowpayments_ipn, name="nowpayments_ipn"),
    path("yesim/<str:secret>/", views.yesim_webhook, name="yesim_webhook"),
    path("cron/<str:task>/", views.cron, name="cron"),
]
