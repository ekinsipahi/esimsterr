from django.urls import path

from . import views

urlpatterns = [
    path("subscribe/<int:plan_id>/", views.subscribe, name="subscribe"),
    path("dashboard/subscriptions/", views.subscriptions_list, name="subscriptions_list"),
    path("dashboard/subscription/<uuid:pk>/", views.subscription_detail, name="subscription_detail"),
    path("dashboard/billing-portal/", views.billing_portal, name="billing_portal"),
]
