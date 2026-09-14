from django.urls import path

from . import views

urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("verify/sent/", views.verify_sent, name="verify_sent"),
    path("verify/resend/", views.verify_resend, name="verify_resend"),
    path("verify/<str:token>/", views.verify_email, name="verify_email"),
    path("auth/google/", views.google_finish, name="google_finish"),
    path("dashboard/account/", views.account, name="account"),
    path("dashboard/account/delete/", views.account_delete, name="account_delete"),
    path("unsubscribe/", views.unsubscribe, name="unsubscribe"),
    path("password-reset/", views.PasswordResetView.as_view(), name="password_reset"),
    path("password-reset/done/", views.PasswordResetDoneView.as_view(), name="password_reset_done"),
    path("password-reset/<uidb64>/<token>/", views.PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("password-reset/complete/", views.PasswordResetCompleteView.as_view(), name="password_reset_complete"),
]
