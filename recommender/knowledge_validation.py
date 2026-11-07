"""Validation for provenance and curated knowledge-base records."""
import re
from uuid import UUID

from django.core.exceptions import ValidationError

from .normalization import normalize_label


def validate_metadata(value):
    if not isinstance(value, dict):
        raise ValidationError("Metadata must be a JSON object.")


def validate_occupation_uri(value):
    _validate_uri(value, "occupation")


def validate_skill_uri(value):
    _validate_uri(value, "skill")


def _validate_uri(value, kind):
    if not value:
        return
    try:
        if not re.fullmatch(r"https?://data\.europa\.eu/esco/" + kind + r"/[0-9a-fA-F-]{36}", value):
            raise ValueError
        UUID(value.rsplit("/", 1)[-1])
    except ValueError as exc:
        raise ValidationError(f"Expected an authoritative ESCO {kind} URI. Do not generate one from a label.") from exc


def validate_localized_titles(value):
    validate_metadata(value)
    for locale, titles in value.items():
        if not re.fullmatch(r"[a-z]{2}(?:-[A-Z]{2})?", locale) or not isinstance(titles, list):
            raise ValidationError("Use locale keys such as en-MY and lists of titles.")
        keys = []
        for title in titles:
            if not isinstance(title, str) or not title.strip() or len(title) > 255:
                raise ValidationError("Localized titles must be nonempty strings of at most 255 characters.")
            keys.append(normalize_label(title))
        if len(set(keys)) != len(keys):
            raise ValidationError("Localized titles must not contain equivalent duplicates.")


def validate_riasec_profile(value):
    if value is None:
        return
    if not isinstance(value, dict) or set(value) != set("RIASEC"):
        raise ValidationError("An evidenced profile must define all six RIASEC dimensions.")
    if any(type(score) not in (int, float) or not 0 <= score <= 1 for score in value.values()):
        raise ValidationError("RIASEC profile values must be numbers from 0 to 1.")
