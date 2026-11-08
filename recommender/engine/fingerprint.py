"""Content signatures include direct ORM edits, not just view invalidation hooks."""
import hashlib
import json

from django.conf import settings

from recommender.engine.config import configuration


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, allow_nan=False).encode('utf-8')).hexdigest()


def input_signature(user):
    from accounts.models import UserProfile
    from assessment.models import UserResponse
    from recommender.models import Career, CareerEnrichment, CareerSkill, Skill, SkillAlias
    from recommender.matching import _NAMES_PATH, _VECTORS_PATH
    response = UserResponse.objects.select_related('active_session__bank').filter(user=user).first()
    inputs = None
    if response:
        inputs = {'id': response.pk, 'completed_at': response.completed_at, 'submitted_at': response.submitted_at,
                  'free_text': response.free_text_skills,
                  'skills': list(response.skill_ratings.order_by('pk').values('skill_name', 'rating')),
                  'answers': list(response.riasec_answers.order_by('pk').values('question_id', 'question__riasec_type', 'rating'))}
        if response.active_session_id:
            session = response.active_session
            inputs['active'] = {'id': session.pk, 'user': session.user_id, 'status': session.status,
                                'scorer': session.scoring_version, 'result': session.result, 'bank': session.bank.version}
    config = configuration()
    artifacts = {}
    if config.version == 'careercoach-legacy-v1' or config.semantic_enabled:
        for path in (_NAMES_PATH, _VECTORS_PATH):
            try:
                artifacts[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
            except FileNotFoundError:
                artifacts[path.name] = 'missing'
    payload = {'schema': 2, 'user': user.pk, 'response': inputs,
               'profile': UserProfile.objects.filter(user=user).values('field_of_study', 'experience_level').first(),
               'config': config.as_dict(), 'legacy_threshold': settings.SIMILARITY_THRESHOLD,
               'model': str(settings.EMBEDDING_MODEL_PATH), 'artifacts': artifacts,
               # Full content: low-frequency catalog edits have no timestamp fields.
               'catalog': {model._meta.model_name: list(model.objects.order_by('pk').values())
                           for model in (Career, Skill, CareerSkill, SkillAlias, CareerEnrichment)}}
    return digest(payload)
