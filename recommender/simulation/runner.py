"""Execute genuine assessment lifecycles and v2 recommendations privately."""
from datetime import datetime, timezone
from time import perf_counter
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

from django.contrib.auth.models import User

from accounts.models import UserProfile
from assessment.models import AssessmentSession, QuestionBank, SkillRating, UserResponse
from assessment.services import finalize_session, save_answer, start_session, validate_bank
from recommender.cache import _to_json
from recommender.engine.config import configuration
from recommender.models import Career, Skill, RecommendationRun
from recommender.recommendations import get_recommendations
from recommender.simulation.assertions import check_assessment, check_recommendations, monotonicity_checks, require
from recommender.simulation.catalog import require_isolation
from recommender.simulation.profiles import generate_profiles

FIXED_TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)


def execute(*, count=100, mode='both', seed=42, progress=lambda text: None):
    require_isolation()
    require(configuration().version == 'careercoach-explainable-v2.0' and not configuration().semantic_enabled,
            'Simulation requires v2 exact-only configuration')
    require(not User.objects.exists(), 'Simulation destination contains preexisting users')
    bank = QuestionBank.objects.get(status='active')
    validated = validate_bank(bank)
    items = [{'code': item.code, 'dimension': item.dimension, 'quick_core': item.quick_core} for item in validated]
    # Existing assessment skill fields accept at most 100 characters.
    skills = [s for s in Skill.objects.order_by('pk').values('id', 'name') if len(s['name']) <= 100]
    profiles = generate_profiles(skills, items, count=count, seed=seed)
    career_ids = set(Career.objects.values_list('pk', flat=True))
    modes = ['quick', 'detailed'] if mode == 'both' else [mode]
    require(all(m in ('quick', 'detailed') for m in modes), 'Invalid simulation mode')
    runs = []
    monotonic = monotonicity_checks(items, bank.version)
    session_field = AssessmentSession._meta.get_field('id')
    with patch('django.utils.timezone.now', return_value=FIXED_TIME):
        for profile in profiles:
            user = User.objects.create_user(username='synthetic_'+profile['profile_id'], password=None)
            UserProfile.objects.create(user=user, field_of_study=profile['field_of_study'], experience_level=profile['experience_level'])
            response = UserResponse.objects.create(user=user, free_text_skills=profile['free_text_skills'])
            SkillRating.objects.bulk_create([SkillRating(response=response, skill_name=s['name'], rating=s['rating']) for s in profile['skills']])
            for selected_mode in modes:
                identity = f'{seed}:{profile["profile_id"]}:{selected_mode}'
                started = perf_counter()
                # Stable worker-only identity/time keeps engine input signatures
                # reproducible. Selection, scoring and recommendation logic are real.
                with patch.object(session_field, '_get_default', lambda: uuid5(NAMESPACE_URL, identity)):
                    session = start_session(user, selected_mode, seed=str(profile['seed']))
                selected = list(session.items.all())
                for row in selected:
                    session = save_answer(user, session.pk, position=row.position, item_id=row.pk,
                        rating=profile['responses'][row.code], revision=session.revision)
                session = finalize_session(user, session.pk, revision=session.revision)
                elapsed_assessment = perf_counter()-started
                answers = [{'id': row.code, 'dimension': row.dimension, 'rating': profile['responses'][row.code]} for row in selected]
                check_assessment(answers, session.result, selected_mode, bank.version)
                require({a['id'] for a in answers} == {i['code'] for i in items if selected_mode == 'detailed' or i['quick_core']}, 'Wrong actual bank selection')
                started = perf_counter()
                recommendations = get_recommendations(user, top_n=5)
                elapsed_recommendation = perf_counter()-started
                check_recommendations(recommendations, career_ids)
                repeated = get_recommendations(user, top_n=5)
                require(_to_json(recommendations) == _to_json(repeated), 'Recommendation output is not deterministic')
                runs.append({'profile_id': profile['profile_id'], 'scenario': profile['scenario'], 'mode': selected_mode,
                    'assessment': session.result, 'responses': answers,
                    'assessment_seconds': elapsed_assessment, 'recommendation_seconds': elapsed_recommendation,
                    'recommendations': recommendations})
            if len(runs) % (10*len(modes)) == 0 or len(runs) == count*len(modes):
                progress(f'Completed {len(runs)//len(modes)}/{count} profiles ({len(runs)} assessment/recommendation runs)')
    require(not RecommendationRun.objects.exists(), 'Simulator unexpectedly persisted recommendation history')
    return profiles, runs, {'bank_version': bank.version, 'monotonicity_checks': monotonic,
                            'assertions_passed': True, 'deterministic_repeats': len(runs)}
