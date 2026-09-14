from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

urlpatterns = [
    path("config/", views.config, name="api_config"),
    # auth
    path("auth/register/", views.register, name="api_register"),
    path("auth/login/", views.login, name="api_login"),
    path("auth/google/", views.google_login, name="api_google"),
    path("auth/resend-verification/", views.resend_verification, name="api_resend_verification"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="api_refresh"),
    path("auth/me/", views.me, name="api_me"),
    # catalogue
    path("countries/", views.countries, name="api_countries"),
    path("regions/", views.regions, name="api_regions"),
    path("plans/", views.plans, name="api_plans"),
    path("devices/", views.devices, name="api_devices"),
    # customer
    path("esims/", views.my_esims, name="api_esims"),
    path("esims/<uuid:pk>/", views.esim_detail, name="api_esim_detail"),
    path("esims/<uuid:pk>/rename/", views.esim_rename, name="api_esim_rename"),
    path("orders/", views.my_orders, name="api_orders"),
    path("checkout-url/", views.checkout_url, name="api_checkout_url"),
    path("account/delete/", views.delete_account_api, name="api_account_delete"),
    # guest purchases, identified by the device rather than an account
    path("device/esims/", views.device_esims, name="api_device_esims"),
    path("device/claim/", views.device_claim, name="api_device_claim"),
    path("device/nonce/", views.device_nonce, name="api_device_nonce"),
    path("device/attest/", views.device_attest, name="api_device_attest"),
    # wallet
    path("wallet/", views.wallet, name="api_wallet"),
    path("referral/", views.referral, name="api_referral"),
    path("referral/apply/", views.referral_apply, name="api_referral_apply"),
    # inbox
    path("inbox/", views.inbox, name="api_inbox"),
    path("inbox/read-all/", views.inbox_read_all, name="api_inbox_read_all"),
    path("inbox/<int:pk>/read/", views.inbox_read, name="api_inbox_read"),
    path("wallet/topup-url/", views.wallet_topup_url, name="api_wallet_topup_url"),
    path("orders/pay-with-balance/", views.pay_with_balance, name="api_pay_with_balance"),
    # in-app card payment
    path("pay/sheet/", views.payment_sheet, name="api_payment_sheet"),
    path("pay/cards/", views.saved_cards, name="api_saved_cards"),
    path("pay/cards/<str:pm_id>/", views.delete_card, name="api_delete_card"),
    # legal
    path("legal/", views.legal_index, name="api_legal"),
    path("legal/accept/", views.legal_accept, name="api_legal_accept"),
    path("legal/<slug:slug>/", views.legal_document, name="api_legal_document"),
]
