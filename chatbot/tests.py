import json
from types import SimpleNamespace
from unittest.mock import patch

from django.test import Client, override_settings

from careercoach.test_utils import UserDataTestCase


class ChatbotTests(UserDataTestCase):
    def send(self, data):
        return self.client.post("/chat/message/", json.dumps(data), content_type="application/json")

    def test_invalid_message_shapes_and_types(self):
        for value in [None, [], 1, {}, {"message": None}, {"message": []}, {"message": True},
                      {"message": 1}, {"message": "  "}, {"message": "x" * 1001}]:
            with self.subTest(value=value):
                self.assertEqual(self.send(value).status_code, 400)

    def test_invalid_json_encoding_and_content_type(self):
        for value in [b"{", b"\xff", b"[" * 2000 + b"]" * 2000]:
            self.assertEqual(self.client.post("/chat/message/", value, content_type="application/json").status_code, 400)
        self.assertEqual(self.client.post("/chat/message/", {"message": "Hello"}).status_code, 415)

    def test_missing_configuration_is_generic(self):
        response = self.send({"message": "Hello"})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("settings.py", response.json()["error"])
        self.assertNotIn("GROQ_API_KEY", response.json()["error"])

    def test_methods_and_clear(self):
        self.assertEqual(self.client.get("/chat/message/").status_code, 405)
        self.assertEqual(self.client.get("/chat/clear/").status_code, 405)
        session = self.client.session
        session["chatbot_history"] = [{"role": "user", "content": "private"}]
        session.save()
        self.client.get("/chat/clear/")
        self.assertIn("chatbot_history", self.client.session)
        self.assertEqual(self.client.post("/chat/clear/").status_code, 200)
        self.assertNotIn("chatbot_history", self.client.session)

    def test_csrf_protects_message_and_clear(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        for path in ["/chat/message/", "/chat/clear/"]:
            self.assertEqual(client.post(path, {}).status_code, 403)
        client.get("/chat/")
        self.assertEqual(client.post("/chat/clear/", {}, HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value).status_code, 200)

    @override_settings(CHAT_REQUESTS_PER_MINUTE=1)
    def test_per_user_rate_limit_and_other_user_independence(self):
        self.assertEqual(self.send({"message": "Hello"}).status_code, 503)
        self.assertEqual(self.send({"message": "Hello"}).status_code, 429)
        self.client.force_login(self.other)
        self.assertEqual(self.send({"message": "Hello"}).status_code, 503)

    @override_settings(CHAT_REQUESTS_PER_DAY=1)
    def test_clearing_history_does_not_reset_daily_quota(self):
        self.send({"message": "Hello"})
        self.client.post("/chat/clear/")
        self.assertEqual(self.send({"message": "Hello"}).status_code, 429)

    def test_session_history_is_isolated_and_escaped(self):
        session = self.client.session
        session["chatbot_history"] = [{"role": "user", "content": '<script>alert("x")</script>'}]
        session.save()
        response = self.client.get("/chat/")
        self.assertNotContains(response, '<script>alert("x")</script>')
        self.assertContains(response, "&lt;script&gt;")
        other = Client()
        other.force_login(self.other)
        self.assertNotContains(other.get("/chat/"), "&lt;script&gt;")


@override_settings(GROQ_API_KEY="test-placeholder")
class GroqChatTests(UserDataTestCase):
    def send(self, data):
        return self.client.post("/chat/message/", json.dumps(data), content_type="application/json")

    @patch("groq.Groq")
    def test_success_stores_history_and_limits_context(self, groq):
        session = self.client.session
        session["chatbot_history"] = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"Turn {i}"} for i in range(20)]
        session.save()
        client = groq.return_value.__enter__.return_value
        client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Learn Python."))])
        response = self.send({"message": "Next step?"})
        self.assertEqual(response.json(), {"reply": "Learn Python."})
        history = self.client.session["chatbot_history"]
        self.assertEqual(len(history), 20)
        self.assertEqual(history[-1]["content"], "Learn Python.")
        self.assertEqual(history[-2]["content"], "Next step?")
        self.assertEqual(groq.call_args.kwargs["max_retries"], 0)
        self.assertEqual(groq.call_args.kwargs["timeout"], 20)

    @patch("groq.Groq")
    def test_external_error_does_not_leak_details_or_change_history(self, groq):
        client = groq.return_value.__enter__.return_value
        client.chat.completions.create.side_effect = RuntimeError("sensitive provider response")
        response = self.send({"message": "Hello"})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("sensitive", response.json()["error"])
        self.assertNotIn("chatbot_history", self.client.session)

    @patch("groq.Groq")
    def test_empty_or_invalid_provider_reply_is_handled(self, groq):
        client = groq.return_value.__enter__.return_value
        for value in [None, "", "x" * 12001]:
            with self.subTest(value=type(value).__name__):
                client.chat.completions.create.return_value = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=value))])
                self.assertEqual(self.send({"message": "Hello"}).status_code, 502)

    @patch("chatbot.views._build_system_prompt", side_effect=RuntimeError("private model path"))
    def test_prompt_context_failure_is_generic(self, prompt):
        response = self.send({"message": "Hello"})
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("private", response.json()["error"])

    def test_prompt_uses_only_current_user_data(self):
        from assessment.models import SkillRating
        from chatbot.views import _build_system_prompt
        SkillRating.objects.filter(response__user=self.other).update(skill_name="Other user's private skill")
        prompt = _build_system_prompt(self.user)
        self.assertIn("Programming", prompt)
        self.assertNotIn("Other user's private skill", prompt)
