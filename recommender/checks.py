from django.core.checks import Error, register
from recommender.engine.config import configuration


@register()
def recommendation_configuration(app_configs, **kwargs):
    try:
        configuration()
    except (ValueError, TypeError) as exc:
        return [Error(str(exc), id='recommender.E001')]
    return []
