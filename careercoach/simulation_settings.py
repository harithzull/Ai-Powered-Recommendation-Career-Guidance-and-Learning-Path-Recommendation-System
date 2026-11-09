"""Private worker settings: never read .env or connect to an application DB."""
from .test_settings import *  # noqa: F403

CAREERCOACH_SIMULATION_ISOLATED = True
RECOMMENDATION_ENGINE = 'v2'
RECOMMENDATION_SEMANTIC_ENABLED = False
