"""Versioned algorithm behavior. Weights remain the legacy design defaults."""
from dataclasses import asdict, dataclass
from math import isfinite

from django.conf import settings


@dataclass(frozen=True)
class Configuration:
    version: str
    weights: dict
    semantic_enabled: bool
    semantic_threshold: float
    model_revision: str
    max_reported_skills: int = 30

    def as_dict(self):
        return asdict(self)


def configuration():
    engine = getattr(settings, 'RECOMMENDATION_ENGINE', 'legacy')
    if engine not in ('legacy', 'v2'):
        raise ValueError('Unknown recommendation engine')
    weights = dict(settings.RECOMMENDATION_WEIGHTS)
    if set(weights) != {'interest', 'skill', 'background'} or any(
        isinstance(v, bool) or not isinstance(v, (float, int)) or not isfinite(v) or v < 0
        for v in weights.values()
    ) or abs(sum(weights.values()) - 1) > 1e-9:
        raise ValueError('Recommendation weights must be finite, nonnegative and sum to one')
    threshold = getattr(settings, 'RECOMMENDATION_SEMANTIC_THRESHOLD', .75)
    if isinstance(threshold, bool) or not isinstance(threshold, (float, int)) or not isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError('Invalid semantic threshold')
    return Configuration('careercoach-explainable-v2.0' if engine == 'v2' else 'careercoach-legacy-v1',
                         weights, bool(getattr(settings, 'RECOMMENDATION_SEMANTIC_ENABLED', False)),
                         threshold, str(getattr(settings, 'RECOMMENDATION_MODEL_REVISION', 'unrecorded')))
