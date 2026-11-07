"""Fail tests that accidentally depend on external services."""
from unittest.mock import patch

from django.test.runner import DiscoverRunner


class OfflineTestRunner(DiscoverRunner):
    def run_tests(self, *args, **kwargs):
        with patch("socket.socket.connect", side_effect=AssertionError("Network access is forbidden in tests")):
            return super().run_tests(*args, **kwargs)
