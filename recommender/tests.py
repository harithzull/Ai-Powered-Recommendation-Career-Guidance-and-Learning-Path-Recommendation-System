import json
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import numpy as np
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from accounts.models import UserProfile
from careercoach.test_utils import UserDataTestCase
from recommender import matching
from recommender.cache import compute_and_cache, get_cached_or_compute, invalidate
from recommender.models import CachedRecommendation, Career, CareerSkill, Skill
from recommender.recommendations import get_recommendations
from recommender.scoring import background_score, interest_score, normalized_riasec


class RiasecScoringTests(SimpleTestCase):
    def test_average_avoids_adaptive_question_count_bias(self):
        scores = normalized_riasec([("R", 5), ("R", 3), ("I", 4)])
        self.assertEqual(scores["R"], 0.8)
        self.assertEqual(scores["I"], 0.8)
        self.assertEqual(scores["A"], 0)

    def test_empty_and_boundary_scores(self):
        self.assertEqual(normalized_riasec([]), dict.fromkeys("RIASEC", 0))
        self.assertEqual(normalized_riasec([("R", 1)])["R"], 0.2)
        self.assertEqual(normalized_riasec([("R", 5)])["R"], 1)

    def test_interest_uses_industry_types_and_unknown_is_neutral(self):
        self.assertEqual(interest_score({"R": 0.4, "I": 0.8}, Career(industry="Technology")), 0.6)
        self.assertEqual(interest_score({}, Career(industry="Unknown")), 0.5)


class RecommendationTests(UserDataTestCase):
    def result(self, career=None):
        return {"career": career or self.career, "final_score": 75, "interest_pct": 80,
                "skill_pct": 70, "background_pct": 65, "missing_skills": ["SQL"],
                "extra_missing_count": 0, "why": "Test explanation"}

    def test_background_alignment_and_experience(self):
        response = self.user.assessment_response
        self.assertEqual(background_score(response, self.career), 0.91)
        self.assertEqual(background_score(response, Career(industry="Finance")), 0.49)
        UserProfile.objects.filter(user=self.user).update(experience_level="3+ years")
        self.assertEqual(background_score(type(response).objects.get(pk=response.pk), self.career), 1)

    @patch("recommender.recommendations.semantic_skill_match_from_vectors")
    @patch("recommender.recommendations.encode_user_skills", return_value=np.ones((1, 2)))
    def test_weighted_ranking_and_rounding(self, encode, match):
        other = Career.objects.create(title="Analyst", industry="Technology")
        match.side_effect = lambda vectors, career: (0.9, []) if career.pk == self.career.pk else (0.2, ["SQL"])
        results = get_recommendations(self.user)
        self.assertEqual([r["career"].pk for r in results], [self.career.pk, other.pk])
        self.assertEqual(results[0]["final_score"], round((0.8 * 0.45 + 0.9 * 0.4 + 0.91 * 0.15) * 100, 1))
        encode.assert_called_once()
        self.assertEqual(results[1]["missing_skills"], ["SQL"])

    @patch("recommender.recommendations.encode_user_skills")
    def test_partial_assessment_does_not_run_embedding(self, encode):
        from assessment.models import UserResponse
        UserResponse.objects.filter(user=self.user).update(completed_at=None)
        self.assertEqual(get_recommendations(self.user), [])
        encode.assert_not_called()

    @patch("recommender.cache.get_recommendations")
    def test_cache_hit_avoids_recomputation(self, compute):
        compute.return_value = [self.result()]
        first = compute_and_cache(self.user)
        second = get_cached_or_compute(self.user)
        self.assertEqual(first[0]["final_score"], second[0]["final_score"])
        self.assertEqual(second[0]["career"].pk, self.career.pk)
        compute.assert_called_once()

    @patch("recommender.cache.get_recommendations")
    def test_small_first_request_caches_five_results(self, compute):
        compute.return_value = [self.result() for _ in range(5)]
        self.assertEqual(len(get_cached_or_compute(self.user, top_n=1)), 1)
        self.assertEqual(len(get_cached_or_compute(self.user, top_n=5)), 5)
        compute.assert_called_once_with(self.user, top_n=5)

    @patch("recommender.cache.get_recommendations")
    def test_cache_and_invalidation_are_user_scoped(self, compute):
        compute.side_effect = lambda user, top_n: [self.result(Career(pk=user.pk, title=user.username))]
        compute_and_cache(self.user)
        compute_and_cache(self.other)
        self.assertEqual(get_cached_or_compute(self.user)[0]["career"].title, self.user.username)
        self.assertEqual(get_cached_or_compute(self.other)[0]["career"].title, self.other.username)
        invalidate(self.user)
        self.assertFalse(CachedRecommendation.objects.filter(user=self.user).exists())
        self.assertTrue(CachedRecommendation.objects.filter(user=self.other).exists())

    @patch("recommender.cache.get_recommendations")
    def test_corrupt_cache_recovers(self, compute):
        compute.return_value = [self.result()]
        compute_and_cache(self.user)
        for data in ["{", "null", "[{}]"]:
            CachedRecommendation.objects.filter(user=self.user).update(results_json=data)
            with self.subTest(data=data):
                self.assertEqual(get_cached_or_compute(self.user)[0]["career"].pk, self.career.pk)

    @patch("recommender.cache.get_recommendations")
    def test_profile_fingerprint_and_expiry_trigger_recomputation(self, compute):
        compute.return_value = [self.result()]
        compute_and_cache(self.user)
        UserProfile.objects.filter(user=self.user).update(field_of_study="Business")
        get_cached_or_compute(self.user)
        self.assertEqual(compute.call_count, 2)
        CachedRecommendation.objects.filter(user=self.user).update(computed_at=timezone.now() - timedelta(days=2))
        get_cached_or_compute(self.user)
        self.assertEqual(compute.call_count, 3)

    @patch("recommender.cache.get_recommendations")
    def test_weight_change_invalidates_fingerprint(self, compute):
        compute.return_value = [self.result()]
        compute_and_cache(self.user)
        with override_settings(RECOMMENDATION_WEIGHTS={"interest": 0.5, "skill": 0.4, "background": 0.1}):
            get_cached_or_compute(self.user)
        self.assertEqual(compute.call_count, 2)

    @patch("recommender.cache.get_recommendations", side_effect=RuntimeError("private model path"))
    def test_model_failure_is_generic_and_does_not_cache_failure(self, compute):
        response = self.client.get("/recommendations/")
        self.assertEqual(response.status_code, 503)
        self.assertNotContains(response, "private model path", status_code=503)
        self.assertFalse(CachedRecommendation.objects.filter(user=self.user).exists())

    @patch("recommender.cache.get_recommendations")
    def test_navigation_does_not_initiate_computation(self, compute):
        self.assertEqual(self.client.get("/accounts/profile/").status_code, 200)
        compute.assert_not_called()


class MatchingTests(UserDataTestCase):
    @override_settings(SIMILARITY_THRESHOLD=0.5)
    def test_weighted_cosine_similarity_and_core_gap_threshold(self):
        core = Skill.objects.create(name="Python")
        gap = Skill.objects.create(name="SQL")
        CareerSkill.objects.create(career=self.career, skill=core, importance=3, is_core=True)
        CareerSkill.objects.create(career=self.career, skill=gap, importance=1, is_core=True)
        vectors = np.array([[1, 0], [0, 1]], dtype=np.float32)
        with patch("recommender.matching._load_store", return_value=(vectors, {"Python": 0, "SQL": 1})):
            score, missing = matching.semantic_skill_match_from_vectors(np.array([[1, 0]], dtype=np.float32), self.career)
        self.assertAlmostEqual(score, 0.75)
        self.assertEqual(missing, ["SQL"])

    def test_empty_skill_input_uses_zero_vector_without_model(self):
        with patch("recommender.matching._load_store", return_value=(np.ones((2, 384)), {})), patch("recommender.matching.get_model") as model:
            self.assertEqual(matching.encode_user_skills([]).shape, (1, 384))
            model.assert_not_called()

    def test_user_skills_are_encoded_once_with_mock_model(self):
        with patch("recommender.matching._load_store", return_value=(np.ones((2, 2)), {})), patch("recommender.matching.get_model") as model:
            model.return_value.encode.return_value = np.ones((2, 2))
            np.testing.assert_equal(matching.encode_user_skills(["Python", "SQL"]), np.ones((2, 2)))
            model.return_value.encode.assert_called_once_with(["Python", "SQL"], convert_to_numpy=True)


class ImportSafetyTests(UserDataTestCase):
    def test_existing_catalog_requires_explicit_replacement(self):
        with self.assertRaises(CommandError):
            call_command("import_data", stdout=StringIO())
        self.assertTrue(Career.objects.filter(pk=self.career.pk).exists())

    def test_invalid_files_are_rejected_before_deletion(self):
        with patch("recommender.management.commands.import_data.CAREERS_CSV", new=Path("missing.csv")):
            with self.assertRaises(CommandError):
                call_command("import_data", replace_existing=True, stdout=StringIO())
        self.assertTrue(Career.objects.filter(pk=self.career.pk).exists())

    def test_admin_catalog_edit_invalidates_recommendations(self):
        from django.contrib import admin
        from django.test import RequestFactory
        from recommender.admin import CareerAdmin
        CachedRecommendation.objects.create(user=self.user, results_json="[]")
        self.career.title = "Updated title"
        CareerAdmin(Career, admin.site).save_model(RequestFactory().post("/admin/"), self.career, None, True)
        self.assertFalse(CachedRecommendation.objects.exists())

    def test_import_failure_rolls_back_catalog_and_derived_data(self):
        with patch("recommender.management.commands.import_data.Command._import_skills", side_effect=ValueError("bad row")):
            with self.assertRaises(ValueError):
                call_command("import_data", replace_existing=True, stdout=StringIO())
        self.assertTrue(Career.objects.filter(pk=self.career.pk).exists())
