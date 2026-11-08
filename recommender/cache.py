"""User-scoped lazy cache with content fingerprints and durable run snapshots.

Assessment/profile hooks remove only the disposable cache. Recommendations
recompute on explicit page access; navigation/chat never trigger computation.
History and saved roadmaps are independent of cache invalidation.
"""
from __future__ import annotations

import json
import types
import logging
from datetime import timedelta

from django.contrib.auth.models import User
from django.utils import timezone
from django.db import transaction

from recommender.models import CachedRecommendation, RecommendationRun
from recommender.engine.config import configuration
from recommender.engine.fingerprint import input_signature
from recommender.recommendations import get_recommendations
from careercoach.security import user_work_lock

logger = logging.getLogger(__name__)


class RecommendationUnavailable(Exception):
    pass


def _signature(user):
    return input_signature(user)


# ── Serialisation helpers ────────────────────────────────────────────────────

def _to_json(results: list[dict]) -> str:
    rows = []
    for r in results:
        c = r["career"]
        rows.append({**{key: value for key, value in r.items() if key != 'career'},
            "career_pk":               c.pk,
            "career_title":            c.title,
            "career_industry":         c.industry,
            "career_work_environment": c.work_environment,
            "career_summary":          c.summary,
            "final_score":             r["final_score"],
            "interest_pct":            r["interest_pct"],
            "skill_pct":               r["skill_pct"],
            "background_pct":          r["background_pct"],
            "missing_skills":          r["missing_skills"],
            "extra_missing_count":     r["extra_missing_count"],
            "why":                     r["why"],
        })
    return json.dumps(rows)


def _from_json(data: str) -> list[dict]:
    results = []
    for row in json.loads(data):
        career = types.SimpleNamespace(
            pk=row["career_pk"],
            title=row["career_title"],
            industry=row["career_industry"],
            work_environment=row["career_work_environment"],
            summary=row["career_summary"],
        )
        results.append({**{key: value for key, value in row.items() if not key.startswith('career_')},
            'career_id': row.get('career_id', row['career_pk']),
            "career":              career,
            "final_score":         row["final_score"],
            "interest_pct":        row["interest_pct"],
            "skill_pct":           row["skill_pct"],
            "background_pct":      row["background_pct"],
            "missing_skills":      row["missing_skills"],
            "extra_missing_count": row["extra_missing_count"],
            "why":                 row["why"],
        })
    return results


# ── Public API ───────────────────────────────────────────────────────────────

def compute_and_cache(user: User, top_n: int = 5) -> list[dict]:
    """Run the recommendation pipeline, persist the result, and return it."""
    try:
        signature = _signature(user)
        config = configuration()
        # Always store at least the five results used by the full results page.
        results = get_recommendations(user, top_n=max(5, top_n))
        if signature != _signature(user):
            raise ValueError('Recommendation inputs changed during computation')
        for row in results:
            row.setdefault('algorithm_version', config.version)
            row['input_signature'] = signature
    except (OSError, RuntimeError, ImportError, ValueError) as exc:
        logger.warning("Recommendation computation failed (%s)", type(exc).__name__)
        raise RecommendationUnavailable from exc
    data = _to_json(results)
    with transaction.atomic():
        run = RecommendationRun.objects.create(user=user, algorithm_version=config.version,
            input_signature=signature, configuration=config.as_dict(), results_json=data)
        CachedRecommendation.objects.update_or_create(user=user, defaults={
            'results_json': data, 'input_signature': signature, 'algorithm_version': config.version, 'run': run})
    return results[:top_n]


def get_cached_or_compute(user: User, top_n: int = 5, *, compute=True) -> list[dict]:
    """Return the cached recommendations, computing and saving them if absent."""
    try:
        cached = CachedRecommendation.objects.get(user=user)
        if (cached.input_signature == _signature(user)
                and cached.computed_at > timezone.now() - timedelta(hours=24)):
            results = _from_json(cached.results_json)
            if len(results) >= top_n or top_n <= 5:
                return results[:top_n]
    except (CachedRecommendation.DoesNotExist, ValueError, TypeError, KeyError, AttributeError):
        pass
    if not compute:
        return []
    with user_work_lock(user):
        return compute_and_cache(user, top_n=top_n)


def invalidate(user: User) -> None:
    """Delete the cached row so the next request triggers a fresh compute."""
    CachedRecommendation.objects.filter(user=user).delete()
