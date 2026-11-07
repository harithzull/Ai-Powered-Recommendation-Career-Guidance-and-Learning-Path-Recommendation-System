import os
import subprocess
import sys
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from .environment import env_bool, env_int, env_list


class EnvironmentTests(SimpleTestCase):
    def test_boolean_values_are_explicit(self):
        for value in ["true", "1", "YES"]:
            with self.subTest(value=value), patch.dict(os.environ, {"FLAG": value}):
                self.assertTrue(env_bool("FLAG"))
        with patch.dict(os.environ, {"FLAG": "treu"}):
            with self.assertRaises(ImproperlyConfigured):
                env_bool("FLAG")

    def test_lists_and_positive_limits(self):
        with patch.dict(os.environ, {"HOSTS": " localhost,example.com, ", "LIMIT": "0"}):
            self.assertEqual(env_list("HOSTS"), ["localhost", "example.com"])
            with self.assertRaises(ImproperlyConfigured):
                env_int("LIMIT", 10, 1)

    def _settings_process(self, **overrides):
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith(("DJANGO_", "GROQ_"))}
        environment.update({
            "DJANGO_READ_DOT_ENV": "false", "DJANGO_DEBUG": "false",
            "DJANGO_SECRET_KEY": "test-production-check-secret-with-sufficient-entropy-729516abcd",
            "DJANGO_ALLOWED_HOSTS": "careercoach.example.com",
        })
        environment.update(overrides)
        return subprocess.run([sys.executable, "-B", "-c",
                               "import careercoach.settings as s; "
                               "assert s.SESSION_COOKIE_SECURE and s.CSRF_COOKIE_SECURE; "
                               "assert s.SECURE_SSL_REDIRECT; assert s.SECURE_HSTS_SECONDS > 0; "
                               "assert s.GROQ_API_KEY == ''"],
                              env=environment, capture_output=True, text=True, timeout=30)

    def test_production_defaults_enable_transport_security(self):
        result = self._settings_process()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_secret_fails_closed(self):
        result = self._settings_process(DJANGO_SECRET_KEY="")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Set DJANGO_SECRET_KEY", result.stderr)

    def test_production_rejects_wildcard_hosts_and_weak_secret(self):
        for values in [{"DJANGO_ALLOWED_HOSTS": "*"}, {"DJANGO_SECRET_KEY": "weak"}]:
            with self.subTest(values=values):
                self.assertNotEqual(self._settings_process(**values).returncode, 0)
