from django.urls import path

from . import views

urlpatterns = [
    path("checkout/<int:plan_id>/", views.checkout, name="checkout"),
    path("order/<str:ref>/", views.order_detail, name="order_detail"),
    path("order/<str:ref>/status/", views.order_status_api, name="order_status"),
    path("esim/qr/<uuid:pk>.png", views.qr_png, name="esim_qr"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/orders/", views.orders_list, name="orders_list"),
    path("dashboard/esim/<uuid:pk>/", views.esim_detail, name="esim_detail"),
    path("dashboard/esim/<uuid:pk>/rename/", views.esim_rename, name="esim_rename"),
    path("dashboard/esim/<uuid:pk>/topup/", views.topup, name="esim_topup"),
]
