"""Pure descriptive interest scoring, independent of HTTP, templates and models."""
from fractions import Fraction
from itertools import combinations

DIMENSIONS = "RIASEC"
SCORING_VERSION = "careercoach-mean-v2"
MODE_COUNTS = {"quick": 3, "detailed": 6}
NEAR_TIE_POINTS = 5  # UI heuristic, not a statistical uncertainty estimate.


class AssessmentError(ValueError):
    pass


def score_answers(answers, *, mode, bank_version):
    if mode not in MODE_COUNTS or not isinstance(bank_version, str) or not bank_version:
        raise AssessmentError("Unsupported assessment mode or bank version.")
    totals, counts, seen = dict.fromkeys(DIMENSIONS, 0), dict.fromkeys(DIMENSIONS, 0), set()
    for answer in answers:
        if not isinstance(answer, dict):
            raise AssessmentError("Invalid response.")
        identity, dimension, rating = answer.get("id"), answer.get("dimension"), answer.get("rating")
        if (type(identity) not in (str, int) or identity in seen or not isinstance(dimension, str)
                or len(dimension) != 1 or dimension not in DIMENSIONS):
            raise AssessmentError("Duplicate or invalid question.")
        if type(rating) is not int or not 1 <= rating <= 5:
            raise AssessmentError("Every question requires an integer response from 1 to 5.")
        seen.add(identity)
        totals[dimension] += rating
        counts[dimension] += 1
    if any(n != MODE_COUNTS[mode] for n in counts.values()):
        raise AssessmentError("Complete every selected question with balanced coverage before finishing.")
    means = {t: Fraction(totals[t], counts[t]) for t in DIMENSIONS}
    points = {t: (means[t] - 1) * 25 for t in DIMENSIONS}
    ranked = sorted(DIMENSIONS, key=lambda t: (-means[t], DIMENSIONS.index(t)))
    ties = [[t for t in DIMENSIONS if means[t] == value] for value in sorted(set(means.values()), reverse=True)]
    near = [[a, b] for a, b in combinations(ranked, 2) if 0 < abs(points[a] - points[b]) <= NEAR_TIE_POINTS]
    return {
        "scoring_version": SCORING_VERSION, "mode": mode, "bank_version": bank_version,
        "raw_totals": totals, "raw_averages": {t: round(float(means[t]), 6) for t in DIMENSIONS},
        "counts": counts, "scores": {t: round(float(points[t]), 2) for t in DIMENSIONS},
        "compatibility_profile": {t: round(float(means[t] / 5), 4) for t in DIMENSIONS},
        "holland_code": "".join(ranked[:3]), "ranked_dimensions": ranked,
        "ties": [group for group in ties if len(group) > 1], "near_ties": near,
        "near_tie_points": NEAR_TIE_POINTS,
    }
