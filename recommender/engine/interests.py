"""Read stored assessment evidence; never rescore or modify an assessment."""
from math import isfinite

from recommender.constants import INDUSTRY_RIASEC

DIMENSIONS = 'RIASEC'


def valid_number(value, lower=0, upper=1):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and isfinite(value) and lower <= value <= upper


def student_interests(response):
    if response.active_session_id:
        session = response.active_session
        if session.user_id != response.user_id or session.status != 'completed':
            raise ValueError('Invalid active assessment session')
        result = session.result
        counts = result.get('counts', {})
        if session.scoring_version == 'careercoach-mean-v2':
            values = {t: result.get('scores', {}).get(t) for t in DIMENSIONS}
            profile = {t: value/100 for t, value in values.items()
                       if counts.get(t, 0) > 0 and valid_number(value, 0, 100)}
        elif session.scoring_version == 'legacy-mean-div5-v1':
            profile = {t: (v-.2)/.8 for t, v in result.get('compatibility_profile', {}).items()
                       if t in DIMENSIONS and counts.get(t, 0) > 0 and valid_number(v, .2, 1)}
        else:
            profile = {}  # Unknown scorer is missing evidence, never silently reinterpreted.
        return {'profile': profile, 'scoring_version': session.scoring_version, 'bank_version': session.bank.version}
    totals, counts = {}, {}
    for answer in response.riasec_answers.all():
        t = answer.question.riasec_type
        if t in DIMENSIONS and valid_number(answer.rating, 1, 5):
            totals[t] = totals.get(t, 0) + answer.rating
            counts[t] = counts.get(t, 0) + 1
    return {'profile': {t: (totals[t]/counts[t]-1)/4 for t in totals},
            'scoring_version': 'legacy-answers-mean-1-to-5', 'bank_version': None}


def occupation_profile(career):
    enrichment = getattr(career, 'enrichment', None)
    if not enrichment or enrichment.review_status != 'reviewed':
        return None
    # A reviewed family assignment does not validate an interest profile.
    metadata = enrichment.review_metadata
    review = metadata.get('riasec_profile', {}) if isinstance(metadata, dict) else {}
    if not isinstance(review, dict) or review.get('review_status') != 'reviewed' or not all(
        isinstance(review.get(k), str) and review[k].strip()
        for k in ('source', 'method', 'version', 'reviewer', 'reviewed_at')
    ):
        return None
    if review.get('scale') != 'descriptive_interest_0_1':
        return None
    values = enrichment.riasec_profile
    if not isinstance(values, dict) or set(values) != set(DIMENSIONS) or not all(valid_number(v) for v in values.values()):
        return None
    if max(values.values()) - min(values.values()) < 1e-9:
        return None  # Uninformative occupation profile: industry fallback.
    return values, review


def alignment(student, career):
    profile = student['profile']
    reliable = occupation_profile(career)
    base = {'student_scoring_version': student['scoring_version'], 'bank_version': student['bank_version']}
    if reliable and len(profile) == 6 and max(profile.values()) - min(profile.values()) > 1e-9:
        target, review = reliable
        differences = {t: abs(profile[t]-target[t]) for t in DIMENSIONS}
        return dict(base, score=1-sum(differences.values())/6, available=True,
                    method='occupation_normalized_l1', evidence_quality='documented_reviewed_profile',
                    dimensions=list(DIMENSIONS), differences=differences, provenance=review,
                    note='One minus mean absolute difference across six stored dimensions; not a probability.')
    dimensions = [t for t in INDUSTRY_RIASEC.get(career.industry, []) if t in profile]
    if not dimensions:
        return dict(base, score=None, available=False, method='unavailable', evidence_quality='missing', dimensions=[],
                    note='No usable industry or assessment evidence; weight is redistributed.')
    flat = len(profile) > 1 and max(profile.values()) - min(profile.values()) < 1e-9
    return dict(base, score=.5 if flat else sum(profile[t] for t in dimensions)/len(dimensions), available=True,
                method='industry_fallback', evidence_quality='industry_proxy', dimensions=dimensions,
                dimension_values={t: profile[t] for t in dimensions},
                note=('Flat student interests provide no directional preference; neutral alignment.' if flat else
                      'Industry-level interest proxy; a documented reviewed occupation profile was unavailable or unusable.'))
