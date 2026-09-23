from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SupportConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.support"
    verbose_name = _("Support")

    def ready(self):
        # Wire the pre_delete → archive receiver (chat-log preservation).
        from . import signals  # noqa: F401
