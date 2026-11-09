"""Deterministic scenarios; no assumed link between a Holland code and a job."""
import random

from accounts.models import EXPERIENCE_CHOICES, FIELD_OF_STUDY_CHOICES
from assessment.scoring import DIMENSIONS

GENERATOR_VERSION = 'synthetic-students-v1'
DISTRIBUTION = {'dominant': 12, 'mixed': 18, 'neutral': 10, 'extreme': 10, 'skill_background': 20, 'randomized': 30}


def scenario_counts(count):
    if type(count) is not int or not 1 <= count <= 10000:
        raise ValueError('count must be an integer from 1 to 10000')
    counts = {k: count*v//100 for k, v in DISTRIBUTION.items()}
    order = sorted(DISTRIBUTION, key=lambda k: (-(count*DISTRIBUTION[k] % 100), list(DISTRIBUTION).index(k)))
    for key in order[:count-sum(counts.values())]:
        counts[key] += 1
    return counts


def generate_profiles(skills, items, *, count=100, seed=42):
    """A rating per actual bank item is shared between Quick and Detailed.

    Modes share item responses, not necessarily means: Detailed includes extra
    items whose simulated ratings may differ. Skill names must come from catalog.
    """
    pool = sorted(skills, key=lambda s: (s['id'], s['name']))
    items = sorted(items, key=lambda i: i['code'])
    if not pool or not items:
        raise ValueError('A real skill catalog and active bank are required')
    root = random.Random(seed)
    profiles = []
    for category, total in scenario_counts(count).items():
        for index in range(total):
            profile_seed = root.getrandbits(64)
            rng = random.Random(profile_seed)
            preference = {t: 3 for t in DIMENSIONS}
            jitter = False
            if category == 'dominant':
                preference = {t: 2 for t in DIMENSIONS}
                preference[DIMENSIONS[index % 6]] = 5
            elif category == 'mixed':
                for t in rng.sample(list(DIMENSIONS), 2 if index % 2 == 0 else 3):
                    preference[t] = 5
                jitter = index % 3 == 2
            elif category == 'extreme':
                preference = {t: (1 if index % 2 == 0 else 5) for t in DIMENSIONS} if index < 4 else {
                    t: (1 if (i+index) % 2 == 0 else 5) for i, t in enumerate(DIMENSIONS)}
            elif category == 'skill_background':
                preference = {t: rng.randint(2, 4) for t in DIMENSIONS}
                jitter = index % 2 == 0
            elif category == 'randomized':
                preference = {t: rng.randint(1, 5) for t in DIMENSIONS}
                jitter = True
            elif category == 'neutral':
                preference = dict.fromkeys(DIMENSIONS, [2, 3, 4][index % 3])
            responses = {item['code']: max(1, min(5, preference[item['dimension']] + (rng.choice([-1, 0, 1]) if jitter else 0))) for item in items}
            skill_count = (index % 5)*3 if category == 'skill_background' else rng.choice([0, 2, 4, 6, 10])
            chosen = rng.sample(pool, min(skill_count, len(pool)))
            reports = [{'skill_id': s['id'], 'name': s['name'], 'rating': rng.randint(1, 5)} for s in chosen]
            duplicate = reports[0]['name'] if reports and index % 4 == 0 else ''
            field = rng.choice(['', *[c[0] for c in FIELD_OF_STUDY_CHOICES]])
            experience = rng.choice(['', *[c[0] for c in EXPERIENCE_CHOICES]])
            profiles.append({'profile_id': f'SYN-{len(profiles)+1:03d}', 'scenario': category,
                'seed': profile_seed, 'preferences': preference, 'responses': responses, 'skills': reports,
                'free_text_skills': duplicate, 'field_of_study': field, 'experience_level': experience})
    if len(profiles) != count or len({p['profile_id'] for p in profiles}) != count:
        raise AssertionError('Missing or duplicate profile identifiers')
    return profiles
