from django.urls import path

from . import views

urlpatterns = [
    path("support/", views.support, name="support"),
    path("support/ticket/<str:ref>/", views.ticket_detail, name="ticket_detail"),
    path("api/assistant/", views.assistant_api, name="assistant_api"),
]
