"""Validate the bounded assessment protocol before touching stored answers."""
import json
from collections import Counter

from .adaptive import PER_TYPE_CAP, TOTAL_TARGET
from .models import RIASECQuestion

MAX_SKILLS = 30
MAX_JSON_LENGTH = 16000


def parse_json(raw):
    if len(raw) > MAX_JSON_LENGTH:
        raise ValueError("Payload too large")
    try:
        return json.loads(raw)
    except RecursionError as exc:
        raise ValueError("JSON nesting is too deep") from exc


def clean_history(payload, *, complete=False):
    if not isinstance(payload, list) or len(payload) > TOTAL_TARGET:
        raise ValueError("Expected a bounded answer list")
    history = []
    seen = set()
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("Expected an answer object")
        qid, rating = item.get("id"), item.get("rating")
        if type(qid) is not int or qid <= 0 or type(rating) is not int or not 1 <= rating <= 5 or qid in seen:
            raise ValueError("Invalid answer")
        history.append((qid, rating))
        seen.add(qid)
    questions = {q.pk: q for q in RIASECQuestion.objects.filter(pk__in=seen)}
    if len(questions) != len(history):
        raise ValueError("Unknown question")
    counts = Counter(q.riasec_type for q in questions.values())
    if any(count > PER_TYPE_CAP for count in counts.values()):
        raise ValueError("Too many questions for one type")
    if complete and set(counts) != set("RIASEC"):
        raise ValueError("All six interest types are required")
    return history, questions


def clean_skills(payload):
    # Choosing no skills is allowed: the recommendation engine supports this.
    if not isinstance(payload, dict) or len(payload) > MAX_SKILLS:
        raise ValueError("Expected a bounded skill object")
    cleaned = {}
    for name, rating in payload.items():
        name = name.strip()
        if not name or len(name) > 100 or name in cleaned or type(rating) is not int or not 1 <= rating <= 5:
            raise ValueError("Invalid skill name or rating")
        cleaned[name] = rating
    return cleaned
