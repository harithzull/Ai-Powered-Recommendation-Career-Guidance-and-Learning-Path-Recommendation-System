"""Check production settings with disposable values, never a developer's .env.

This validates configuration defaults; also run check --deploy in the actual
deployment environment before release.
"""
import os
from pathlib import Path
import secrets
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
environment = {key: value for key, value in os.environ.items()
               if not key.startswith(("DJANGO_", "GROQ_"))}
environment.update({
    "DJANGO_SETTINGS_MODULE": "careercoach.settings",
    "DJANGO_READ_DOT_ENV": "false",
    "DJANGO_DEBUG": "false",
    "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
    "DJANGO_ALLOWED_HOSTS": "careercoach.example.com",
    "DJANGO_CSRF_TRUSTED_ORIGINS": "https://careercoach.example.com",
    # Simulate a fully HTTPS deployment, including HTTPS on every subdomain.
    "DJANGO_HSTS_SECONDS": "31536000",
    "DJANGO_HSTS_INCLUDE_SUBDOMAINS": "true",
    "DJANGO_HSTS_PRELOAD": "true",
    "GROQ_API_KEY": "",
})
result = subprocess.run([sys.executable, "-B", "manage.py", "check", "--deploy", "--fail-level", "WARNING"],
                        cwd=root, env=environment)
sys.exit(result.returncode)
