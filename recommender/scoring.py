"""
RIASEC interest scoring and background scoring.
Neither function touches the embedding layer.
"""
from assessment.models import UserResponse
from recommender.constants import (
    EXPERIENCE_WEIGHT,
    FIELD_TO_INDUSTRIES,
    INDUSTRY_RIASEC,
)
from recommender.models import Career

MAX_RATING = 5


def normalized_riasec(type_rating_pairs) -> dict[str, float]:
    """
    Canonical RIASEC scoring. Takes an iterable of (type_letter, rating) pairs
    and returns each type's 0-1 score as the *average* rating ÷ max rating.

    Averaging (not summing) is what makes adaptive assessment work: each type
    may be answered a different number of times, so a raw sum would unfairly
    favour types that happened to get more questions. A type with no answers
    scores 0.0.
    """
    sums: dict[str, int] = {}
    counts: dict[str, int] = {}
    for t, rating in type_rating_pairs:
        sums[t] = sums.get(t, 0) + rating
        counts[t] = counts.get(t, 0) + 1

    return {
        t: round((sums[t] / counts[t]) / MAX_RATING, 4) if counts.get(t) else 0.0
        for t in "RIASEC"
    }


def riasec_profile(response: UserResponse) -> dict[str, float]:
    """
    Return a dict mapping each RIASEC type letter to a 0-1 normalized score.
    e.g. {"R": 0.4, "I": 0.9, "A": 0.2, "S": 0.6, "E": 0.3, "C": 0.8}
    """
    return normalized_riasec(
        (a.question.riasec_type, a.rating)
        for a in response.riasec_answers.select_related("question").all()
    )


def interest_score(profile: dict[str, float], career: Career) -> float:
    """
    Average of the user's normalized RIASEC scores for the career's industry types.
    Returns 0-1.
    """
    types = INDUSTRY_RIASEC.get(career.industry, [])
    if not types:
        return 0.5  # unknown industry — neutral
    return round(sum(profile.get(t, 0.0) for t in types) / len(types), 4)


def background_score(response: UserResponse, career: Career) -> float:
    """
    Two-part score based on field of study and experience level.

    course_alignment  : 1.0 if career industry is in FIELD_TO_INDUSTRIES[field],
                        else 0.4.
    experience_weight : EXPERIENCE_WEIGHT[level], defaults to 0.7 if unset.
    final             : 0.7 * course_alignment + 0.3 * experience_weight
    """
    try:
        profile = response.user.profile
        field = profile.field_of_study or "Other"
        level = profile.experience_level or "No experience"
    except AttributeError:
        # No profile row exists yet — degrade gracefully
        field = "Other"
        level = "No experience"

    aligned_industries = FIELD_TO_INDUSTRIES.get(field, [])
    course_alignment = 1.0 if career.industry in aligned_industries else 0.4

    exp_weight = EXPERIENCE_WEIGHT.get(level, 0.7)

    return round(0.7 * course_alignment + 0.3 * exp_weight, 4)
