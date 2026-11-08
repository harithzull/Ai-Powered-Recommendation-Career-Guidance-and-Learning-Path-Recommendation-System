import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import mock_open, patch

import numpy as np
from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import TestCase, SimpleTestCase, override_settings
from django.utils import timezone

from accounts.models import UserProfile
from assessment.models import AssessmentSession, QuestionBank, RIASECAnswer, SkillRating, UserResponse
from recommender.cache import _from_json, _signature, _to_json, compute_and_cache, get_cached_or_compute, invalidate, RecommendationUnavailable
from recommender.engine.candidates import candidates
from recommender.engine.config import configuration
from recommender.engine.context import background
from recommender.engine.interests import alignment, student_interests
from recommender.engine.ranking import combine
from recommender.engine.skills import alignment as skills_alignment, reported_skills, semantic_candidates
from recommender.evaluation import compact, deterministic_embeddings, seed_synthetic
from recommender.models import CachedRecommendation, Career, CareerEnrichment, CareerSkill, RecommendationRun, Skill, SkillAlias
from recommender.recommendations import get_recommendations


@override_settings(RECOMMENDATION_ENGINE='v2', RECOMMENDATION_SEMANTIC_ENABLED=False)
class EngineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users = dict(seed_synthetic())
        cls.user = cls.users['analytic']
        cls.software = Career.objects.get(title='Synthetic Software')
        cls.python = Skill.objects.get(name='Python')

    def response(self, user=None):
        return UserResponse.objects.get(user=user or self.user)

    def reports(self, user=None):
        return reported_skills(self.response(user), configuration())

    def test_candidates_include_all_careers_and_prefetch_relations(self):
        Career.objects.create(title='Unknown', industry='Unknown')
        with self.assertNumQueries(2):
            rows = candidates()
            self.assertEqual(len(rows), 4)
            for career in rows:
                list(career.career_skills.all())
                getattr(career, 'enrichment', None)

    def test_legacy_answers_map_1_to_5_to_0_to_1_without_rewriting_answers(self):
        profile = student_interests(self.response())
        self.assertEqual(profile['profile']['I'], 1)
        self.assertEqual(profile['profile']['A'], 0)
        self.assertEqual(profile['profile']['R'], .5)
        self.assertEqual(self.response().riasec_answers.count(), 6)

    def session(self, version='careercoach-mean-v2', user=None, counts=None, **extra):
        user = user or self.user
        bank = QuestionBank.objects.first()
        result = {'scores': dict(zip('RIASEC', [50, 100, 0, 25, 25, 75])),
                  'compatibility_profile': dict(zip('RIASEC', [.6, 1, .2, .4, .4, .8])),
                  'counts': counts or dict.fromkeys('RIASEC', 3)}
        result.update(extra)
        session = AssessmentSession.objects.create(user=user, bank=bank, mode='quick', status='completed',
            scoring_version=version, result=result, completed_at=timezone.now())
        UserResponse.objects.filter(user=self.user).update(active_session=session)
        return session

    def test_stored_phase2b_scores_are_used_without_rescoring(self):
        self.session()
        self.assertEqual(student_interests(self.response())['profile'], student_interests(
            self.response(self.users['alias_duplicate']))['profile'])

    def test_legacy_session_compatibility_and_unknown_scorer(self):
        self.session(version='legacy-mean-div5-v1')
        self.assertAlmostEqual(student_interests(self.response())['profile']['R'], .5)
        AssessmentSession.objects.filter(pk=self.response().active_session_id).update(scoring_version='unknown-v999')
        self.assertEqual(student_interests(self.response())['profile'], {})

    def test_incomplete_and_cross_user_sessions_are_rejected(self):
        session = self.session(user=self.users['creative'])
        with self.assertRaises(ValueError):
            student_interests(self.response())
        AssessmentSession.objects.filter(pk=session.pk).update(user=self.user, status='in_progress')
        with self.assertRaises(ValueError):
            student_interests(self.response())

    def test_unanswered_dimension_is_missing_not_zero_dislike(self):
        self.session(counts=dict.fromkeys('RIASEC', 0))
        result = alignment(student_interests(self.response()), self.software)
        self.assertFalse(result['available'])
        self.assertIsNone(result['score'])

    def enrich(self, profile=None, metadata=None, status='reviewed'):
        profile = profile or dict(zip('RIASEC', [.5, 1, 0, .25, .25, .75]))
        metadata = metadata or {'riasec_profile': {'review_status': 'reviewed', 'source': 'Synthetic fixture only',
            'method': 'Synthetic test profile, not real occupation data', 'version': 'test-1',
            'reviewer': 'test fixture', 'reviewed_at': '2026-11-08', 'scale': 'descriptive_interest_0_1'}}
        return CareerEnrichment.objects.create(career=self.software, riasec_profile=profile,
            review_status=status, review_metadata=metadata)

    def test_reviewed_occupation_profile_l1_and_provenance(self):
        self.enrich()
        result = alignment(student_interests(self.response()), Career.objects.get(pk=self.software.pk))
        self.assertEqual(result['method'], 'occupation_normalized_l1')
        self.assertEqual(result['score'], 1)
        self.assertEqual(set(result['differences']), set('RIASEC'))
        self.assertEqual(result['provenance']['version'], 'test-1')

    def test_review_of_family_does_not_validate_interest_profile(self):
        self.enrich(metadata={'evidence': 'Reviewed family only'})
        result = alignment(student_interests(self.response()), Career.objects.get(pk=self.software.pk))
        self.assertEqual(result['method'], 'industry_fallback')

    def test_occupation_profile_requires_a_documented_comparable_scale(self):
        enrichment = self.enrich()
        del enrichment.review_metadata['riasec_profile']['scale']
        career = Career.objects.get(pk=self.software.pk)
        career.enrichment = enrichment
        self.assertEqual(alignment(student_interests(self.response()), career)['method'], 'industry_fallback')

    def test_l1_distance_uses_each_dimension_with_no_holland_tie_bias(self):
        target = dict(zip('RIASEC', [.25, .75, .25, .5, .5, .5]))
        self.enrich(profile=target)
        result = alignment(student_interests(self.response()), Career.objects.get(pk=self.software.pk))
        self.assertAlmostEqual(result['score'], .75)

    def test_removed_user_profile_does_not_reuse_a_cached_reverse_relation(self):
        self.assertIsNotNone(self.user.profile)
        get_recommendations(self.user)
        UserProfile.objects.filter(user=self.user).delete()
        row = get_recommendations(self.user)[0]
        self.assertFalse(row['components']['background']['available'])

    def test_unreviewed_profile_fallback_and_no_missing_profile_penalty(self):
        before = get_recommendations(self.user)
        self.enrich(status='needs_review')
        after = get_recommendations(self.user)
        self.assertEqual(compact(before), compact(after))

    def test_partial_and_nonfinite_occupation_profiles_fall_back(self):
        enrichment = self.enrich()
        for invalid in ({'I': 1}, dict.fromkeys('RIASEC', float('nan')), dict.fromkeys('RIASEC', True)):
            enrichment.riasec_profile = invalid
            career = Career.objects.get(pk=self.software.pk)
            career.enrichment = enrichment
            self.assertEqual(alignment(student_interests(self.response()), career)['method'], 'industry_fallback')

    def test_flat_student_and_flat_occupation_are_not_artificial_perfect_matches(self):
        self.enrich()
        career = Career.objects.get(pk=self.software.pk)
        result = alignment(student_interests(self.response(self.users['flat_missing'])), career)
        self.assertEqual(result['score'], .5)
        self.assertEqual(result['method'], 'industry_fallback')
        career.enrichment.riasec_profile = dict.fromkeys('RIASEC', .5)
        self.assertEqual(alignment(student_interests(self.response()), career)['method'], 'industry_fallback')

    def test_unknown_industry_and_absent_profile_have_no_implicit_zero(self):
        result = alignment(student_interests(self.response()), Career(industry='Unknown'))
        self.assertFalse(result['available'])
        result = background(self.user, Career(industry='Unknown'))
        self.assertFalse(result['available'])

    def test_canonical_alias_and_free_text_duplicates_count_once(self):
        response = self.response(self.users['alias_duplicate'])
        response.free_text_skills = ' python , PY, Python'
        response.save()
        reports = reported_skills(response, configuration())
        self.assertEqual(len(reports['items']), 1)
        result = skills_alignment(reports, self.software)
        self.assertEqual(result['score'], .5)
        self.assertEqual(result['matched_skills'][0]['self_reported_rating'], 5)
        self.assertFalse(result['matched_skills'][0]['proficiency_verified'])

    def test_reviewed_exact_alias_is_confirmed_but_related_or_unreviewed_is_not(self):
        response = self.response()
        response.skill_ratings.all().delete()
        SkillRating.objects.create(response=response, skill_name='Py', rating=3)
        self.assertEqual(skills_alignment(self.reports(), self.software)['matched_skills'][0]['method'], 'reviewed_alias')
        SkillAlias.objects.filter(name='Py').update(kind='related')
        self.assertEqual(skills_alignment(self.reports(), self.software)['matched_skills'], [])
        SkillAlias.objects.filter(name='Py').update(kind='exact', review_status='needs_review')
        self.assertEqual(skills_alignment(self.reports(), self.software)['matched_skills'], [])

    def test_missing_alias_evidence_and_normalized_canonical_collisions_are_not_confirmed(self):
        SkillAlias.objects.filter(name='Py').update(review_metadata={})
        result = reported_skills(self.response(self.users['alias_duplicate']), configuration())
        self.assertEqual(len(result['items']), 2)
        Skill.objects.create(name='PYTHON')
        result = self.reports()
        self.assertIsNone(next(r for r in result['items'] if r['name'] == 'Python')['skill_id'])

    def test_ratings_do_not_invent_proficiency_comparisons(self):
        before = get_recommendations(self.user)
        SkillRating.objects.filter(response=self.response()).update(rating=1)
        self.assertEqual(compact(before), compact(get_recommendations(self.user)))

    def test_missing_reports_or_relations_are_unavailable_not_zero(self):
        result = skills_alignment(self.reports(self.users['flat_missing']), self.software)
        self.assertFalse(result['available'])
        result = skills_alignment(self.reports(), Career.objects.create(title='Empty career'))
        self.assertIsNone(result['score'])
        self.assertEqual(result['opportunities'], [])

    def test_related_skills_classified_without_unverified_legacy_requirements(self):
        result = skills_alignment(self.reports(self.users['creative']), self.software)
        self.assertEqual(len(result['opportunities']), 2)
        for item in result['opportunities']:
            self.assertEqual(item['classification'], 'not_reported')
            self.assertEqual(item['relation_type'], 'unspecified')
            self.assertEqual(item['proficiency_requirement'], 'unknown')
        self.assertEqual(result['verified_proficiency_gaps'], [])

    def test_verified_relation_priority_not_legacy_importance(self):
        CareerSkill.objects.filter(career=self.software, skill__name='SQL').update(
            quality_status='reviewed', source_relation_type='essential', source_metadata={'evidence': 'Synthetic source only'})
        result = skills_alignment(self.reports(self.users['creative']), self.software)
        self.assertEqual(result['opportunities'][0]['name'], 'SQL')
        self.assertEqual(result['opportunities'][0]['relation_type'], 'essential')

    def test_semantic_proposals_never_inflate_confirmed_coverage(self):
        result = skills_alignment(self.reports(self.users['creative']), self.software,
            {'Python': {'reported_name': 'Writing', 'cosine_similarity': .95, 'counted_in_score': False}}, 'available')
        self.assertEqual(result['score'], 0)
        self.assertEqual(result['potential_matches'][0]['classification'], 'potential_semantic_match')
        self.assertEqual(len(result['opportunities']), 2)

    @override_settings(RECOMMENDATION_SEMANTIC_ENABLED=True)
    def test_semantic_threshold_and_local_model_failures(self):
        with patch('numpy.load', return_value=np.eye(2)), \
             patch('pathlib.Path.read_text', return_value=json.dumps(['Python', 'SQL'])), \
             patch('recommender.embeddings.get_model') as model:
            # cosines .8 and .6; only .8 meets default .75 cutoff.
            model.return_value.encode.return_value = np.array([[.8, .6]])
            reports = {'items': [{'name': 'Synthetic unknown'}]}
            suggestions, status = semantic_candidates(reports, configuration())
            self.assertEqual(status, 'available')
            self.assertEqual(set(suggestions), {'Python'})
            self.assertFalse(suggestions['Python']['counted_in_score'])
            model.side_effect = OSError('local model missing')
            self.assertEqual(semantic_candidates(reports, configuration()), ({}, 'unavailable'))

    def test_disabled_semantic_never_loads_model(self):
        with patch('recommender.embeddings.get_model') as model:
            self.assertEqual(semantic_candidates(self.reports(), configuration()), ({}, 'disabled'))
            get_recommendations(self.user)
            model.assert_not_called()

    def test_broad_duplicates_do_not_improve_ranking_and_unique_budget_is_bounded(self):
        baseline = compact(get_recommendations(self.user))
        response = self.response()
        response.free_text_skills = ','.join(['Py', 'PYTHON']*50)
        response.save()
        self.assertEqual(baseline, compact(get_recommendations(self.user)))
        response.free_text_skills = ','.join(f'Unknown {i}' for i in range(100))
        response.save()
        reports = self.reports()
        self.assertEqual(len(reports['items']), 30)
        self.assertTrue(reports['truncated'])

    def test_ranking_formula_components_and_explanations(self):
        row = get_recommendations(self.user)[0]
        self.assertEqual(row['career'].title, 'Synthetic Software')
        self.assertEqual(row['final_score'], round(100*(.75*.45 + 1*.4 + 1*.15), 1))
        self.assertAlmostEqual(sum(c['contribution_points'] for c in row['components'].values()), 88.75)
        self.assertEqual(row['algorithm_version'], 'careercoach-explainable-v2.0')
        self.assertEqual(row['riasec']['method'], 'industry_fallback')
        self.assertIn('Python', row['why'])
        self.assertNotIn('Design', row['why'])
        self.assertIn('not a probability', row['explanation']['score_meaning'])
        self.assertEqual(len(row['input_signature']), 64)

    def test_missing_components_renormalize_and_all_missing_neutral(self):
        row = get_recommendations(self.users['flat_missing'])[0]
        self.assertEqual(row['final_score'], 50)
        self.assertEqual(row['components']['interest']['effective_weight'], 1)
        self.assertEqual(row['components']['skill']['effective_weight'], 0)
        self.assertEqual(combine({k: {'score': None, 'available': False} for k in configuration().weights}, configuration().weights), 50)

    def test_ties_are_stable_across_recomputations(self):
        rows = get_recommendations(self.users['flat_missing'])
        self.assertEqual([r['career'].title for r in rows], ['Synthetic Data', 'Synthetic Design', 'Synthetic Software'])
        self.assertEqual(compact(rows), compact(get_recommendations(self.users['flat_missing'])))

    def test_partial_assessment_no_model_or_results(self):
        UserResponse.objects.filter(user=self.user).update(completed_at=None)
        self.assertEqual(get_recommendations(self.user), [])

    def test_experience_is_descriptive_not_an_invented_requirement(self):
        before = get_recommendations(self.user)
        UserProfile.objects.filter(user=self.user).update(experience_level='3+ years')
        # Re-fetch user avoids a deliberately cached Django reverse relation.
        self.user.refresh_from_db()
        after = get_recommendations(self.user)
        self.assertEqual(compact(before), compact(after))
        self.assertEqual(after[0]['components']['background']['experience_context'], '3+ years')

    def test_extended_contract_survives_cache_roundtrip(self):
        rows = get_recommendations(self.user)
        restored = _from_json(_to_json(rows))
        for key in ('algorithm_version', 'career_id', 'components', 'riasec', 'matched_skills', 'opportunities', 'explanation', 'input_signature'):
            self.assertEqual(rows[0][key], restored[0][key])

    def test_cache_hit_history_and_explicit_invalidation_preserves_history(self):
        rows = compute_and_cache(self.user)
        with patch('recommender.cache.get_recommendations') as compute:
            self.assertEqual(get_cached_or_compute(self.user)[0]['why'], rows[0]['why'])
            compute.assert_not_called()
        self.assertEqual(self.user.recommendation_runs.count(), 1)
        invalidate(self.user)
        self.assertEqual(self.user.recommendation_runs.count(), 1)

    def test_each_relevant_content_change_invalidates_signature(self):
        actions = [
            lambda: SkillRating.objects.filter(response=self.response(), skill_name='Python').update(rating=1),
            lambda: UserResponse.objects.filter(user=self.user).update(free_text_skills='extra'),
            lambda: RIASECAnswer.objects.filter(response=self.response(), question__riasec_type='I').update(rating=2),
            lambda: UserProfile.objects.filter(user=self.user).update(experience_level='Internship'),
            lambda: Career.objects.filter(pk=self.software.pk).update(summary='changed'),
            lambda: Skill.objects.filter(pk=self.python.pk).update(category='knowledge'),
            lambda: CareerSkill.objects.filter(career=self.software).update(source_relation_type='optional'),
            lambda: SkillAlias.objects.filter(name='Py').update(review_status='needs_review'),
            lambda: self.enrich(),
        ]
        for action in actions:
            before = _signature(self.user)
            action()
            self.assertNotEqual(before, _signature(self.user))

    def test_stored_session_result_changes_invalidate(self):
        session = self.session()
        before = _signature(self.user)
        AssessmentSession.objects.filter(pk=session.pk).update(result={'scores': {}})
        self.assertNotEqual(before, _signature(self.user))

    def test_config_and_version_changes_invalidate_without_user_edits(self):
        before = _signature(self.user)
        for override in ({'RECOMMENDATION_ENGINE': 'legacy'}, {'RECOMMENDATION_SEMANTIC_ENABLED': True},
                         {'RECOMMENDATION_SEMANTIC_THRESHOLD': .9}, {'RECOMMENDATION_MODEL_REVISION': 'new'},
                         {'RECOMMENDATION_WEIGHTS': {'interest': .5, 'skill': .4, 'background': .1}}):
            with override_settings(**override):
                self.assertNotEqual(before, _signature(self.user))

    @override_settings(RECOMMENDATION_SEMANTIC_ENABLED=True)
    def test_embedding_artifact_bytes_invalidate(self):
        with patch('pathlib.Path.read_bytes', return_value=b'artifact one'):
            before = _signature(self.user)
        with patch('pathlib.Path.read_bytes', return_value=b'artifact two'):
            self.assertNotEqual(before, _signature(self.user))

    def test_changed_inputs_during_compute_are_not_cached(self):
        with patch('recommender.cache._signature', side_effect=['before', 'after']):
            with self.assertRaises(RecommendationUnavailable):
                compute_and_cache(self.user)
        self.assertFalse(CachedRecommendation.objects.filter(user=self.user).exists())
        self.assertFalse(RecommendationRun.objects.filter(user=self.user).exists())

    def test_cross_user_cache_and_history_isolation(self):
        compute_and_cache(self.user)
        compute_and_cache(self.users['creative'])
        self.assertNotEqual(get_cached_or_compute(self.user)[0]['career'].title,
                            get_cached_or_compute(self.users['creative'])[0]['career'].title)
        self.client.force_login(self.user)
        response = self.client.get('/recommendations/history/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['page']), 1)
        self.assertEqual(response.context['page'][0].user_id, self.user.pk)
        self.client.logout()
        self.assertEqual(self.client.get('/recommendations/history/').status_code, 302)

    def test_history_is_read_only_and_post_not_allowed(self):
        compute_and_cache(self.user)
        run = self.user.recommendation_runs.get()
        run.results_json = '[]'
        with self.assertRaises(ValidationError):
            run.save()
        self.client.force_login(self.user)
        self.assertEqual(self.client.post('/recommendations/history/').status_code, 405)

    def test_migration_archives_verbatim_legacy_cache(self):
        cache = CachedRecommendation.objects.create(user=self.user, results_json='legacy opaque data', input_signature='old')
        migration = importlib.import_module('recommender.migrations.0006_cachedrecommendation_algorithm_version_and_more')
        migration.archive_existing(apps, SimpleNamespace(connection=SimpleNamespace(alias='default')))
        cache.refresh_from_db()
        self.assertEqual(cache.run.results_json, 'legacy opaque data')
        self.assertEqual(cache.run.created_at, cache.computed_at)
        self.assertEqual(cache.results_json, 'legacy opaque data')

    def test_existing_saved_roadmap_and_progress_survive_recomputation(self):
        from roadmap.generator import get_or_create_roadmap
        from roadmap.models import SavedRoadmap, RoadmapProgress
        saved = SavedRoadmap.objects.create(user=self.user, career=self.software, title='Original', overview='Keep',
                                           steps_json='[{"index":0,"label":"Original"}]')
        progress = RoadmapProgress.objects.create(user=self.user, career=self.software, step_index=0)
        compute_and_cache(self.user)
        invalidate(self.user)
        with patch('roadmap.generator.generate_roadmap') as generate:
            self.assertEqual(get_or_create_roadmap(self.user, self.software)[1], 'Original')
            generate.assert_not_called()
        saved.refresh_from_db()
        progress.refresh_from_db()
        self.assertEqual(saved.overview, 'Keep')
        self.assertEqual(progress.step_index, 0)

    @patch('roadmap.generator._call_groq', return_value=None)
    def test_new_roadmap_uses_opportunities_and_no_legacy_embeddings(self, groq):
        from roadmap.generator import generate_roadmap
        with patch('roadmap.generator.semantic_skill_match') as semantic:
            steps, _, _ = generate_roadmap(self.users['creative'], self.software)
            semantic.assert_not_called()
        self.assertIn('not verified deficiencies', groq.call_args.args[0])
        self.assertTrue(any('confirm your current experience' in s.why_it_matters for s in steps))
        self.assertFalse(any('core requirement' in s.why_it_matters for s in steps))

    def test_results_template_shows_evidence_and_safe_point_labels(self):
        self.client.force_login(self.user)
        response = self.client.get('/recommendations/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not probabilities')
        self.assertContains(response, 'industry_fallback')
        self.assertContains(response, 'Scoring evidence')

    @override_settings(RECOMMENDATION_ENGINE='legacy')
    def test_recorded_pre_change_legacy_baseline_is_reproducible(self):
        baseline = json.loads((Path(settings.BASE_DIR)/'docs/evaluation/phase2c-legacy-baseline.json').read_text(encoding='utf-8'))
        with deterministic_embeddings():
            for name, user in self.users.items():
                self.assertEqual(compact(get_recommendations(user, top_n=10)), baseline['profiles'][name]['legacy'])


class ConfigurationTests(SimpleTestCase):
    def test_legacy_vector_store_reloads_when_artifacts_are_rebuilt(self):
        from recommender import matching
        with patch.object(matching, '_skill_vectors', None), patch.object(matching, '_skill_index', None), \
             patch.object(matching, '_store_state', None), \
             patch('pathlib.Path.stat', return_value=SimpleNamespace(st_mtime_ns=1, st_size=10)) as stat, \
             patch('builtins.open', mock_open(read_data='["Python"]')), \
             patch('numpy.load', side_effect=[np.array([[1, 0]]), np.array([[0, 1]])]) as load:
            self.assertEqual(matching._load_store()[0].tolist(), [[1, 0]])
            matching._load_store()
            self.assertEqual(load.call_count, 1)
            stat.return_value = SimpleNamespace(st_mtime_ns=2, st_size=10)
            self.assertEqual(matching._load_store()[0].tolist(), [[0, 1]])
            self.assertEqual(load.call_count, 2)

    def test_invalid_weights_are_rejected(self):
        for weights in ({'interest': 1}, {'interest': -.1, 'skill': .6, 'background': .5},
                        {'interest': float('nan'), 'skill': .4, 'background': .15},
                        {'interest': True, 'skill': 0, 'background': 0}):
            with override_settings(RECOMMENDATION_WEIGHTS=weights), self.assertRaises(ValueError):
                configuration()

    def test_invalid_engine_or_semantic_threshold_rejected(self):
        for override in ({'RECOMMENDATION_ENGINE': 'typo'}, {'RECOMMENDATION_SEMANTIC_THRESHOLD': 2},
                         {'RECOMMENDATION_SEMANTIC_THRESHOLD': float('nan')}):
            with override_settings(**override), self.assertRaises(ValueError):
                configuration()

    @override_settings(RECOMMENDATION_ENGINE='v2', RECOMMENDATION_WEIGHTS={'interest': .5, 'skill': .5, 'background': 0})
    def test_configurable_weights_and_zero_weight_components(self):
        components = {'interest': {'score': 1, 'available': True}, 'skill': {'score': 0, 'available': True},
                      'background': {'score': 1, 'available': True}}
        self.assertEqual(combine(components, configuration().weights), 50)
        self.assertEqual(components['background']['contribution_points'], 0)
