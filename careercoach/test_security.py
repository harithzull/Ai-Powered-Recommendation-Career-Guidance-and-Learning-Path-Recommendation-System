from django.conf import settings
from django.test import SimpleTestCase


class SecurityConfigurationTests(SimpleTestCase):
    def test_secret_is_configured(self):
        self.assertTrue(settings.SECRET_KEY)

    def test_security_flags_follow_environment(self):
        self.assertEqual(settings.SESSION_COOKIE_SECURE, not settings.DEBUG)
        self.assertEqual(settings.CSRF_COOKIE_SECURE, not settings.DEBUG)
        self.assertEqual(settings.SECURE_SSL_REDIRECT, not settings.DEBUG)

    def test_login_requires_authentication_for_dashboard(self):
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)
