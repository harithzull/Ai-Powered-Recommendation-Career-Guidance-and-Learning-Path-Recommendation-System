"""
Recommendation caching layer.

Results from the expensive semantic-matching pipeline are stored as JSON in
CachedRecommendation (one row per user).  The cache is written immediately
after any input that affects rankings (quiz submit, profile save) so that
subsequent page loads read from the DB instead of re-running the pipeline.

Invalidation rules
  - Assessment Part 1 retake  → delete cache (Part 2 not yet re-submitted)
  - Assessment Part 2 submit  → compute_and_cache()
  - Profile save              → compute_and_cache() if assessment is complete
  - Recommendations page miss → compute_and_cache() (lazy fallback)
"""
from __future__ import annotations

import json
import types
import hashlib
import logging
from datetime import timedelta

from django.contrib.auth.models import User
from django.conf import settings
from django.utils import timezone

from recommender.models import CachedRecommendation
from recommender.recommendations import get_recommendations
from careercoach.security import user_work_lock

logger = logging.getLogger(__name__)


class RecommendationUnavailable(Exception):
    pass


def _signature(user):
    from assessment.models import UserResponse
    from accounts.models import UserProfile
    response = UserResponse.objects.filter(user=user).values("submitted_at", "completed_at").first()
    profile = UserProfile.objects.filter(user=user).values("field_of_study", "experience_level").first()
    payload = {"version": 1, "response": response, "profile": profile,
               "weights": settings.RECOMMENDATION_WEIGHTS,
               "threshold": settings.SIMILARITY_THRESHOLD, "model": settings.EMBEDDING_MODEL_PATH}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


# ── Serialisation helpers ────────────────────────────────────────────────────

def _to_json(results: list[dict]) -> str:
    rows = []
    for r in results:
        c = r["career"]
        rows.append({
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
        results.append({
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
        # Always store at least the five results used by the full results page.
        results = get_recommendations(user, top_n=max(5, top_n))
    except (OSError, RuntimeError, ImportError, ValueError) as exc:
        logger.warning("Recommendation computation failed (%s)", type(exc).__name__)
        raise RecommendationUnavailable from exc
    CachedRecommendation.objects.update_or_create(
        user=user,
        defaults={"results_json": _to_json(results), "input_signature": _signature(user)},
    )
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
