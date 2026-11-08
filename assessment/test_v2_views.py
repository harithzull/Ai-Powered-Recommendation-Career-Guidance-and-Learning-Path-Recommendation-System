from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
import importlib

from django.apps import apps
from django.db import connection
from django.test import Client, override_settings
from django.urls import reverse

from assessment.models import AssessmentSession, QuestionBank, RIASECAnswer, UserResponse
from assessment.scoring import SCORING_VERSION
from assessment.services import abandon_session, finalize_session, save_answer, start_session
from careercoach.test_utils import UserDataTestCase
from recommender.scoring import riasec_profile


class AssessmentViewTests(UserDataTestCase):
    def setUp(self):
        super().setUp()
        self.session = start_session(self.user, "quick", seed="view-test")
        self.url = reverse("assessment:session", args=[self.session.pk])

    def form(self, session=None, **changes):
        session = session or self.session
        session.refresh_from_db()
        item = session.items.get(position=0)
        values = {"position": "0", "item_id": str(item.pk), "revision": str(session.revision), "rating": "3", "action": "next"}
        values.update(changes)
        return values

    def fill(self, session):
        for item in session.items.all():
            session = save_answer(session.user, session.pk, position=item.position, item_id=item.pk, rating=3, revision=session.revision)
        return session

    def complete(self, session=None):
        session = self.fill(session or self.session)
        return finalize_session(session.user, session.pk, revision=session.revision)

    def test_start_screen_modes_limits_and_resume(self):
        response = self.client.get("/assessment/start/")
        self.assertContains(response, "Resume assessment")
        abandon_session(self.user, self.session.pk, revision=0)
        response = self.client.get("/assessment/start/")
        for text in ["18 questions", "36 questions", "4–6 minutes", "8–12 minutes", "not yet been empirically validated"]:
            self.assertContains(response, text)

    def test_start_is_post_only_and_get_has_no_creation_side_effect(self):
        count = AssessmentSession.objects.count()
        self.client.get("/assessment/start/")
        self.assertEqual(AssessmentSession.objects.count(), count)
        abandon_session(self.user, self.session.pk, revision=0)
        response = self.client.post("/assessment/start/", {"mode": "detailed"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(AssessmentSession.objects.get(user=self.user, status="in_progress").items.count(), 36)

    def test_incomplete_bank_and_invalid_mode_fail_safely(self):
        abandon_session(self.user, self.session.pk, revision=0)
        self.assertEqual(self.client.post("/assessment/start/", {"mode": "adaptive"}).status_code, 400)
        self.session.bank.items.filter(code="R01").update(status="retired")
        response = self.client.post("/assessment/start/", {"mode": "quick"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(AssessmentSession.objects.filter(user=self.user, status="in_progress").exists())

    def test_native_radio_scale_and_saved_answer_survive_refresh(self):
        response = self.client.get(self.url)
        for label in ["Strongly dislike", "Dislike", "Neutral", "Enjoy", "Strongly enjoy"]:
            self.assertContains(response, label)
        self.assertContains(response, 'type="radio"')
        self.assertContains(response, "<fieldset>")
        self.assertContains(response, "<progress")
        self.assertEqual(self.client.post(self.url, self.form(rating="4")).status_code, 302)
        response = self.client.get(self.url + "?q=1")
        self.assertEqual(response.context["selected"].rating, 4)
        self.assertEqual(response.context["answered"], 1)

    def test_previous_saves_revision_and_answer_without_erasing_other_answers(self):
        self.client.post(self.url, self.form(rating="5"))
        item = self.session.items.get(position=1)
        response = self.client.post(self.url, self.form(position="1", item_id=str(item.pk), action="previous", rating="2"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(self.session.items.order_by("position").values_list("rating", flat=True))[:2], [5, 2])
        self.assertEqual(self.client.get(self.url).context["question_number"], 1)

    def test_save_exit_and_resume_keep_cursor_and_answer(self):
        response = self.client.post(self.url, self.form(action="save"))
        self.assertRedirects(response, "/assessment/start/", fetch_redirect_response=False)
        self.assertEqual(self.client.get(self.url).context["selected"].rating, 3)

    def test_invalid_values_and_duplicate_scalar_fields_rejected(self):
        for invalid in ["0", "6", "True", "3.5", "x", "99999999999999999"]:
            with self.subTest(invalid=invalid):
                self.assertEqual(self.client.post(self.url, self.form(rating=invalid)).status_code, 400)
        values = self.form()
        values["rating"] = ["1", "5"]
        self.assertEqual(self.client.post(self.url, values).status_code, 400)
        self.assertEqual(self.session.items.filter(rating__isnull=False).count(), 0)

    def test_oversized_form_rejected(self):
        values = self.form()
        values["padding"] = "x" * (65 * 1024)
        self.assertEqual(self.client.post(self.url, values).status_code, 413)

    def test_stale_form_and_duplicate_submission_are_conflicts(self):
        form = self.form()
        self.assertEqual(self.client.post(self.url, form).status_code, 302)
        self.assertEqual(self.client.post(self.url, form).status_code, 409)

    def test_session_ownership_and_selected_question_authorization(self):
        other = start_session(self.other, "quick")
        other_url = reverse("assessment:session", args=[other.pk])
        self.assertEqual(self.client.get(other_url).status_code, 404)
        self.assertEqual(self.client.post(other_url, self.form(other)).status_code, 404)
        self.assertEqual(self.client.post(self.url, self.form(item_id=str(other.items.first().pk))).status_code, 404)

    def test_private_routes_require_authentication(self):
        self.client.logout()
        for name in ["session", "review", "result"]:
            self.assertEqual(self.client.get(reverse("assessment:" + name, args=[self.session.pk])).status_code, 302)
        for url in ["/assessment/start/", "/assessment/history/"]:
            self.assertEqual(self.client.get(url).status_code, 302)

    def test_csrf_enforcement_and_valid_form_flow(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        for url in ["/assessment/start/", "/assessment/retake/", self.url,
                    reverse("assessment:review", args=[self.session.pk]), reverse("assessment:abandon", args=[self.session.pk])]:
            self.assertEqual(client.post(url, self.form()).status_code, 403)
        client.get(self.url)
        token = client.cookies["csrftoken"].value
        self.assertEqual(client.post(self.url, self.form(), HTTP_X_CSRFTOKEN=token).status_code, 302)

    def test_review_rejects_missing_answers_and_does_not_finalize_on_get(self):
        url = reverse("assessment:review", args=[self.session.pk])
        self.assertEqual(self.client.get(url).context["missing"], 18)
        self.assertEqual(self.client.post(url, {"revision": "0"}).status_code, 400)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "in_progress")

    def test_finalize_and_results_use_actual_scores_and_code(self):
        session = self.fill(self.session)
        url = reverse("assessment:review", args=[session.pk])
        response = self.client.post(url, {"revision": session.revision})
        result_url = reverse("assessment:result", args=[session.pk])
        self.assertRedirects(response, result_url, fetch_redirect_response=False)
        response = self.client.get(result_url)
        self.assertContains(response, "RIA")
        self.assertContains(response, "50.0 out of 100")
        self.assertEqual(len(response.context["rows"]), 6)
        self.assertContains(response, "<meter", count=6)
        self.assertContains(response, "Some dimensions are tied or close")
        self.assertContains(response, "R, I, A, S, E, C")

    def test_complete_question_form_flow_without_javascript(self):
        for _ in range(18):
            page = self.client.get(self.url)
            selected, session = page.context["selected"], page.context["session"]
            response = self.client.post(self.url, {"position": selected.position, "item_id": selected.pk,
                "revision": session.revision, "rating": 4, "action": "next"})
            self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("assessment:review", args=[self.session.pk]))
        review = self.client.get(response.url)
        self.assertEqual(review.context["missing"], 0)
        response = self.client.post(response.url, {"revision": review.context["session"].revision})
        result = self.client.get(response.url)
        self.assertEqual(result.status_code, 200)
        self.assertEqual([row["score"] for row in result.context["rows"]], [75] * 6)

    def test_completed_posts_cannot_modify_answers_or_result(self):
        session = self.complete()
        before = deepcopy(session.result)
        self.assertEqual(self.client.post(self.url, self.form(rating="5")).status_code, 409)
        url = reverse("assessment:review", args=[session.pk])
        self.assertEqual(self.client.post(url, {"revision": session.revision}).status_code, 409)
        session.refresh_from_db()
        self.assertEqual(before, session.result)

    def test_other_user_cannot_finalize_abandon_or_view_result_or_history_comparison(self):
        other = self.complete(start_session(self.other, "quick"))
        for route in ["review", "abandon"]:
            url = reverse("assessment:" + route, args=[other.pk])
            self.assertEqual(self.client.post(url, {"revision": other.revision}).status_code, 404)
        self.assertEqual(self.client.get(reverse("assessment:result", args=[other.pk])).status_code, 404)
        self.assertEqual(self.client.get("/assessment/history/", {"first": other.pk, "second": other.pk}).status_code, 404)

    def test_resume_from_another_client_uses_database_state(self):
        self.client.post(self.url, self.form(rating="4"))
        client = Client()
        client.force_login(self.user)
        response = client.get(self.url + "?q=1")
        self.assertEqual(response.context["selected"].rating, 4)

    def test_history_comparison_only_for_matching_forms(self):
        first = self.complete()
        second = self.complete(start_session(self.user, "quick"))
        response = self.client.get("/assessment/history/", {"first": first.pk, "second": second.pk})
        self.assertContains(response, "Same-form comparison")
        third = self.complete(start_session(self.user, "detailed"))
        response = self.client.get("/assessment/history/", {"first": first.pk, "second": third.pk})
        self.assertContains(response, "should not be presented as a direct trend")
        self.assertIsNone(response.context["comparison"])

    def test_invalid_comparison_ids_and_question_positions_fail_safely(self):
        self.assertEqual(self.client.get("/assessment/history/?first=bad&second=bad").status_code, 400)
        self.assertEqual(self.client.get(self.url + "?q=bad").status_code, 400)
        self.assertEqual(self.client.get(self.url + "?q=100").status_code, 404)

    @override_settings(ASSESSMENT_REQUESTS_PER_MINUTE=1)
    def test_answer_rate_limit(self):
        self.client.post(self.url, self.form())
        self.assertEqual(self.client.post(self.url, self.form()).status_code, 429)

    @patch("recommender.recommendations.encode_user_skills", return_value=[[1, 0]])
    @patch("recommender.recommendations.semantic_skill_match_from_vectors", return_value=(0.7, []))
    def test_existing_recommendation_pipeline_keeps_weights_and_scale(self, match, encode):
        from recommender.recommendations import get_recommendations
        self.complete()
        results = get_recommendations(self.user)
        expected = round((0.6 * 0.45 + 0.7 * 0.40 + 0.91 * 0.15) * 100, 1)
        self.assertEqual(results[0]["final_score"], expected)
        self.assertEqual(results[0]["interest_pct"], 60)

    def test_new_user_can_review_skills_without_legacy_interest_answers(self):
        self.complete()
        RIASECAnswer.objects.filter(response__user=self.user).delete()  # Test fixture only.
        self.assertEqual(self.client.get("/assessment/skills/").status_code, 200)


class LegacyArchiveTests(UserDataTestCase):
    def test_migration_archives_legacy_mean_over_five_without_changing_original_rows(self):
        migration = importlib.import_module("assessment.migrations.0007_seed_bank_and_archive_legacy")
        before = list(RIASECAnswer.objects.values_list("pk", "rating"))
        original_time = UserResponse.objects.get(user=self.user).completed_at
        migration.seed_and_archive(apps, SimpleNamespace(connection=connection))
        legacy = AssessmentSession.objects.get(user=self.user, mode="legacy")
        self.assertEqual(legacy.scoring_version, "legacy-mean-div5-v1")
        self.assertEqual(legacy.result["scores"], dict.fromkeys("RIASEC", 80))
        self.assertEqual(legacy.result["holland_code"], "")
        self.assertIsNone(legacy.bank)
        self.assertEqual(before, list(RIASECAnswer.objects.values_list("pk", "rating")))
        self.assertEqual(UserResponse.objects.get(user=self.user).completed_at, original_time)
        self.assertEqual(riasec_profile(UserResponse.objects.get(user=self.user)), dict.fromkeys("RIASEC", 0.8))
        migration.seed_and_archive(apps, SimpleNamespace(connection=connection))
        self.assertEqual(AssessmentSession.objects.filter(mode="legacy").count(), 2)
        response = self.client.get(reverse("assessment:result", args=[legacy.pk]))
        self.assertContains(response, "A Holland Code was not recorded")
        self.assertContains(response, "80.0 out of 100")
        self.assertEqual(len(response.context["rows"]), 6)
