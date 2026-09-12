from django.urls import path

from . import views

urlpatterns = [
    path("cheap-esim/", views.cheap_esim, name="cheap_esim"),
    path("esim-prices/", views.prices, name="prices"),
    path("what-is-esim/", views.what_is_esim, name="what_is_esim"),
    path("esim-not-working/", views.esim_not_working, name="esim_not_working"),
    # Parameterised intents. The literal prefixes keep these clear of the
    # catalogue's /esim/<slug>/ and /esim-region/<slug>/ product URLs.
    path("buy-esim-with-<slug:slug>/", views.payment_method, name="payment_method"),
    path("alternatives/<slug:slug>/", views.alternative, name="alternative"),
    path("esim-for-<slug:slug>/", views.use_case, name="use_case"),
]
