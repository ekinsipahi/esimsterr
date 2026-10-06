from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounts'

    def ready(self):
        # Connects the user_logged_in receiver that logs where the website
        # signs people in from. Imported for the side effect only.
        from . import login_log  # noqa: F401
