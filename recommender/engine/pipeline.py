from assessment.models import UserResponse
from recommender.engine.candidates import candidates
from recommender.engine.config import configuration
from recommender.engine.context import background
from recommender.engine.explanations import explain
from recommender.engine.interests import alignment as interest_alignment, student_interests
from recommender.engine.ranking import combine, stable_order
from recommender.engine.skills import alignment as skill_alignment, reported_skills, semantic_candidates


def recommend(user, top_n=5):
    from accounts.models import UserProfile
    try:
        response = UserResponse.objects.select_related('active_session__bank').prefetch_related(
            'riasec_answers__question', 'skill_ratings').get(user=user, completed_at__isnull=False)
    except UserResponse.DoesNotExist:
        return []
    config = configuration()
    interests = student_interests(response)
    # Read once from the DB, avoiding stale reverse-relation caches on a reused User.
    profile = UserProfile.objects.filter(user=user).first()
    reports = reported_skills(response, config)
    semantic, semantic_status = semantic_candidates(reports, config)
    results = []
    for career in candidates():
        interest = interest_alignment(interests, career)
        skills = skill_alignment(reports, career, semantic, semantic_status)
        components = {'interest': {'score': interest['score'], 'available': interest['available'], 'method': interest['method']},
                      'skill': {'score': skills['score'], 'available': skills['available'], 'method': skills['method']},
                      'background': background(user, career, profile=profile)}
        score = combine(components, config.weights)
        explanation = explain(components, interest, skills)
        missing = [r['name'] for r in skills['opportunities']]
        results.append({'career': career, 'career_id': career.pk, 'final_score': round(score, 1), '_unrounded_score': score,
                        'algorithm_version': config.version, 'configuration': config.as_dict(), 'components': components,
                        'riasec': interest, 'skill_alignment': skills, 'matched_skills': skills['matched_skills'],
                        'opportunities': skills['opportunities'], 'explanation': explanation,
                        # Compatibility adapter for current dashboards, chat and templates.
                        'interest_pct': round((interest['score'] if interest['available'] else .5)*100, 1),
                        'skill_pct': round((skills['score'] if skills['available'] else .5)*100, 1),
                        'background_pct': round((components['background']['score'] if components['background']['available'] else .5)*100, 1),
                        'missing_skills': missing, 'extra_missing_count': max(0, len(missing)-10), 'why': explanation['summary']})
    ranked = stable_order(results)[:max(0, top_n)]
    from recommender.engine.fingerprint import input_signature
    signature = input_signature(user)
    for row in ranked:
        del row['_unrounded_score']
        row['input_signature'] = signature
    return ranked
