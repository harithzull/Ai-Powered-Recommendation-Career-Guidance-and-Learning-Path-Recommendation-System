from django.apps import AppConfig


class ResumeConfig(AppConfig):
    name = 'resume'

    def ready(self):
        from . import checks, signals  # noqa: F401
