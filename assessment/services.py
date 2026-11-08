"""Balanced, versioned assessment lifecycle. Call mutations under the user's work lease."""
from collections import Counter
import random
import secrets

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from recommender.models import CachedRecommendation
from .models import AssessmentSession, InterestItem, QuestionBank, SessionItem, UserResponse
from .scoring import AssessmentError, DIMENSIONS, MODE_COUNTS, SCORING_VERSION, score_answers


class SessionConflict(AssessmentError):
    pass


def validate_bank(bank):
    items = list(bank.items.filter(status=InterestItem.Status.ACTIVE).order_by("code"))
    if Counter(i.dimension for i in items) != Counter(dict.fromkeys(DIMENSIONS, 6)):
        raise AssessmentError("The question bank needs six active questions in every interest category.")
    if Counter(i.dimension for i in items if i.quick_core) != Counter(dict.fromkeys(DIMENSIONS, 3)):
        raise AssessmentError("The question bank needs three Quick core questions in every interest category.")
    if any(not item.text.strip() or not item.facet.strip() or not item.purpose.strip() for item in items):
        raise AssessmentError("The question bank is missing item content or review information.")
    return items


def select_items(bank, mode, seed):
    if mode not in MODE_COUNTS:
        raise AssessmentError("Choose Quick or Detailed assessment.")
    items = validate_bank(bank)
    rng = random.Random(seed)  # Reproducible ordering, not a security token.
    groups = {t: [i for i in items if i.dimension == t and (mode == "detailed" or i.quick_core)] for t in DIMENSIONS}
    order = list(DIMENSIONS)
    rng.shuffle(order)
    for group in groups.values():
        rng.shuffle(group)
    return [groups[t][round_index] for round_index in range(MODE_COUNTS[mode]) for t in order]


@transaction.atomic
def start_session(user, mode, *, seed=None):
    if mode not in MODE_COUNTS:
        raise AssessmentError("Choose Quick or Detailed assessment.")
    if AssessmentSession.objects.filter(user=user, status="in_progress").exists():
        raise SessionConflict("Resume or abandon your existing assessment before starting another.")
    bank = QuestionBank.objects.filter(status="active").first()
    if bank is None:
        raise AssessmentError("The assessment is temporarily unavailable: no active question bank.")
    seed = seed or secrets.token_hex(16)
    items = select_items(bank, mode, seed)
    session = AssessmentSession.objects.create(user=user, bank=bank, mode=mode,
                                              selection_seed=seed, scoring_version=SCORING_VERSION)
    SessionItem.objects.bulk_create([SessionItem(session=session, item=item, position=position,
        code=item.code, dimension=item.dimension, text=item.text, facet=item.facet) for position, item in enumerate(items)])
    return session


def _editable(user, session_id, revision):
    session = get_object_or_404(AssessmentSession.objects.select_for_update(), pk=session_id, user=user)
    if session.status != AssessmentSession.Status.IN_PROGRESS:
        raise SessionConflict("This assessment is closed. Start a retake to answer again.")
    if type(revision) is not int or revision != session.revision:
        raise SessionConflict("This page is out of date. Reload it before saving again.")
    return session


@transaction.atomic
def save_answer(user, session_id, *, position, item_id, rating, revision, action="next"):
    session = _editable(user, session_id, revision)
    if action not in {"next", "previous", "save"} or type(position) is not int:
        raise AssessmentError("Invalid navigation action.")
    selected = get_object_or_404(SessionItem, session=session, position=position, pk=item_id)
    if rating is None:
        if action != "previous":
            raise AssessmentError("Select how much you would enjoy this activity.")
    elif type(rating) is not int or not 1 <= rating <= 5:
        raise AssessmentError("Select a response from 1 to 5.")
    else:
        selected.rating, selected.answered_at = rating, timezone.now()
        selected.save(update_fields=["rating", "answered_at"])
    total = session.items.count()
    session.current_position = max(0, position - 1) if action == "previous" else min(position + (action == "next"), total - 1)
    session.revision += 1
    session.save(update_fields=["current_position", "revision"])
    return session


@transaction.atomic
def finalize_session(user, session_id, *, revision):
    session = _editable(user, session_id, revision)
    if session.scoring_version != SCORING_VERSION:
        raise AssessmentError("This session's scoring version is unsupported; please contact support.")
    rows = list(session.items.all())
    result = score_answers([{"id": row.code, "dimension": row.dimension, "rating": row.rating} for row in rows],
                          mode=session.mode, bank_version=session.bank.version)
    now = timezone.now()
    response, _ = UserResponse.objects.get_or_create(user=user, defaults={"completed_at": now})
    profile = getattr(user, "profile", None)
    session.context_snapshot = {
        "field_of_study": getattr(profile, "field_of_study", ""),
        "experience_level": getattr(profile, "experience_level", ""),
        "skills": list(response.skill_ratings.values("skill_name", "rating")),
    }
    session.result, session.completed_at, session.status = result, now, AssessmentSession.Status.COMPLETED
    session.revision += 1
    session.save(update_fields=["result", "completed_at", "status", "context_snapshot", "revision"])
    response.active_session = session
    fields = ["active_session"]
    if response.completed_at is None:
        response.completed_at = now
        fields.append("completed_at")
    response.save(update_fields=fields)
    CachedRecommendation.objects.filter(user=user).delete()
    return session


@transaction.atomic
def abandon_session(user, session_id, *, revision):
    session = _editable(user, session_id, revision)
    session.status = AssessmentSession.Status.ABANDONED
    session.revision += 1
    session.save(update_fields=["status", "revision"])
    return session


def comparable(first, second):
    if first.mode == "legacy" or second.mode == "legacy":
        return False
    return (first.status == second.status == "completed" and first.mode == second.mode
            and first.scoring_version == second.scoring_version and first.bank_id == second.bank_id
            and set(first.items.values_list("code", flat=True)) == set(second.items.values_list("code", flat=True)))
