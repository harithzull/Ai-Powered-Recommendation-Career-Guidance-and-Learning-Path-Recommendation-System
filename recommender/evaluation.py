"""Synthetic fixtures shared by the offline comparison and regression tests.

Never call seed_synthetic against an application database. The runner enforces
an isolated in-memory database and blocks network connections.
"""
from contextlib import contextmanager
from unittest.mock import patch

import numpy as np
from django.contrib.auth.models import User
from django.utils import timezone

from accounts.models import UserProfile
from assessment.models import RIASECAnswer, RIASECQuestion, SkillRating, UserResponse
from recommender.models import Career, CareerSkill, Skill, SkillAlias


def seed_synthetic():
    skills = {name: Skill.objects.create(name=name) for name in ('Python', 'SQL', 'Writing', 'Design')}
    SkillAlias.objects.create(skill=skills['Python'], name='Py', review_status='reviewed',
                              review_metadata={'evidence': 'Synthetic test synonym only'})
    for title, industry, names in (
        ('Synthetic Software', 'Technology', ['Python', 'SQL']),
        ('Synthetic Data', 'Data & AI', ['SQL', 'Python', 'Writing']),
        ('Synthetic Design', 'Creative & Design', ['Design', 'Writing']),
    ):
        career = Career.objects.create(title=title, industry=industry)
        for index, name in enumerate(names):
            CareerSkill.objects.create(career=career, skill=skills[name], importance=5 if index == 0 else 2,
                                       is_core=index == 0, required_level='intermediate' if index == 0 else 'basic')
    questions = {t: RIASECQuestion.objects.create(text=f'Synthetic {t}', riasec_type=t) for t in 'RIASEC'}
    profiles = [
        ('analytic', [3, 5, 1, 2, 2, 4], [('Python', 5), ('SQL', 2)], 'Computing/IT'),
        ('creative', [1, 2, 5, 3, 2, 2], [('Writing', 4)], 'Arts & Design'),
        ('flat_missing', [3]*6, [], ''),
        ('alias_duplicate', [3, 5, 1, 2, 2, 4], [('Python', 5), ('Py', 1)], 'Computing/IT'),
    ]
    users = []
    for name, ratings, reported, field in profiles:
        user = User.objects.create_user(username=f'synthetic_{name}')
        UserProfile.objects.update_or_create(user=user, defaults={'field_of_study': field, 'experience_level': 'No experience' if field else ''})
        response = UserResponse.objects.create(user=user, completed_at=timezone.now())
        for t, rating in zip('RIASEC', ratings):
            RIASECAnswer.objects.create(response=response, question=questions[t], rating=rating)
        for label, rating in reported:
            SkillRating.objects.create(response=response, skill_name=label, rating=rating)
        users.append((name, user))
    return users


@contextmanager
def deterministic_embeddings():
    names = ['Python', 'SQL', 'Writing', 'Design']
    vectors = np.eye(4, dtype=np.float32)
    def encode(texts):
        return np.array([vectors[names.index(t)] if t in names else np.zeros(4) for t in texts] or [np.zeros(4)], dtype=np.float32)
    with patch('recommender.recommendations.encode_user_skills', side_effect=encode), \
         patch('recommender.matching._load_store', return_value=(vectors, dict(zip(names, range(4))))):
        yield


def compact(results):
    return [{'career': r['career'].title, 'score': r['final_score'],
             'components': {key: r[key] for key in ('interest_pct', 'skill_pct', 'background_pct')}} for r in results]
