import os
from unittest.mock import patch
from django.conf import settings
from django.test import SimpleTestCase, override_settings
from django.urls import reverse


class SecurityConfigurationTests(SimpleTestCase):
    def test_secret_is_configured(self):
        self.assertTrue(settings.SECRET_KEY)

    @override_settings(DEBUG=False)
    def test_security_defaults(self):
        self.assertTrue(settings.SESSION_COOKIE_SECURE)
        self.assertTrue(settings.CSRF_COOKIE_SECURE)
        self.assertTrue(settings.SECURE_SSL_REDIRECT)
        self.assertGreater(settings.SECURE_HSTS_SECONDS, 0)

    def test_login_requires_authentication_for_dashboard(self):
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)
