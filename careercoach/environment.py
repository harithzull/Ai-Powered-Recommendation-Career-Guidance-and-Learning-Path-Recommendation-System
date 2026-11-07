"""Small, strict environment parsers shared by settings and their tests."""
import os

from django.core.exceptions import ImproperlyConfigured


def env_bool(name, default=False):
    value = os.environ.get(name, str(default)).strip().lower()
    if value not in {"true", "false", "1", "0", "yes", "no"}:
        raise ImproperlyConfigured(f"{name} must be true or false.")
    return value in {"true", "1", "yes"}


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


def env_int(name, default, minimum=0):
    try:
        value = int(os.environ.get(name, default))
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} must be an integer.") from exc
    if value < minimum:
        raise ImproperlyConfigured(f"{name} must be at least {minimum}.")
    return value
