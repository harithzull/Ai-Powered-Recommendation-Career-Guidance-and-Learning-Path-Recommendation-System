from collections import Counter
from copy import deepcopy
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import Client, SimpleTestCase, override_settings
from django.urls import reverse

from careercoach.test_utils import UserDataTestCase
from assessment.bank_v1 import BANK_VERSION, ITEMS
from assessment.models import AssessmentSession, InterestItem, QuestionBank, SessionItem, UserResponse, RIASECAnswer, SkillRating
from assessment.scoring import AssessmentError, SCORING_VERSION, score_answers
from assessment.services import (SessionConflict, abandon_session, comparable, finalize_session,
                                  save_answer, select_items, start_session, validate_bank)
from recommender.models import CachedRecommendation
from recommender.scoring import riasec_profile
from roadmap.models import SavedRoadmap, RoadmapProgress


def answers(mode="quick", ratings=None):
    ratings = ratings or dict.fromkeys("RIASEC", 3)
    return [{"id": f"{t}{i}", "dimension": t, "rating": ratings[t]}
            for t in "RIASEC" for i in range(3 if mode == "quick" else 6)]


class ScoreTests(SimpleTestCase):
    def score(self, values, mode="quick"):
        return score_answers(values, mode=mode, bank_version=BANK_VERSION)

    def test_scale_endpoints_and_neutral(self):
        for rating, points, compatibility in [(1, 0, 0.2), (3, 50, 0.6), (5, 100, 1)]:
            with self.subTest(rating=rating):
                result = self.score(answers(ratings=dict.fromkeys("RIASEC", rating)))
                self.assertEqual(result["scores"], dict.fromkeys("RIASEC", points))
                self.assertEqual(result["raw_averages"], dict.fromkeys("RIASEC", rating))
                self.assertEqual(result["compatibility_profile"], dict.fromkeys("RIASEC", compatibility))

    def test_raw_averages_counts_totals_and_holland_code(self):
        result = self.score(answers(ratings={"R": 1, "I": 5, "A": 4, "S": 3, "E": 2, "C": 1}))
        self.assertEqual(result["holland_code"], "IAS")
        self.assertEqual(result["raw_totals"]["I"], 15)
        self.assertEqual(result["counts"], dict.fromkeys("RIASEC", 3))
        self.assertEqual(result["scores"]["A"], 75)

    def test_deterministic_ties_do_not_disappear(self):
        result = self.score(answers())
        self.assertEqual(result["holland_code"], "RIA")
        self.assertEqual(result["ties"], [list("RIASEC")])

    def test_near_tie_threshold_is_descriptive(self):
        values = answers("detailed", dict.fromkeys("RIASEC", 3))
        values[0]["rating"] = 4
        result = self.score(values, "detailed")
        self.assertIn(["R", "I"], result["near_ties"])
        self.assertEqual(result["near_tie_points"], 5)

    def test_missing_answer_or_dimension_is_rejected(self):
        for values in [answers()[:-1], [], [a for a in answers() if a["dimension"] != "R"]]:
            with self.subTest(length=len(values)), self.assertRaises(AssessmentError):
                self.score(values)

    def test_invalid_ratings_are_rejected(self):
        for rating in [None, True, False, "3", 1.5, 0, 6, [], {}]:
            values = answers()
            values[0]["rating"] = rating
            with self.subTest(rating=rating), self.assertRaises(AssessmentError):
                self.score(values)

    def test_duplicate_or_invalid_item_ids_and_dimensions_rejected(self):
        for field, value in [("id", "R1"), ("id", None), ("dimension", None), ("dimension", "RI"), ("dimension", "X")]:
            values = answers()
            values[0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(AssessmentError):
                self.score(values)

    def test_response_order_does_not_change_result(self):
        values = answers(ratings={"R": 1, "I": 5, "A": 4, "S": 3, "E": 2, "C": 1})
        self.assertEqual(self.score(values), self.score(list(reversed(values))))

    def test_detailed_counts_and_fractional_means(self):
        values = answers("detailed")
        values[0]["rating"] = 4
        result = self.score(values, "detailed")
        self.assertEqual(result["counts"]["R"], 6)
        self.assertAlmostEqual(result["raw_averages"]["R"], 19 / 6, places=5)
        self.assertEqual(result["scores"]["R"], 54.17)
        self.assertEqual(result["compatibility_profile"]["R"], 0.6333)

    def test_unknown_mode_or_bank_rejected(self):
        for mode, bank in [("adaptive", BANK_VERSION), ("quick", "")]:
            with self.assertRaises(AssessmentError):
                score_answers(answers(), mode=mode, bank_version=bank)


class SessionTests(UserDataTestCase):
    def setUp(self):
        super().setUp()
        self.bank = QuestionBank.objects.get(version=BANK_VERSION)

    def session(self, mode="quick", user=None):
        return start_session(user or self.user, mode, seed="fixed-seed")

    def fill(self, session, rating=3):
        for item in session.items.all():
            session = save_answer(session.user, session.pk, position=item.position, item_id=item.pk,
                                  rating=rating, revision=session.revision)
        return session

    def complete(self, mode="quick", rating=3, user=None):
        session = self.fill(self.session(mode, user=user), rating)
        return finalize_session(session.user, session.pk, revision=session.revision)

    def test_seeded_bank_has_36_active_items_and_six_facets_each(self):
        selected = validate_bank(self.bank)
        self.assertEqual(len(selected), 36)
        self.assertEqual(Counter(i.dimension for i in selected), dict.fromkeys("RIASEC", 6))
        self.assertEqual(Counter(i.dimension for i in selected if i.quick_core), dict.fromkeys("RIASEC", 3))
        self.assertEqual(len(ITEMS), 36)
        self.assertTrue(all(i.purpose and i.facet for i in selected))

    def test_quick_selection_is_balanced_unique_interleaved_and_frozen(self):
        session = self.session()
        rows = list(session.items.all())
        self.assertEqual(len(rows), 18)
        self.assertEqual(Counter(row.dimension for row in rows), dict.fromkeys("RIASEC", 3))
        self.assertEqual(len({row.item_id for row in rows}), 18)
        self.assertEqual(session.bank.version, BANK_VERSION)
        self.assertEqual(session.scoring_version, SCORING_VERSION)
        self.assertTrue(all(a.dimension != b.dimension for a, b in zip(rows, rows[1:])))
        self.assertEqual([r.code for r in rows], [i.code for i in select_items(self.bank, "quick", "fixed-seed")])

    def test_detailed_has_36_balanced_items(self):
        session = self.session("detailed")
        self.assertEqual(Counter(session.items.values_list("dimension", flat=True)), dict.fromkeys("RIASEC", 6))
        self.assertEqual(session.items.count(), 36)

    def test_answer_values_do_not_affect_selected_questions(self):
        session = self.session()
        before = list(session.items.values_list("code", flat=True))
        self.fill(session, 1)
        self.assertEqual(before, list(session.items.values_list("code", flat=True)))

    def test_retired_item_excluded_and_incomplete_bank_creates_no_session(self):
        item = self.bank.items.first()
        item.status = "retired"
        item.save()
        with self.assertRaises(AssessmentError):
            self.session()
        self.assertFalse(AssessmentSession.objects.filter(user=self.user).exists())

    def test_existing_session_does_not_change_after_bank_retirement_or_item_edit(self):
        session = self.session()
        row = session.items.first()
        original = row.text
        InterestItem.objects.filter(pk=row.item_id).update(text="Changed outside the supported editing workflow", status="retired")
        QuestionBank.objects.filter(pk=self.bank.pk).update(status="retired")
        row.refresh_from_db()
        self.assertEqual(row.text, original)
        session = self.fill(session)
        self.assertEqual(finalize_session(self.user, session.pk, revision=session.revision).status, "completed")

    def test_model_guards_published_items_and_bank_version(self):
        item = self.bank.items.first()
        item.text = "Changed item"
        with self.assertRaises(ValidationError):
            item.save()
        self.bank.version = "renamed"
        with self.assertRaises(ValidationError):
            self.bank.save()

    def test_draft_items_excluded_and_quick_core_shortage_fails(self):
        item = self.bank.items.first()
        InterestItem.objects.filter(pk=item.pk).update(quick_core=False)
        with self.assertRaises(AssessmentError):
            self.session()

    def test_one_open_session_per_user_and_other_user_independence(self):
        first = self.session()
        with self.assertRaises(SessionConflict):
            self.session("detailed")
        second = self.session(user=self.other)
        self.assertNotEqual(first.pk, second.pk)

    def test_save_update_and_resume_progress(self):
        session = self.session()
        item = session.items.first()
        session = save_answer(self.user, session.pk, position=0, item_id=item.pk, rating=2, revision=0)
        self.assertEqual(session.current_position, 1)
        session = save_answer(self.user, session.pk, position=0, item_id=item.pk, rating=5, revision=1)
        item.refresh_from_db()
        self.assertEqual(item.rating, 5)
        self.assertIsNotNone(item.answered_at)
        self.assertEqual(session.items.filter(rating__isnull=False).count(), 1)

    def test_stale_revision_rejects_duplicate_post(self):
        session = self.session()
        item = session.items.first()
        save_answer(self.user, session.pk, position=0, item_id=item.pk, rating=4, revision=0)
        with self.assertRaises(SessionConflict):
            save_answer(self.user, session.pk, position=0, item_id=item.pk, rating=1, revision=0)
        item.refresh_from_db()
        self.assertEqual(item.rating, 4)

    def test_invalid_or_missing_rating_does_not_advance(self):
        session = self.session()
        item = session.items.first()
        for value in [None, True, "3", 0, 6, 1.5]:
            with self.subTest(value=value), self.assertRaises(AssessmentError):
                save_answer(self.user, session.pk, position=0, item_id=item.pk, rating=value, revision=0)
        session.refresh_from_db()
        self.assertEqual(session.revision, 0)

    def test_incomplete_finalization_is_rejected_without_touching_active_result(self):
        session = self.session()
        response = UserResponse.objects.get(user=self.user)
        with self.assertRaises(AssessmentError):
            finalize_session(self.user, session.pk, revision=0)
        response.refresh_from_db()
        self.assertIsNone(response.active_session_id)
        session.refresh_from_db()
        self.assertEqual(session.status, "in_progress")

    def test_finalization_preserves_legacy_answers_skills_and_roadmaps(self):
        SavedRoadmap.objects.create(user=self.user, career=self.career, title="Keep", steps_json="[]")
        RoadmapProgress.objects.create(user=self.user, career=self.career, step_index=0)
        CachedRecommendation.objects.create(user=self.user, results_json="[]")
        CachedRecommendation.objects.create(user=self.other, results_json="[]")
        before = list(RIASECAnswer.objects.filter(response__user=self.user).values_list("pk", "rating"))
        skills = list(SkillRating.objects.filter(response__user=self.user).values_list("pk", "skill_name", "rating"))
        original_time = UserResponse.objects.get(user=self.user).completed_at
        session = self.complete()
        self.assertEqual(session.status, "completed")
        self.assertEqual(session.result["scores"]["R"], 50)
        response = UserResponse.objects.get(user=self.user)
        self.assertEqual(response.active_session_id, session.pk)
        self.assertEqual(response.completed_at, original_time)
        self.assertEqual(before, list(RIASECAnswer.objects.filter(response__user=self.user).values_list("pk", "rating")))
        self.assertEqual(skills, list(SkillRating.objects.filter(response__user=self.user).values_list("pk", "skill_name", "rating")))
        self.assertTrue(SavedRoadmap.objects.filter(user=self.user).exists())
        self.assertTrue(RoadmapProgress.objects.filter(user=self.user).exists())
        self.assertFalse(CachedRecommendation.objects.filter(user=self.user).exists())
        self.assertTrue(CachedRecommendation.objects.filter(user=self.other).exists())

    def test_adapter_uses_mean_over_five_and_leaves_legacy_unchanged(self):
        self.assertEqual(riasec_profile(UserResponse.objects.get(user=self.user)), dict.fromkeys("RIASEC", 0.8))
        self.complete(rating=3)
        self.assertEqual(riasec_profile(UserResponse.objects.get(user=self.user)), dict.fromkeys("RIASEC", 0.6))
        self.assertEqual(riasec_profile(UserResponse.objects.get(user=self.other)), dict.fromkeys("RIASEC", 0.8))

    def test_completed_session_and_items_are_immutable(self):
        session = self.complete()
        item = session.items.first()
        with self.assertRaises(SessionConflict):
            save_answer(self.user, session.pk, position=0, item_id=item.pk, rating=5, revision=session.revision)
        with self.assertRaises(SessionConflict):
            finalize_session(self.user, session.pk, revision=session.revision)
        item.rating = 5
        with self.assertRaises(ValidationError):
            item.save()
        session.result = {}
        with self.assertRaises(ValidationError):
            session.save()

    def test_retake_creates_new_session_and_keeps_old_result_active(self):
        first = self.complete()
        frozen = deepcopy(first.result)
        second = self.session("detailed")
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(UserResponse.objects.get(user=self.user).active_session_id, first.pk)
        first.refresh_from_db()
        self.assertEqual(first.result, frozen)

    def test_abandon_and_restart_preserve_saved_answers_and_previous_result(self):
        first = self.complete()
        second = self.session()
        second = self.fill(second)
        abandon_session(self.user, second.pk, revision=second.revision)
        third = self.session()
        self.assertEqual(second.items.filter(rating__isnull=False).count(), 18)
        self.assertNotEqual(third.pk, second.pk)
        self.assertEqual(UserResponse.objects.get(user=self.user).active_session_id, first.pk)

    def test_first_assessment_for_new_user_creates_compatibility_response(self):
        user = User.objects.create_user("new")
        session = self.complete(user=user)
        response = UserResponse.objects.get(user=user)
        self.assertEqual(response.active_session_id, session.pk)
        self.assertIsNotNone(response.completed_at)
        self.assertFalse(response.riasec_answers.exists())

    def test_reproducibility_and_comparable_forms(self):
        first = self.complete()
        second = self.complete()
        self.assertTrue(comparable(first, second))
        self.assertEqual(first.result, second.result)
        third = self.complete("detailed")
        self.assertFalse(comparable(first, third))

    def test_database_rating_constraint_and_selected_item_uniqueness(self):
        session = self.session()
        item = session.items.first()
        with self.assertRaises(IntegrityError), transaction.atomic():
            SessionItem.objects.filter(pk=item.pk).update(rating=6)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SessionItem.objects.create(session=session, item=item.item, position=99, code=item.code, dimension=item.dimension, text=item.text, facet=item.facet)

    def test_check_bank_command(self):
        out = StringIO()
        call_command("check_assessment_bank", stdout=out)
        self.assertIn("Quick=18, Detailed=36", out.getvalue())

    def test_clone_creates_editable_draft_without_changing_published_questions(self):
        original = self.bank.items.first()
        call_command("clone_question_bank", self.bank.version, "editable-test-version", stdout=StringIO())
        cloned_bank = QuestionBank.objects.get(version="editable-test-version")
        self.assertEqual(cloned_bank.status, "draft")
        self.assertEqual(cloned_bank.items.count(), 36)
        edited = cloned_bank.items.get(code=original.code)
        edited.text = "A revised activity requiring content review."
        edited.save()
        original.refresh_from_db()
        self.assertNotEqual(original.text, edited.text)
        with self.assertRaises(CommandError):
            call_command("clone_question_bank", self.bank.version, "editable-test-version", stdout=StringIO())

    def test_publish_new_bank_does_not_change_existing_session(self):
        session = self.session()
        draft = QuestionBank.objects.create(version="test-revised-bank")
        for item in self.bank.items.all():
            InterestItem.objects.create(bank=draft, code=item.code, dimension=item.dimension, facet=item.facet,
                purpose=item.purpose, text=item.text + " Imagine learning first.", quick_core=item.quick_core, status="active")
        InterestItem.objects.create(bank=draft, code="R99", dimension="R", facet="Retired candidate",
            purpose="Candidate only", text="A retired activity.", status="retired")
        call_command("publish_question_bank", draft.version, stdout=StringIO())
        session.refresh_from_db()
        self.assertEqual(session.bank_id, self.bank.pk)
        selected = select_items(draft, "detailed", "seed")
        self.assertEqual(len(selected), 36)
        self.assertNotIn("R99", [item.code for item in selected])
        self.bank.refresh_from_db()
        self.assertEqual(self.bank.status, "retired")

    def test_incomplete_publication_rolls_back_current_active_bank(self):
        draft = QuestionBank.objects.create(version="test-incomplete-bank")
        with self.assertRaises(CommandError):
            call_command("publish_question_bank", draft.version, stdout=StringIO())
        self.bank.refresh_from_db()
        self.assertEqual(self.bank.status, "active")

    def test_adapter_rejects_corrupt_cross_user_pointer(self):
        session = self.complete(user=self.other)
        response = UserResponse.objects.get(user=self.user)
        response.active_session = session
        response.save(update_fields=["active_session"])
        with self.assertRaises(ValueError):
            riasec_profile(UserResponse.objects.get(user=self.user))
