from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("destinations/", views.destinations, name="destinations"),
    path("regions/", views.regions_index, name="regions"),
    path("unlimited-esim/", views.unlimited, name="unlimited"),
    path("how-it-works/", views.how_it_works, name="how_it_works"),
    path("esim-compatible-devices/", views.compatible_devices, name="compatible_devices"),
    path("faq/", views.faq, name="faq"),
    path("about/", views.about, name="about"),
    path("privacy/", views.legal, {"page": "privacy"}, name="privacy"),
    path("terms/", views.legal, {"page": "terms"}, name="terms"),
    path("refund-policy/", views.legal, {"page": "refund"}, name="refund"),
    path("api/search/", views.search_api, name="search_api"),
    # SEO-friendly product URLs — keep these last so they never shadow the pages above.
    path("esim/<slug:slug>/", views.country_detail, name="country_detail"),
    path("esim-region/<slug:slug>/", views.region_detail, name="region_detail"),
]
