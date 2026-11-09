"""Safety/contract tests use tiny fixtures; the 100-profile run uses the real catalog."""
from contextlib import closing
import csv
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase, SimpleTestCase, override_settings

from assessment.models import AssessmentSession, InterestItem, QuestionBank, SessionItem
from assessment.scoring import DIMENSIONS, score_answers
from recommender.models import Career, CareerSkill, Skill
from recommender.simulation.assertions import check_assessment, check_recommendations, monotonicity_checks
from recommender.simulation.catalog import COPY_MODELS, fingerprints, install_snapshot, read_snapshot, require_isolation
from recommender.simulation.profiles import generate_profiles, scenario_counts
from recommender.simulation.reports import export_reports, validate_output_paths
from recommender.simulation.runner import execute


class GeneratorTests(SimpleTestCase):
    def fixtures(self):
        return ([{'id': n, 'name': f'Skill {n}'} for n in range(1, 21)],
                [{'code': f'{t}{n}', 'dimension': t, 'quick_core': n < 3} for t in DIMENSIONS for n in range(6)])

    def generate(self, **kwargs):
        return generate_profiles(*self.fixtures(), **kwargs)

    def test_exact_distribution_unique_ids_seeds_and_repeatability(self):
        first = self.generate()
        self.assertEqual(first, self.generate())
        self.assertNotEqual(first, self.generate(seed=43))
        self.assertEqual(len({p['profile_id'] for p in first}), 100)
        self.assertEqual(len({p['seed'] for p in first}), 100)
        self.assertEqual(scenario_counts(100), {'dominant': 12, 'mixed': 18, 'neutral': 10, 'extreme': 10, 'skill_background': 20, 'randomized': 30})
        dominant = [p for p in first if p['scenario'] == 'dominant']
        for t in DIMENSIONS:
            self.assertEqual(sum(p['preferences'][t] == 5 for p in dominant), 2)

    def test_scaling_counts_and_valid_ratings(self):
        for count in (1, 3, 7, 99, 101):
            profiles = self.generate(count=count)
            self.assertEqual(len(profiles), count)
            self.assertTrue(all(len(p['responses']) == 36 and all(type(v) is int and 1 <= v <= 5 for v in p['responses'].values()) for p in profiles))

    def test_empty_and_duplicate_skills_use_catalog_identities(self):
        profiles = self.generate()
        self.assertTrue(any(not p['skills'] for p in profiles))
        self.assertTrue(any(p['free_text_skills'] for p in profiles))
        for p in profiles:
            self.assertTrue(all(s['name'] == f'Skill {s["skill_id"]}' for s in p['skills']))
            self.assertEqual(len({s['skill_id'] for s in p['skills']}), len(p['skills']))

    def test_invalid_counts_rejected(self):
        for count in (0, -1, True, 10001):
            with self.assertRaises(ValueError):
                self.generate(count=count)

    def test_neutral_ties_and_both_real_scorer_modes(self):
        skills, items = self.fixtures()
        profile = next(p for p in self.generate() if p['scenario'] == 'neutral')
        for mode in ('quick', 'detailed'):
            answers = [{'id': i['code'], 'dimension': i['dimension'], 'rating': profile['responses'][i['code']]} for i in items if mode == 'detailed' or i['quick_core']]
            result = score_answers(answers, mode=mode, bank_version='synthetic-test')
            check_assessment(answers, result, mode, 'synthetic-test')
            self.assertEqual(result['holland_code'], 'RIA')
            self.assertEqual(result['ties'], [list(DIMENSIONS)])
        self.assertEqual(monotonicity_checks(items, 'synthetic-test'), 12)

    def test_command_launcher_uses_private_subprocess_and_no_orm_access(self):
        # SimpleTestCase fails any accidental default DB query in the parent.
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)/'source.sqlite3'
            source.touch()
            with patch('recommender.management.commands.simulate_profiles.subprocess.run', return_value=SimpleNamespace(returncode=0)) as run:
                call_command('simulate_profiles', count=7, mode='quick', seed=123, source_db=source, output_dir=Path(temp)/'reports')
            command = run.call_args.args[0]
            self.assertIn('7', command)
            self.assertEqual(run.call_args.kwargs['env']['DJANGO_SETTINGS_MODULE'], 'careercoach.simulation_settings')
            self.assertNotIn('GROQ_API_KEY', run.call_args.kwargs['env'])

    def test_command_propagates_worker_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)/'source.sqlite3'
            source.touch()
            with patch('recommender.management.commands.simulate_profiles.subprocess.run', return_value=SimpleNamespace(returncode=1)), self.assertRaises(CommandError):
                call_command('simulate_profiles', source_db=source)

    def test_memory_default_requires_an_explicit_source(self):
        with self.assertRaises(CommandError):
            call_command('simulate_profiles')

    def test_report_destination_cannot_overwrite_a_source_database(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)/'evaluation_summary.json'
            source.write_bytes(b'Source database placeholder')
            with self.assertRaises(ValueError):
                validate_output_paths(temp, source)
            self.assertEqual(source.read_bytes(), b'Source database placeholder')

    def test_spreadsheet_formula_text_is_escaped(self):
        from recommender.simulation.reports import write_csv
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)/'test.csv'
            write_csv(target, [{'title': '=UNTRUSTED()', 'points': 50}])
            with target.open(encoding='utf-8', newline='') as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual(row['title'], "'=UNTRUSTED()")


@override_settings(CAREERCOACH_SIMULATION_ISOLATED=True, RECOMMENDATION_ENGINE='v2', RECOMMENDATION_SEMANTIC_ENABLED=False)
class SimulationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        skill = Skill.objects.create(name='Writing')
        for n in range(6):
            career = Career.objects.create(title=f'Test career {n}', industry='Education' if n % 2 else 'Technology')
            if n < 5:
                CareerSkill.objects.create(career=career, skill=skill)

    def test_normal_settings_cannot_run_synthetic_mutations(self):
        with override_settings(CAREERCOACH_SIMULATION_ISOLATED=False), self.assertRaises(RuntimeError):
            execute(count=1)
        self.assertFalse(User.objects.exists())

    def test_file_database_is_rejected_even_with_marker(self):
        with patch.dict(connection.settings_dict, NAME='normal.sqlite3'), self.assertRaises(RuntimeError):
            require_isolation()

    def test_existing_private_users_are_rejected_instead_of_destroyed(self):
        User.objects.create_user('preexisting')
        with self.assertRaises(AssertionError):
            execute(count=1)
        self.assertTrue(User.objects.filter(username='preexisting').exists())

    def test_real_quick_detailed_lifecycle_ranking_and_exports(self):
        with patch('recommender.embeddings.get_model', side_effect=AssertionError('No embeddings permitted')):
            profiles, runs, checks = execute(count=3)
        self.assertEqual(len(profiles), 3)
        self.assertEqual(len(runs), 6)
        self.assertEqual(AssessmentSession.objects.filter(status='completed').count(), 6)
        self.assertEqual(SessionItem.objects.count(), 3*(18+36))
        self.assertTrue(checks['assertions_passed'])
        self.assertEqual(checks['deterministic_repeats'], 6)
        metadata = {'seed': 42, 'test_date': '2026-11-09', 'fingerprints': {'catalog': 'test', 'assessment_bank': 'test'},
                    'catalog_counts': {'recommender.career': 6}}
        with tempfile.TemporaryDirectory() as temp:
            summary = export_reports(temp, profiles, runs, checks, metadata)
            self.assertEqual(summary['assessment_run_count'], 6)
            self.assertEqual(summary['quick_vs_detailed']['pair_count'], 3)
            with (Path(temp)/'assessment_results_100.csv').open(encoding='utf-8', newline='') as stream:
                assessments = list(csv.DictReader(stream))
            self.assertEqual(len(assessments), 6)
            self.assertEqual(set(json.loads(assessments[0]['scores'])), set(DIMENSIONS))
            with (Path(temp)/'recommendation_results_100.csv').open(encoding='utf-8', newline='') as stream:
                recommendations = list(csv.DictReader(stream))
            self.assertEqual(len(recommendations), 30)
            self.assertIn('input_signature', recommendations[0])
            result = json.loads((Path(temp)/'evaluation_summary.json').read_text(encoding='utf-8'))
            self.assertEqual(result['profile_count'], 3)
            self.assertIn('Software correctness', (Path(temp)/'evaluation_summary.md').read_text(encoding='utf-8'))

    def test_single_mode_and_missing_catalog_evidence(self):
        Career.objects.update(industry='Unknown')
        CareerSkill.objects.all().delete()
        profiles, runs, checks = execute(count=1, mode='quick')
        self.assertEqual(len(runs), 1)
        for row in runs[0]['recommendations']:
            self.assertEqual(row['final_score'], 50)
            self.assertTrue(all(not c['available'] for c in row['components'].values()))
        check_recommendations(runs[0]['recommendations'], set(Career.objects.values_list('pk', flat=True)))
        from recommender.simulation.reports import summarize
        summary = summarize(profiles, runs, checks, {'seed': 42})
        self.assertEqual(summary['tie_diagnostics']['runs_with_any_unrounded_top_five_tie'], 1)
        self.assertEqual(summary['tie_diagnostics']['runs_with_all_five_unrounded_scores_tied'], 1)
        self.assertTrue(any('tied' in warning for warning in summary['warnings']))

    def test_assertions_reject_invalid_or_unsupported_results(self):
        _, runs, _ = execute(count=1, mode='detailed')
        rows = runs[0]['recommendations']
        rows[0]['skill_alignment']['verified_proficiency_gaps'] = ['invented']
        with self.assertRaises(AssertionError):
            check_recommendations(rows, set(Career.objects.values_list('pk', flat=True)))

    def make_source(self, path):
        # A tiny SQLite source with exact model columns plus a secret user table.
        # The reader must copy only the allowlisted public catalog/bank tables.
        with closing(sqlite3.connect(path)) as db, db:
            for model in COPY_MODELS:
                columns = ','.join('"'+f.column+'"' for f in model._meta.fields)
                db.execute(f'CREATE TABLE "{model._meta.db_table}" ({columns})')
                for row in model.objects.order_by('pk').values_list(*[f.attname for f in model._meta.fields]):
                    values = [json.dumps(v) if isinstance(v, (dict, list)) else v for v in row]
                    db.execute(f'INSERT INTO "{model._meta.db_table}" VALUES ({",".join("?" for _ in values)})', values)
            db.execute('CREATE TABLE auth_user (password TEXT)')
            db.execute("INSERT INTO auth_user VALUES ('DO_NOT_COPY_PRIVATE_USER_DATA')")

    def test_source_read_only_and_only_public_tables_are_copied(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)/'source.sqlite3'
            self.make_source(source)
            before = source.read_bytes()
            snapshot = read_snapshot(source)
            self.assertEqual(before, source.read_bytes())
            self.assertNotIn('DO_NOT_COPY_PRIVATE_USER_DATA', json.dumps(snapshot))
            self.assertEqual(set(snapshot), {m._meta.label_lower for m in COPY_MODELS})
            self.assertEqual(fingerprints(snapshot), fingerprints(read_snapshot(source)))

    def test_install_snapshot_preserves_provenance_and_is_guarded(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)/'source.sqlite3'
            self.make_source(source)
            snapshot = read_snapshot(source)
            CareerSkill.objects.all().delete()
            Career.objects.all().delete()
            Skill.objects.all().delete()
            install_snapshot(snapshot)
            self.assertEqual(Career.objects.count(), 6)
            self.assertEqual(Skill.objects.get().source_taxonomy, 'unknown')
            self.assertEqual(InterestItem.objects.filter(bank__status='active', status='active').count(), 36)

    def test_fresh_workers_reproduce_exports_and_signatures_without_source_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)/'source.sqlite3'
            self.make_source(source)
            original = source.read_bytes()
            exports = []
            for index in range(2):
                target = Path(temp)/f'reports-{index}'
                result = subprocess.run([sys.executable, '-B', str(settings.BASE_DIR/'scripts/simulate_profiles.py'),
                    '--source-db', str(source), '--output-dir', str(target), '--count', '2', '--mode', 'both', '--seed', '42'],
                    capture_output=True, text=True, encoding='utf-8', timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr)
                rows_by_file = {}
                for name in ('synthetic_profiles_100.csv', 'assessment_results_100.csv', 'recommendation_results_100.csv'):
                    with (target/name).open(encoding='utf-8', newline='') as stream:
                        rows_by_file[name] = [{k: v for k, v in row.items() if not k.endswith('_seconds')} for row in csv.DictReader(stream)]
                exports.append(rows_by_file)
                summary = json.loads((target/'evaluation_summary.json').read_text(encoding='utf-8'))
                self.assertTrue(summary['checks']['source_database_bytes_unchanged'])
            self.assertEqual(original, source.read_bytes())
            self.assertEqual(exports[0], exports[1])
