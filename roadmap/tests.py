import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import Client, override_settings

from careercoach.test_utils import UserDataTestCase
from roadmap.generator import RoadmapStep, _steps_to_json, generate_roadmap, get_or_create_roadmap
from roadmap.models import RoadmapProgress, SavedRoadmap


class RoadmapTests(UserDataTestCase):
    def setUp(self):
        super().setUp()
        self.url = f"/roadmap/{self.career.pk}/"

    def save_plan(self, user=None):
        return SavedRoadmap.objects.create(user=user or self.user, career=self.career, title="Private plan",
            steps_json=_steps_to_json([RoadmapStep(index=0, label="Learn", title="Learn Python"),
                                       RoadmapStep(index=1, label="Build", title="Build a project")]))

    @patch("roadmap.views.get_or_create_roadmap")
    def test_get_never_calls_groq_or_creates_a_roadmap(self, generate):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="action" value="generate"')
        generate.assert_not_called()
        self.assertFalse(SavedRoadmap.objects.exists())

    @patch("roadmap.generator.semantic_skill_match", return_value=(0.3, ["SQL"]))
    def test_post_creates_own_fallback_plan_without_api_key(self, match):
        response = self.client.post(self.url, {"action": "generate", "user": self.other.pk})
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        saved = SavedRoadmap.objects.get(user=self.user)
        self.assertIn("SQL", saved.steps_json)
        self.assertFalse(SavedRoadmap.objects.filter(user=self.other).exists())

    @patch("roadmap.views.get_or_create_roadmap")
    def test_saved_plan_reused_for_get_and_generate_post(self, generate):
        self.save_plan()
        self.assertContains(self.client.get(self.url), "Learn Python")
        self.assertEqual(self.client.post(self.url, {"action": "generate"}).status_code, 302)
        generate.assert_not_called()

    def test_progress_updates_only_current_user(self):
        self.save_plan()
        self.save_plan(self.other)
        RoadmapProgress.objects.create(user=self.other, career=self.career, step_index=1)
        response = self.client.post(self.url, {"step_0": "on", "user_id": self.other.pk})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(list(RoadmapProgress.objects.filter(user=self.user).values_list("step_index", flat=True)), [0])
        self.assertEqual(list(RoadmapProgress.objects.filter(user=self.other).values_list("step_index", flat=True)), [1])
        self.assertContains(self.client.get(self.url), "50%")

    def test_unchecking_all_progress_is_supported(self):
        self.save_plan()
        RoadmapProgress.objects.create(user=self.user, career=self.career, step_index=0)
        self.client.post(self.url, {})
        self.assertFalse(RoadmapProgress.objects.filter(user=self.user).exists())

    def test_invalid_step_cannot_replace_previous_progress(self):
        self.save_plan()
        RoadmapProgress.objects.create(user=self.user, career=self.career, step_index=0)
        for key in ["step_999", "step_-1", "step_bad"]:
            with self.subTest(key=key):
                self.assertEqual(self.client.post(self.url, {key: "on"}).status_code, 400)
        self.assertEqual(RoadmapProgress.objects.get(user=self.user).step_index, 0)

    def test_progress_replacement_is_atomic(self):
        self.save_plan()
        RoadmapProgress.objects.create(user=self.user, career=self.career, step_index=0)
        with patch("roadmap.views.RoadmapProgress.objects.bulk_create", side_effect=RuntimeError("test")):
            with self.assertRaises(RuntimeError):
                self.client.post(self.url, {"step_1": "on"})
        self.assertEqual(RoadmapProgress.objects.get(user=self.user).step_index, 0)

    def test_other_users_plan_is_not_rendered(self):
        self.save_plan(self.other)
        response = self.client.get(self.url)
        self.assertNotContains(response, "Private plan")
        self.assertNotContains(response, "Learn Python")

    def test_unknown_career_returns_404(self):
        self.assertEqual(self.client.get("/roadmap/999999/").status_code, 404)

    def test_csrf_and_http_methods(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.url, {"action": "generate"}).status_code, 403)
        self.save_plan()
        self.assertEqual(client.post(self.url, {"step_0": "on"}).status_code, 403)
        client.get(self.url)
        self.assertEqual(client.post(self.url, {"step_0": "on"}, HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value).status_code, 302)
        self.assertEqual(self.client.put(self.url).status_code, 405)

    @override_settings(ROADMAP_REQUESTS_PER_DAY=1)
    @patch("roadmap.generator.semantic_skill_match", return_value=(0, []))
    def test_daily_generation_limit_cannot_be_reset_by_retake(self, match):
        self.assertEqual(self.client.post(self.url, {"action": "generate"}).status_code, 302)
        SavedRoadmap.objects.filter(user=self.user).delete()
        self.assertEqual(self.client.post(self.url, {"action": "generate"}).status_code, 429)

    @patch("roadmap.generator.semantic_skill_match", return_value=(0, []))
    def test_corrupt_saved_content_is_only_replaced_by_post(self, match):
        saved = self.save_plan()
        SavedRoadmap.objects.filter(pk=saved.pk).update(steps_json="broken")
        RoadmapProgress.objects.create(user=self.user, career=self.career, step_index=0)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        saved.refresh_from_db()
        self.assertEqual(saved.steps_json, "broken")
        self.assertEqual(self.client.post(self.url, {"action": "generate"}).status_code, 302)
        self.assertFalse(RoadmapProgress.objects.filter(user=self.user).exists())
        json.loads(SavedRoadmap.objects.get(user=self.user).steps_json)


@override_settings(GROQ_API_KEY="test-placeholder")
class GroqRoadmapTests(UserDataTestCase):
    def setUp(self):
        super().setUp()
        self.match = patch("roadmap.generator.semantic_skill_match", return_value=(0.5, ["SQL"]))
        self.match.start()
        self.addCleanup(self.match.stop)

    def data(self):
        return {"roadmap_title": "Personalised plan", "overview": "A plan", "steps": [
            {"title": f"Step {i}", "phase": "Foundation", "difficulty": "Beginner", "description": "Practise"}
            for i in range(5)]}

    def completion(self, content):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    @patch("groq.Groq")
    def test_groq_success_and_persistence_reuse(self, groq):
        client = groq.return_value.__enter__.return_value
        client.chat.completions.create.return_value = self.completion(json.dumps(self.data()))
        steps, title, overview = get_or_create_roadmap(self.user, self.career)
        self.assertEqual(len(steps), 5)
        self.assertEqual(title, "Personalised plan")
        self.assertEqual(get_or_create_roadmap(self.user, self.career)[1], title)
        client.chat.completions.create.assert_called_once()
        self.assertEqual(groq.call_args.kwargs["max_retries"], 0)
        self.assertEqual(groq.call_args.kwargs["timeout"], 20)

    @patch("groq.Groq")
    def test_external_failure_uses_fallback(self, groq):
        groq.return_value.__enter__.return_value.chat.completions.create.side_effect = RuntimeError("private provider detail")
        steps, _, _ = generate_roadmap(self.user, self.career)
        self.assertGreaterEqual(len(steps), 3)
        self.assertTrue(any("SQL" in step.title for step in steps))

    @patch("groq.Groq")
    def test_invalid_json_and_structures_use_fallback(self, groq):
        client = groq.return_value.__enter__.return_value
        for payload in ["bad", "[]", '[1]', '{"steps":[null]}', '{"steps":"wrong"}',
                        json.dumps({**self.data(), "overview": ["wrong"]}),
                        json.dumps({**self.data(), "steps": [{"title": None}] * 5})]:
            with self.subTest(payload=payload):
                client.chat.completions.create.return_value = self.completion(payload)
                steps, title, _ = generate_roadmap(self.user, self.career)
                self.assertGreaterEqual(len(steps), 3)
                self.assertEqual(title, f"Roadmap: {self.career.title}")

    @patch("groq.Groq")
    def test_generated_html_is_escaped_in_roadmap(self, groq):
        data = self.data()
        data["steps"][0]["description"] = '<script>alert("x")</script>'
        groq.return_value.__enter__.return_value.chat.completions.create.return_value = self.completion(json.dumps(data))
        self.client.post(f"/roadmap/{self.career.pk}/", {"action": "generate"})
        response = self.client.get(f"/roadmap/{self.career.pk}/")
        self.assertNotContains(response, '<script>alert("x")</script>')
        self.assertContains(response, "&lt;script&gt;")
