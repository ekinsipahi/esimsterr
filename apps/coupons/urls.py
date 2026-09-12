from django.urls import path

from . import views

urlpatterns = [
    path("coupons/", views.coupons_page, name="coupons"),
    path("api/coupon/validate/", views.validate_api, name="coupon_validate"),
]
