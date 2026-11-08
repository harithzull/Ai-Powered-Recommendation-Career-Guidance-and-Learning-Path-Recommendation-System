"""Offline synthetic comparison. Run from repository root; never touches db.sqlite3."""
import argparse
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DJANGO_SETTINGS_MODULE'] = 'careercoach.test_settings'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-only', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with patch('socket.socket.connect', side_effect=AssertionError('Evaluation must remain offline')):
        import django
        django.setup()
        from django.conf import settings
        from django.core.management import call_command
        from django.test import override_settings
        assert settings.DATABASES['default']['NAME'] == ':memory:'
        call_command('migrate', verbosity=0)
        from recommender.evaluation import compact, deterministic_embeddings, seed_synthetic
        from recommender.recommendations import get_recommendations
        profiles = {}
        with deterministic_embeddings(), override_settings(RECOMMENDATION_ENGINE='legacy'):
            users = seed_synthetic()
            for name, user in users:
                profiles[name] = {'legacy': compact(get_recommendations(user, top_n=10))}
        if not args.baseline_only:
            with override_settings(RECOMMENDATION_ENGINE='v2', RECOMMENDATION_SEMANTIC_ENABLED=False):
                for name, user in users:
                    rows = get_recommendations(user, top_n=10)
                    profiles[name]['v2'] = compact(rows)
                    profiles[name]['details'] = [{k: r[k] for k in ('career_id', 'components', 'explanation', 'riasec', 'skill_alignment')} for r in rows]
                    before = [r['career'] for r in profiles[name]['legacy']]
                    after = [r['career'].title for r in rows]
                    profiles[name]['rank_changes'] = {title: before.index(title)-after.index(title) for title in after}
                    profiles[name]['evidence_coverage'] = {
                        component: sum(row['components'][component]['available'] for row in rows)
                        for component in ('interest', 'skill', 'background')}
                    profiles[name]['explanation_completeness'] = {
                        'recommendations': len(rows),
                        'structured_explanations': sum(all(key in row['explanation'] for key in
                            ('summary', 'supporting_evidence', 'uncertain_suggestions', 'unavailable_evidence', 'score_meaning')) for row in rows)}
                    profiles[name]['potential_anomalies'] = [
                        {'career': row['career'].title, 'warning': 'No comparable evidence: neutral score, alphabetical tie-break.'}
                        for row in rows if not any(c['available'] for c in row['components'].values())]
                    profiles[name]['missing_data'] = {
                        row['career'].title: row['explanation']['unavailable_evidence'] for row in rows}
            baseline = Path(__file__).resolve().parents[1]/'docs/evaluation/phase2c-legacy-baseline.json'
            recorded = json.loads(baseline.read_text(encoding='utf-8'))
            if any(recorded['profiles'][name]['legacy'] != data['legacy'] for name, data in profiles.items()):
                raise AssertionError('Legacy engine differs from the recorded pre-change baseline')
        report = {'synthetic_only': True, 'embedding_fixture': 'orthonormal four-skill vectors; unknown terms zero',
                  'accuracy_claim': 'None. Controlled behavior comparison, not real student outcomes.', 'profiles': profiles}
        if not args.baseline_only:
            report['limitations_and_anomalies'] = [
                'Synthetic fixtures do not establish accuracy, fairness, employability or real-world relevance.',
                'All occupation interest evidence in these fixtures is missing; all alignments are industry proxies.',
                'Flat interests yield neutral scores: deterministic alphabetical ties are not meaningful career differences.',
                'Legacy repetitions/aliases can alter semantic coverage; v2 counts exact canonical identities only.',
                'Legacy importance favors first relation; v2 treats all relations equally because weights are unverified.',
                'Broader genuinely distinct reports can increase coverage; the system cannot verify self-reported possession.',
                'Semantic proposals are disabled in this comparison; threshold behavior is tested separately with fixed vectors.',
                'Education is a broad proxy and may favor familiar fields; no real-user subgroup fairness claim is possible.']
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
        print(f'Wrote synthetic comparison: {args.output}')


if __name__ == '__main__':
    main()
