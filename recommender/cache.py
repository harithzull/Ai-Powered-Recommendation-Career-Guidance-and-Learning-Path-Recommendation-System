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

from django.contrib.auth.models import User

from recommender.models import CachedRecommendation
from recommender.recommendations import get_recommendations


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
    results = get_recommendations(user, top_n=top_n)
    CachedRecommendation.objects.update_or_create(
        user=user,
        defaults={"results_json": _to_json(results)},
    )
    return results


def get_cached_or_compute(user: User, top_n: int = 5) -> list[dict]:
    """Return the cached recommendations, computing and saving them if absent."""
    try:
        cached = CachedRecommendation.objects.get(user=user)
        return _from_json(cached.results_json)[:top_n]
    except CachedRecommendation.DoesNotExist:
        return compute_and_cache(user, top_n=top_n)


def invalidate(user: User) -> None:
    """Delete the cached row so the next request triggers a fresh compute."""
    CachedRecommendation.objects.filter(user=user).delete()
