from unittest.mock import patch

from django.test import override_settings

from assessment.models import UserResponse
from careercoach.test_utils import UserDataTestCase


class DashboardTests(UserDataTestCase):
    def test_partial_assessment_is_not_marked_complete(self):
        UserResponse.objects.filter(user=self.user).update(completed_at=None)
        response = self.client.get("/dashboard/")
        self.assertFalse(response.context["has_assessment"])
        self.assertIsNone(response.context["top_rec"])

    @patch("recommender.cache.get_recommendations", return_value=[])
    def test_completed_user_dashboard_preserves_navigation(self, compute):
        response = self.client.get("/dashboard/")
        self.assertTrue(response.context["has_assessment"])
        self.assertContains(response, "/assessment/retake/")
        self.assertContains(response, "/chat/")

    @override_settings(DEBUG=False, ALLOWED_HOSTS=["testserver"], SECURE_SSL_REDIRECT=True,
                       SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True, SECURE_HSTS_SECONDS=3600)
    def test_https_redirect_and_security_headers(self):
        response = self.client.get("/accounts/login/")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.url, "https://testserver/accounts/login/")
        response = self.client.get("/accounts/login/", secure=True)
        self.assertEqual(response["Strict-Transport-Security"], "max-age=3600")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response["X-Frame-Options"], "DENY")
        self.assertTrue(response.cookies["csrftoken"]["secure"])

    @override_settings(DEBUG=False, ALLOWED_HOSTS=["testserver"])
    def test_invalid_host_is_rejected_without_debug_trace(self):
        response = self.client.get("/", HTTP_HOST="evil.example")
        self.assertEqual(response.status_code, 400)
        self.assertNotContains(response, "Traceback", status_code=400)
