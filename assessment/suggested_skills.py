"""
Derive suggested skill pills from a user's RIASEC interest profile.
Queries the CareerSkill table — no ML, no embeddings.

Industry selection uses PRIMARY type only (first entry in each INDUSTRY_RIASEC
list) so that Healthcare (primary-S, secondary-I) never appears for an I-heavy
user, and Technology (primary-I, secondary-R) doesn't flood an R-heavy user.

Ranking uses industry-relevance-weighted importance so that careers in
strongly-aligned industries outrank careers in weakly-aligned ones:
  score(skill) = sum over target careers of (importance × industry_weight)
  industry_weight = mean(profile[t] for t in industry's RIASEC types)
"""
from __future__ import annotations

from recommender.constants import FIELD_TO_INDUSTRIES, INDUSTRY_RIASEC
from recommender.models import Career, CareerSkill

MAX_PILLS_SHOWN = 15

# The ESCO "Research" industry's 20 careers all share 52 generic academic-
# researcher skills at importance=5. Excluding it stops those skills from
# drowning out practical Data & AI / Technology skills for I-type users.
_SKIP_INDUSTRIES: frozenset[str] = frozenset({"Research"})


# ── Reverse mappings ─────────────────────────────────────────────────────────
def _build_reverses() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """
    Returns (all_reverse, primary_reverse).
    all_reverse    : type → every industry that lists the type
    primary_reverse: type → only industries where the type is listed FIRST
    """
    all_r: dict[str, list[str]]     = {}
    primary_r: dict[str, list[str]] = {}
    for industry, types in INDUSTRY_RIASEC.items():
        if industry in _SKIP_INDUSTRIES:
            continue
        for t in types:
            all_r.setdefault(t, []).append(industry)
        if types:
            primary_r.setdefault(types[0], []).append(industry)
    return all_r, primary_r


RIASEC_TO_INDUSTRIES, RIASEC_TO_PRIMARY_INDUSTRIES = _build_reverses()


# ── Industry relevance weight for a given RIASEC profile ────────────────────
def _industry_weight(industry: str, profile: dict[str, float]) -> float:
    types = INDUSTRY_RIASEC.get(industry, [])
    if not types:
        return 0.0
    return sum(profile.get(t, 0.0) for t in types) / len(types)


# ── Core suggestion logic ────────────────────────────────────────────────────
def get_suggested_skills(
    riasec_profile: dict[str, float],
    field_of_study: str | None = None,
    top_types: int = 3,
    top_n: int = MAX_PILLS_SHOWN,
) -> list[str]:
    """
    Given a normalised RIASEC profile (R/I/A/S/E/C → 0–1), return up to
    `top_n` distinctive skill names.

    Algorithm:
      1. Select industries where the user's top RIASEC types are PRIMARY
         (first-listed), so each industry maps to at most one user preference.
         If a background field is available, prefer industries that match both
         the RIASEC type and the field of study.
         Falls back to secondary associations if primary yields < 20 careers.
      2. Assign each career a weight = mean profile score for its industry.
      3. score(skill) = sum(importance × weight) across target careers.
      4. Return the top-scoring names.
    """
    sorted_types = sorted(
        (t for t in riasec_profile if riasec_profile[t] > 0),
        key=lambda t: riasec_profile[t],
        reverse=True,
    )
    active_types = sorted_types[:top_types]
    if not active_types:
        return []

    field_industries = set(FIELD_TO_INDUSTRIES.get(field_of_study or "", []))

    # Primary industries first (avoids cross-cluster bleed)
    industries: list[str] = []
    seen_ind: set[str] = set()
    for t in active_types:
        for ind in RIASEC_TO_PRIMARY_INDUSTRIES.get(t, []):
            if ind not in seen_ind:
                industries.append(ind)
                seen_ind.add(ind)

    if field_industries:
        matched = [ind for ind in industries if ind in field_industries]
        if Career.objects.filter(industry__in=matched).exists():
            industries = matched
            seen_ind = set(industries)
        else:
            secondary_matched: list[str] = []
            seen_secondary: set[str] = set()
            for t in active_types:
                for ind in RIASEC_TO_INDUSTRIES.get(t, []):
                    if ind in field_industries and ind not in seen_secondary:
                        secondary_matched.append(ind)
                        seen_secondary.add(ind)
            if Career.objects.filter(industry__in=secondary_matched).exists():
                industries = secondary_matched
                seen_ind = set(industries)

    # Fallback to secondary if we have too few careers
    career_ids = (
        list(Career.objects.filter(industry__in=industries).values_list("id", flat=True))
        if industries else []
    )
    if len(career_ids) < 20:
        for t in active_types:
            for ind in RIASEC_TO_INDUSTRIES.get(t, []):
                if ind not in seen_ind:
                    industries.append(ind)
                    seen_ind.add(ind)
        if field_industries:
            matched = [ind for ind in industries if ind in field_industries]
            if Career.objects.filter(industry__in=matched).exists():
                industries = matched
        career_ids = list(
            Career.objects.filter(industry__in=industries).values_list("id", flat=True)
        )

    if not career_ids:
        return []

    # Per-industry weight, per-career weight
    ind_weight: dict[str, float] = {
        ind: _industry_weight(ind, riasec_profile) for ind in industries
    }
    career_weight: dict[int, float] = {
        cid: ind_weight.get(ind, 0.0)
        for cid, ind in Career.objects.filter(id__in=career_ids).values_list("id", "industry")
    }

    # Fetch (career_id, skill_name, importance) — core skills only
    skill_rows = list(
        CareerSkill.objects
        .filter(career_id__in=career_ids, is_core=True)
        .values_list("career_id", "skill__name", "importance")
    )
    if not skill_rows:
        skill_rows = list(
            CareerSkill.objects
            .filter(career_id__in=career_ids)
            .values_list("career_id", "skill__name", "importance")
        )
    if not skill_rows:
        return []

    # Aggregate weighted scores
    scores: dict[str, float] = {}
    for career_id, skill_name, importance in skill_rows:
        w = career_weight.get(career_id, 0.0)
        scores[skill_name] = scores.get(skill_name, 0.0) + importance * w

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [name for name, _ in ranked[:top_n]]


# ── Per-type skill pool (used by the old single-page quiz JS) ────────────────
def get_skills_by_riasec_type(top_n: int = MAX_PILLS_SHOWN) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for riasec_type in "RIASEC":
        profile = {t: (1.0 if t == riasec_type else 0.0) for t in "RIASEC"}
        result[riasec_type] = get_suggested_skills(profile, top_types=1, top_n=top_n)
    return result


# ── User-facing wrapper (kept for compatibility) ─────────────────────────────
def get_suggested_skills_for_user(user, top_n: int = MAX_PILLS_SHOWN) -> list[str]:
    from assessment.models import UserResponse
    from recommender.scoring import normalized_riasec

    try:
        response = (
            UserResponse.objects
            .prefetch_related("riasec_answers__question")
            .get(user=user)
        )
    except UserResponse.DoesNotExist:
        return []

    if not response.riasec_answers.exists():
        return []

    profile = normalized_riasec(
        (a.question.riasec_type, a.rating)
        for a in response.riasec_answers.all()
    )
    try:
        field_of_study = response.user.profile.field_of_study
    except AttributeError:
        field_of_study = ""

    return get_suggested_skills(
        profile,
        field_of_study=field_of_study,
        top_types=1,
        top_n=top_n,
    )
