"""Deterministic offline settings: never load a developer's credentials or database."""
import os

os.environ["DJANGO_READ_DOT_ENV"] = "false"
os.environ["DJANGO_DEBUG"] = "true"
os.environ["DJANGO_SECRET_KEY"] = "test-only-secret-for-offline-tests-never-use-in-production-729516"
os.environ["DJANGO_ALLOWED_HOSTS"] = "testserver,localhost,127.0.0.1"

from .settings import *  # noqa: E402,F403

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
GROQ_API_KEY = ""
EMBEDDING_LOCAL_FILES_ONLY = True
TEST_RUNNER = "careercoach.testing.OfflineTestRunner"
