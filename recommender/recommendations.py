"""
Top-level recommendation pipeline.
Blends RIASEC interest, semantic skill coverage, and background into a ranked list.
"""
from django.conf import settings
from django.contrib.auth.models import User

from assessment.models import UserResponse
from recommender.matching import encode_user_skills, semantic_skill_match_from_vectors
from recommender.models import Career
from recommender.scoring import background_score, interest_score, riasec_profile


def _user_skill_texts(response: UserResponse) -> list[str]:
    """
    Build the list of skill strings to encode for the user.
    Each rated skill is repeated by its rating value so higher-rated skills
    have proportionally more influence on the semantic match.
    Free-text skills (unrated) are included once each.
    Works for both the old fixed-skill format and the new adaptive pill format.
    """
    texts: list[str] = []

    # Rated skills from pill selections (adaptive) or fixed-skill saves (legacy)
    for sr in response.skill_ratings.all():
        texts.extend([sr.skill_name] * sr.rating)

    # Unrated free-text extras
    for raw in response.free_text_skills.split(","):
        token = raw.strip()
        if token:
            texts.append(token)

    return texts


def get_recommendations(user: User, top_n: int = 5) -> list[dict]:
    """
    Return a ranked list of up to `top_n` career recommendations for `user`.

    Each entry is a dict:
        career          : Career instance
        final_score     : float 0-100
        interest_pct    : float 0-100
        skill_pct       : float 0-100
        background_pct  : float 0-100
        missing_skills  : list[str]  (core skills below SIMILARITY_THRESHOLD)
        why             : str        (human-readable explanation snippet)
    """
    try:
        response = UserResponse.objects.prefetch_related(
            "riasec_answers__question", "skill_ratings"
        ).get(user=user)
    except UserResponse.DoesNotExist:
        return []

    weights = getattr(settings, "RECOMMENDATION_WEIGHTS", {
        "interest": 0.45, "skill": 0.40, "background": 0.15
    })

    profile = riasec_profile(response)
    skill_texts = _user_skill_texts(response)
    user_vecs = encode_user_skills(skill_texts)   # encode once, reuse across all careers
    careers = list(Career.objects.all())

    results = []
    for career in careers:
        i_score = interest_score(profile, career)
        s_score, missing = semantic_skill_match_from_vectors(user_vecs, career)
        b_score = background_score(response, career)

        final = (
            i_score * weights["interest"]
            + s_score * weights["skill"]
            + b_score * weights["background"]
        )

        results.append({
            "career":              career,
            "final_score":         round(final * 100, 1),
            "interest_pct":        round(i_score * 100, 1),
            "skill_pct":           round(s_score * 100, 1),
            "background_pct":      round(b_score * 100, 1),
            "missing_skills":      missing,
            "extra_missing_count": max(0, len(missing) - 12),
            "why":                 _why_text(i_score, s_score, missing),
        })

    results.sort(key=lambda x: x["final_score"], reverse=True)
    return results[:top_n]


def _why_text(interest: float, skill: float, missing: list[str]) -> str:
    parts = []

    if interest >= 0.7:
        parts.append("Strong interest match")
    elif interest >= 0.45:
        parts.append("Moderate interest match")
    else:
        parts.append("Low interest match")

    if skill >= 0.5:
        parts.append("good skill coverage")
    elif skill >= 0.3:
        n = len(missing)
        parts.append(f"partial skill coverage ({n} core skill{'s' if n != 1 else ''} to develop)")
    else:
        n = len(missing)
        parts.append(f"significant skill gap ({n} core skill{'s' if n != 1 else ''} to develop)")

    return "; ".join(parts) + "."
