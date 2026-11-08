from django.apps import AppConfig


class RecommenderConfig(AppConfig):
    name = 'recommender'

    def ready(self):
        from . import checks  # noqa: F401
