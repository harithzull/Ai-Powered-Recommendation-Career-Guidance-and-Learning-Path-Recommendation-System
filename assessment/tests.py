import json
from unittest.mock import patch

from django.test import Client, override_settings

from accounts.models import UserProfile
from assessment.adaptive import select_next
from assessment.models import RIASECAnswer, RIASECQuestion, SkillRating, UserResponse
from careercoach.test_utils import UserDataTestCase
from recommender.models import CachedRecommendation
from roadmap.models import RoadmapProgress, SavedRoadmap


class AssessmentTests(UserDataTestCase):
    def test_background_required_fields_and_choice_validation(self):
        for data in [{}, {"field_of_study": "bad", "experience_level": "bad"}]:
            with self.subTest(data=data):
                self.assertEqual(self.client.post("/assessment/background/", data).status_code, 200)
        self.assertEqual(UserProfile.objects.get(user=self.user).field_of_study, "Computing/IT")

    def test_background_update_invalidates_only_current_users_cache(self):
        for user in [self.user, self.other]:
            CachedRecommendation.objects.create(user=user, results_json="[]")
        response = self.client.post("/assessment/background/", {"field_of_study": "Business", "experience_level": "Internship"})
        self.assertRedirects(response, "/assessment/interests/", fetch_redirect_response=False)
        self.assertFalse(CachedRecommendation.objects.filter(user=self.user).exists())
        self.assertTrue(CachedRecommendation.objects.filter(user=self.other).exists())

    def test_interest_submission_resets_completion_skills_and_derived_data(self):
        CachedRecommendation.objects.create(user=self.user, results_json="[]")
        SavedRoadmap.objects.create(user=self.user, career=self.career, title="Old", steps_json="[]")
        response = self.client.post("/assessment/interests/", {"answers_json": json.dumps(self.answers())})
        self.assertRedirects(response, "/assessment/skills/", fetch_redirect_response=False)
        stored = UserResponse.objects.get(user=self.user)
        self.assertIsNone(stored.completed_at)
        self.assertEqual(stored.riasec_answers.count(), 6)
        self.assertFalse(stored.skill_ratings.exists())
        self.assertFalse(CachedRecommendation.objects.filter(user=self.user).exists())
        self.assertFalse(SavedRoadmap.objects.filter(user=self.user).exists())
        self.assertIsNotNone(UserResponse.objects.get(user=self.other).completed_at)

    def test_bad_interest_submissions_leave_answers_unchanged(self):
        invalid = [None, {}, [], [self.answers()[0]] * 6, self.answers()[:5],
                   self.answers() + [{"id": 999999, "rating": 3}],
                   [{"id": a["id"], "rating": True} for a in self.answers()],
                   [{"id": a["id"], "rating": 6} for a in self.answers()]]
        for payload in invalid:
            with self.subTest(payload=payload):
                response = self.client.post("/assessment/interests/", {"answers_json": json.dumps(payload)})
                self.assertRedirects(response, "/assessment/interests/", fetch_redirect_response=False)
        self.assertEqual(RIASECAnswer.objects.filter(response__user=self.user).count(), 6)
        self.assertIsNotNone(UserResponse.objects.get(user=self.user).completed_at)

    def test_missing_riasec_coverage_is_rejected(self):
        questions = RIASECQuestion.objects.filter(riasec_type="R")[:6]
        self.client.post("/assessment/interests/", {"answers_json": json.dumps([
            {"id": q.pk, "rating": 4} for q in questions])})
        self.assertEqual(set(RIASECAnswer.objects.filter(response__user=self.user)
                             .values_list("question__riasec_type", flat=True)), set("RIASEC"))

    def test_skills_submission_accepts_custom_skills_and_completes(self):
        response = self.client.post("/assessment/skills/", {"rated_skills_json": json.dumps({"Python": 5, "Writing": 2})})
        self.assertRedirects(response, "/dashboard/", fetch_redirect_response=False)
        stored = UserResponse.objects.get(user=self.user)
        self.assertIsNotNone(stored.completed_at)
        self.assertEqual(dict(stored.skill_ratings.values_list("skill_name", "rating")), {"Python": 5, "Writing": 2})
        self.assertEqual(SkillRating.objects.get(response__user=self.other).skill_name, "Programming")

    def test_empty_skills_are_supported(self):
        self.client.post("/assessment/skills/", {"rated_skills_json": "{}"})
        self.assertIsNotNone(UserResponse.objects.get(user=self.user).completed_at)
        self.assertFalse(SkillRating.objects.filter(response__user=self.user).exists())

    def test_invalid_skills_do_not_destroy_previous_ratings(self):
        invalid = [[], None, 2, {"Python": True}, {"Python": 1.5}, {"Python": "3"}, {"Python": 6},
                   {"": 3}, {"x" * 101: 3}, {str(i): 3 for i in range(31)}, {"Python": 3, " Python ": 4}]
        for payload in invalid:
            with self.subTest(payload=payload):
                response = self.client.post("/assessment/skills/", {"rated_skills_json": json.dumps(payload)})
                self.assertRedirects(response, "/assessment/skills/", fetch_redirect_response=False)
                self.assertEqual(SkillRating.objects.get(response__user=self.user).skill_name, "Programming")

    def test_stored_skill_cannot_escape_json_script(self):
        attack = '</script><script>alert("xss")</script>'
        self.client.post("/assessment/skills/", {"rated_skills_json": json.dumps({attack: 3})})
        response = self.client.get("/assessment/skills/")
        self.assertNotContains(response, attack)
        self.assertContains(response, r"\u003C/script\u003E")

    def test_retake_get_is_safe_and_post_is_user_scoped(self):
        for user in [self.user, self.other]:
            CachedRecommendation.objects.create(user=user, results_json="[]")
            SavedRoadmap.objects.create(user=user, career=self.career, title="Plan", steps_json="[]")
            RoadmapProgress.objects.create(user=user, career=self.career, step_index=0)
        session = self.client.session
        session["chatbot_history"] = [{"role": "user", "content": "old"}]
        session.save()
        for path in ["/assessment/background/?retake=1", "/assessment/interests/?retake=1"]:
            self.assertEqual(self.client.get(path).status_code, 200)
            self.assertTrue(UserResponse.objects.filter(user=self.user).exists())
        self.assertEqual(self.client.get("/assessment/retake/").status_code, 405)
        self.assertEqual(self.client.post("/assessment/retake/", {"user_id": self.other.pk}).status_code, 302)
        for model in [UserResponse, CachedRecommendation, SavedRoadmap, RoadmapProgress]:
            self.assertFalse(model.objects.filter(user=self.user).exists())
            self.assertTrue(model.objects.filter(user=self.other).exists())
        self.assertNotIn("chatbot_history", self.client.session)

    def test_partial_assessment_cannot_access_results_or_roadmap(self):
        UserResponse.objects.filter(user=self.user).update(completed_at=None)
        for path in ["/recommendations/", f"/roadmap/{self.career.pk}/"]:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 302)

    def test_background_is_required_before_interests(self):
        UserProfile.objects.filter(user=self.user).update(field_of_study="")
        self.assertRedirects(self.client.get("/assessment/interests/"), "/assessment/background/", fetch_redirect_response=False)

    def test_skills_requires_interest_answers(self):
        RIASECAnswer.objects.filter(response__user=self.user).delete()
        self.assertRedirects(self.client.get("/assessment/skills/"), "/assessment/interests/", fetch_redirect_response=False)

    def test_next_question_rejects_malformed_shapes_and_values(self):
        payloads = [None, [], 2, {"history": None}, {"history": [None]},
                    {"history": [{"id": True, "rating": 3}]},
                    {"history": [{"id": 999999, "rating": 3}]},
                    {"history": [self.answers()[0], self.answers()[0]]}]
        for payload in payloads:
            with self.subTest(payload=payload):
                response = self.client.post("/assessment/interests/next/", json.dumps(payload), content_type="application/json")
                self.assertEqual(response.status_code, 400)

    def test_next_question_success_and_method(self):
        self.assertEqual(self.client.get("/assessment/interests/next/").status_code, 405)
        response = self.client.post("/assessment/interests/next/", "{}", content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["done"])
        self.assertIn("text", response.json()["question"])

    def test_invalid_json_and_encoding(self):
        for payload in [b"{", b"\xff", b"[" * 2000 + b"]" * 2000]:
            self.assertEqual(self.client.post("/assessment/interests/next/", payload, content_type="application/json").status_code, 400)

    def test_large_request_is_rejected_without_modifying_data(self):
        response = self.client.post("/assessment/interests/next/", b"x" * (65 * 1024), content_type="application/json")
        self.assertEqual(response.status_code, 413)
        self.assertEqual(RIASECAnswer.objects.filter(response__user=self.user).count(), 6)

    def test_skill_search_and_bounds(self):
        from recommender.models import Skill
        Skill.objects.create(name="Python")
        self.assertEqual(self.client.get("/assessment/skill-search/?q=py").json(), {"results": ["Python"]})
        self.assertEqual(self.client.get("/assessment/skill-search/?q=p").json(), {"results": []})
        self.assertEqual(self.client.get("/assessment/skill-search/", {"q": "x" * 101}).status_code, 400)

    def test_csrf_rejected_and_valid_retake_succeeds(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        for path in ["/assessment/background/", "/assessment/interests/", "/assessment/skills/",
                     "/assessment/interests/next/", "/assessment/retake/", "/accounts/profile/"]:
            with self.subTest(path=path):
                self.assertEqual(client.post(path, {}).status_code, 403)
        self.assertTrue(UserResponse.objects.filter(user=self.user).exists())
        client.get("/assessment/background/")
        response = client.post("/assessment/retake/", {}, HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(UserResponse.objects.filter(user=self.user).exists())


class AdaptiveTests(UserDataTestCase):
    def test_low_ratings_cover_all_types_and_end_early(self):
        history = []
        for _ in range(12):
            result = select_next(history)
            if result.done:
                break
            history.append((result.question.pk, 1))
        self.assertTrue(select_next(history).done)
        self.assertEqual(len(history), 6)
        types = set(RIASECQuestion.objects.filter(pk__in=[qid for qid, _ in history]).values_list("riasec_type", flat=True))
        self.assertEqual(types, set("RIASEC"))

    def test_high_ratings_deepen_without_duplicates_or_missing_types(self):
        history = []
        for _ in range(12):
            result = select_next(history)
            self.assertFalse(result.done)
            history.append((result.question.pk, 5))
        self.assertTrue(select_next(history).done)
        self.assertEqual(len(set(qid for qid, _ in history)), 12)
        for t in "RIASEC":
            self.assertEqual(RIASECQuestion.objects.filter(pk__in=[qid for qid, _ in history], riasec_type=t).count(), 2)
