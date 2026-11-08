"""Conservative keys for equality and alias lookup, never fuzzy entity merging."""
import unicodedata


def normalize_label(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())
