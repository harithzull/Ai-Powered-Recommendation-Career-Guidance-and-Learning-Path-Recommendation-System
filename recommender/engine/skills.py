"""Identity first; self-report is not independently verified proficiency."""
from collections import defaultdict
from math import isfinite

from recommender.models import Skill, SkillAlias
from recommender.normalization import normalize_label


def reported_skills(response, config):
    canonical = defaultdict(list)
    for skill in Skill.objects.all().order_by('pk'):
        canonical[normalize_label(skill.name)].append(skill)
    resolved = {key: values[0] for key, values in canonical.items() if len(values) == 1}
    for alias in SkillAlias.objects.select_related('skill').filter(kind='exact', review_status='reviewed').order_by('pk'):
        if isinstance(alias.review_metadata, dict) and alias.review_metadata.get('evidence') and alias.normalized_name not in canonical:
            resolved[alias.normalized_name] = alias.skill
    tokens = [(rating.skill_name, rating.rating) for rating in response.skill_ratings.all()]
    # Apply the same bounded input budget to old/free-text reports; do not build
    # arbitrarily large embedding batches from historic unvalidated rows.
    tokens += [(t.strip(), None) for t in response.free_text_skills[:6000].split(',') if t.strip()]
    deduplicated = {}
    for text, rating in tokens:
        key = normalize_label(text[:255])
        if not key:
            continue
        skill = resolved.get(key)
        identity = ('canonical', skill.pk) if skill else ('unresolved', key)
        row = deduplicated.setdefault(identity, {'skill_id': skill.pk if skill else None,
                                                 'name': skill.name if skill else text[:255].strip(),
                                                 'rating': None, 'method': 'canonical' if key in canonical and skill else 'reviewed_alias' if skill else 'unresolved'})
        if isinstance(rating, int) and not isinstance(rating, bool) and 1 <= rating <= 5:
            row['rating'] = max(row['rating'] or 0, rating)
    ordered = sorted(deduplicated.values(), key=lambda r: (r['skill_id'] is None, normalize_label(r['name']), r['skill_id'] or 0))
    return {'items': ordered[:config.max_reported_skills], 'truncated': len(ordered) > config.max_reported_skills,
            'has_reports': bool(ordered), 'limit': config.max_reported_skills}


def semantic_candidates(reports, config):
    """Optional cosine proposals only; never counted as confirmed possession.

    The .75 default is an experimental retrieval cutoff, NOT a calibrated
    confidence. Uses the existing local model/store; missing model files simply
    leave semantic evidence unavailable. Failures never erase exact matches.
    """
    if not config.semantic_enabled or not reports['items']:
        return {}, 'disabled' if not config.semantic_enabled else 'no_reports'
    try:
        import json
        import numpy as np
        from recommender.embeddings import get_model
        from recommender.matching import _NAMES_PATH, _VECTORS_PATH
        vectors = np.load(_VECTORS_PATH, allow_pickle=False)
        names = json.loads(_NAMES_PATH.read_text(encoding='utf-8'))
        user_vectors = np.asarray(get_model().encode([r['name'] for r in reports['items']], convert_to_numpy=True))
        if vectors.ndim != 2 or user_vectors.ndim != 2 or vectors.shape[1] != user_vectors.shape[1] or len(names) != len(vectors):
            return {}, 'invalid_artifacts'
        denominator = np.linalg.norm(vectors, axis=1)[:, None]*np.linalg.norm(user_vectors, axis=1)[None, :]
        cosine = np.divide(vectors @ user_vectors.T, denominator, out=np.zeros_like(denominator), where=denominator != 0)
        suggestions = {}
        for row, name in enumerate(names):
            best = int(np.argmax(cosine[row]))
            similarity = float(cosine[row, best])
            if isfinite(similarity) and similarity >= config.semantic_threshold:
                suggestions[name] = {'reported_name': reports['items'][best]['name'], 'cosine_similarity': round(min(1., similarity), 6),
                                     'threshold': config.semantic_threshold, 'counted_in_score': False}
        return suggestions, 'available'
    except (OSError, RuntimeError, ImportError, ValueError, TypeError, KeyError):
        return {}, 'unavailable'


def alignment(reports, career, semantic=None, semantic_status='disabled'):
    by_id = {r['skill_id']: r for r in reports['items'] if r['skill_id'] is not None}
    matches, opportunities, potential = [], [], []
    relations = list(career.career_skills.all())
    for relation in relations:
        skill = relation.skill
        verified_relation = (relation.quality_status == 'reviewed' and isinstance(relation.source_metadata, dict)
                             and bool(relation.source_metadata.get('evidence'))
                             and relation.source_relation_type in ('essential', 'optional'))
        kind = relation.source_relation_type if verified_relation else 'unspecified'
        base = {'skill_id': skill.pk, 'name': skill.name, 'category': skill.category or 'unspecified',
                'relation_type': kind, 'relation_evidence': relation.source_metadata if verified_relation else {},
                'proficiency_requirement': 'unknown'}
        if skill.pk in by_id:
            report = by_id[skill.pk]
            matches.append(dict(base, method=report['method'], self_reported_rating=report['rating'],
                                proficiency_verified=False))
        else:
            proposal = (semantic or {}).get(skill.name)
            row = dict(base, classification='potential_semantic_match' if proposal else 'not_reported',
                       suggestion='Confirm your experience with this skill or explore it; absence from your report is not a deficiency.')
            if proposal:
                row['semantic'] = proposal
                potential.append(row)
            opportunities.append(row)
    opportunities.sort(key=lambda r: ({'essential': 0, 'optional': 1, 'unspecified': 2}[r['relation_type']], normalize_label(r['name']), r['skill_id']))
    available = bool(reports['has_reports'] and relations)
    return {'score': len(matches)/len(relations) if available else None, 'available': available,
            'method': 'equal_weight_canonical_coverage', 'matched_skills': matches, 'potential_matches': potential,
            'opportunities': opportunities, 'verified_proficiency_gaps': [], 'related_skill_count': len(relations),
            'semantic_status': semantic_status, 'reports_truncated': reports['truncated'],
            'note': 'Each canonical relation counts once, irrespective of aliases, repetitions or self-rating. No verified comparable proficiency scale is available.'}
