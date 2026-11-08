from recommender.constants import FIELD_TO_INDUSTRIES

_UNSET = object()


def background(user, career, *, profile=_UNSET):
    profile = getattr(user, 'profile', None) if profile is _UNSET else profile
    field = getattr(profile, 'field_of_study', '')
    experience = getattr(profile, 'experience_level', '')
    industries = FIELD_TO_INDUSTRIES.get(field, [])
    available = bool(industries and career.industry in {i for group in FIELD_TO_INDUSTRIES.values() for i in group})
    score = (1 if career.industry in industries else .4) if available else None
    return {'score': score, 'available': available, 'method': 'education_industry_proxy',
            'education_aligned': career.industry in industries if available else None,
            'experience_context': experience or 'Not reported',
            'note': 'Education is a broad industry proxy, not eligibility. Experience is descriptive only: no comparable career-specific experience requirements are available.'}
