"""Independent contract checks; no replacement implementation of scoring."""
import math
import re
from collections import Counter

from assessment.scoring import DIMENSIONS, MODE_COUNTS, score_answers


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def check_assessment(answers, result, mode, bank_version):
    require(len({a['id'] for a in answers}) == len(answers), 'Duplicate assessment items')
    require(Counter(a['dimension'] for a in answers) == Counter(dict.fromkeys(DIMENSIONS, MODE_COUNTS[mode])), 'Unbalanced item coverage')
    require(result == score_answers(answers, mode=mode, bank_version=bank_version), 'Assessment scoring is not deterministic')
    require(set(result['scores']) == set(DIMENSIONS), 'Missing RIASEC dimensions')
    require(all(math.isfinite(v) and 0 <= v <= 100 for v in result['scores'].values()), 'Assessment score outside boundaries')
    code = result['holland_code']
    require(bool(re.fullmatch('[RIASEC]{3}', code)) and len(set(code)) == 3, 'Invalid Holland Code')
    expected = sorted(DIMENSIONS, key=lambda t: (-result['raw_totals'][t], DIMENSIONS.index(t)))
    require(result['ranked_dimensions'] == expected and code == ''.join(expected[:3]), 'Unstable tie ordering')
    expected_ties = [list(filter(lambda t: result['raw_totals'][t] == total, DIMENSIONS)) for total in sorted(set(result['raw_totals'].values()), reverse=True)]
    require(result['ties'] == [group for group in expected_ties if len(group) > 1], 'Incorrect tie groups')


def check_recommendations(rows, career_ids):
    require(len(rows) == min(5, len(career_ids)), 'Missing top-five candidates')
    ids = [r['career_id'] for r in rows]
    require(len(set(ids)) == len(ids) and set(ids) <= career_ids, 'Duplicate or invalid careers')
    require([r['final_score'] for r in rows] == sorted((r['final_score'] for r in rows), reverse=True), 'Ranking points not descending')
    for row in rows:
        require(math.isfinite(row['final_score']) and 0 <= row['final_score'] <= 100, 'Invalid ranking points')
        components = row['components']
        positive = any(c['available'] and c['configured_weight'] > 0 for c in components.values())
        require(math.isclose(sum(c['effective_weight'] for c in components.values()), 1 if positive else 0, abs_tol=1e-9), 'Invalid effective weight sum')
        for c in components.values():
            require(c['score'] is None if not c['available'] else (math.isfinite(c['score']) and 0 <= c['score'] <= 1), 'Invalid component evidence/score')
            require(all(math.isfinite(c[k]) and c[k] >= 0 for k in ('configured_weight', 'effective_weight', 'contribution_points')), 'Nonfinite component contribution')
            require(c['available'] or c['effective_weight'] == 0, 'Missing evidence contributes weight')
        if not positive:
            require(row['final_score'] == 50, 'Missing evidence is not neutral')
        else:
            require(abs(sum(c['contribution_points'] for c in components.values())-row['final_score']) <= .0500001, 'Unexplained final score')
        skills = row['skill_alignment']
        require(not skills['verified_proficiency_gaps'], 'Unverified proficiency gap claim')
        matched = skills['matched_skills']
        require(len({m['skill_id'] for m in matched}) == len(matched), 'Duplicate confirmed skills')
        require(all(m['method'] in ('canonical', 'reviewed_alias') and m['proficiency_verified'] is False for m in matched), 'Semantic/unverified proficiency counted as confirmed')
        require(all(not m['semantic']['counted_in_score'] for m in skills['potential_matches']), 'Semantic proposal contributes to score')
        require(all(o['classification'] in ('not_reported', 'potential_semantic_match') and o['proficiency_requirement'] == 'unknown' for o in row['opportunities']), 'Unsupported gap classification')
        explanation = row['explanation']
        require(all(key in explanation for key in ('summary', 'supporting_evidence', 'uncertain_suggestions', 'unavailable_evidence', 'score_meaning')), 'Incomplete explanation')
        require(bool(explanation['summary']) and 'not a probability' in explanation['score_meaning'], 'Missing explanation/score caveat')
        require(all(m['name'] in explanation['summary'] for m in matched), 'Matched skill absent from explanation')
        require(not row['riasec']['available'] or row['riasec']['method'] in explanation['summary'], 'Missing interest method in explanation')
        require(len(row['input_signature']) == 64 and row['algorithm_version'] == 'careercoach-explainable-v2.0', 'Missing version/signature')


def monotonicity_checks(items, bank_version):
    checks = 0
    for mode in MODE_COUNTS:
        chosen = [item for item in items if mode == 'detailed' or item['quick_core']]
        baseline = [{'id': i['code'], 'dimension': i['dimension'], 'rating': 2} for i in chosen]
        before = score_answers(baseline, mode=mode, bank_version=bank_version)
        for dimension in DIMENSIONS:
            raised = [dict(row, rating=4 if row['dimension'] == dimension else row['rating']) for row in baseline]
            after = score_answers(raised, mode=mode, bank_version=bank_version)
            require(after['scores'][dimension] >= before['scores'][dimension], 'Assessment monotonicity failure')
            require(all(after['scores'][t] == before['scores'][t] for t in DIMENSIONS if t != dimension), 'Unrelated assessment dimension changed')
            checks += 1
    return checks
