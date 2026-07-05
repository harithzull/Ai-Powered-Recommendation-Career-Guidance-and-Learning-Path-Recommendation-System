"""
Adaptive RIASEC engine.

Item-by-item adaptive selection: each answer decides the next question.
The engine is *stateless* — it is handed the full answer history so far and
returns the next question (or ``None`` when the assessment is complete). This
keeps the branching logic in one testable place and avoids server-side session
state during the walk.

Branching rule (per the user's last answer):
  * Agree / Strongly agree (4-5) -> deepen: ask ONE more question of the SAME
    type to confirm the interest (capped at two questions per type, so a type
    is never asked more than twice in a row).
  * Neutral (3)                  -> ask ONE clarifying same-type question, then
    move on.
  * Disagree / Strongly disagree (1-2) -> drop that type and move to a type the
    user hasn't seen yet.

Coverage is guaranteed: the engine never deepens a type if doing so would leave
too few remaining slots to give every still-unseen type at least one question.
Once all six types are covered, leftover budget deepens the highest-scoring
(most liked) types, still capped at two questions per type.
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import RIASECQuestion

# Tuning knobs
TOTAL_TARGET = 12     # upper bound on questions in a full walk (6 types x 2)
PER_TYPE_CAP = 2      # never ask more than this many questions of one type
LIKE_THRESHOLD = 3.5  # avg rating at/above which a type counts as "liked"
RIASEC_ORDER = "RIASEC"


@dataclass
class NextQuestion:
    done: bool
    question: RIASECQuestion | None
    answered: int
    target: int


def _by_type() -> dict[str, list[RIASECQuestion]]:
    """All pool questions grouped by type, each list ordered by ``order``."""
    pool: dict[str, list[RIASECQuestion]] = {t: [] for t in RIASEC_ORDER}
    for q in RIASECQuestion.objects.all():           # Meta ordering = ["order"]
        pool.setdefault(q.riasec_type, []).append(q)
    return pool


def _first_unused(pool_for_type: list[RIASECQuestion], asked_ids: set[int]):
    for q in pool_for_type:
        if q.id not in asked_ids:
            return q
    return None


def select_next(history: list[tuple[int, int]]) -> NextQuestion:
    """
    Args:
        history: list of (question_id, rating) in the order they were answered.

    Returns:
        NextQuestion. ``done=True`` (question=None) when the walk is complete.
    """
    pool = _by_type()
    qtype = {q.id: t for t in pool for q in pool[t]}

    asked_ids = {qid for qid, _ in history}
    counts: dict[str, int] = {t: 0 for t in RIASEC_ORDER}
    sums: dict[str, int] = {t: 0 for t in RIASEC_ORDER}
    for qid, rating in history:
        t = qtype.get(qid)
        if t:
            counts[t] += 1
            sums[t] += rating

    answered = len(history)
    uncovered = [t for t in RIASEC_ORDER if counts[t] == 0]

    # ── Stop condition ──────────────────────────────────────────────────────
    if answered >= TOTAL_TARGET and not uncovered:
        return NextQuestion(done=True, question=None,
                            answered=answered, target=TOTAL_TARGET)

    def has_unused(t: str) -> bool:
        return _first_unused(pool.get(t, []), asked_ids) is not None

    # Keep enough slots free to still cover every unseen type.
    remaining_budget = TOTAL_TARGET - answered
    allow_deepen = remaining_budget > len(uncovered)

    desired: str | None = None

    # Deepen on agreement, but only up to PER_TYPE_CAP (2) questions per type.
    if history:
        last_id, last_rating = history[-1]
        last_type = qtype.get(last_id)
        if last_type and has_unused(last_type) and counts[last_type] < PER_TYPE_CAP and allow_deepen:
            if last_rating >= 4:
                desired = last_type                       # agree -> deepen
            elif last_rating == 3 and counts[last_type] < 2:
                desired = last_type                       # neutral -> one clarifier

    # Move on: cover an unseen type first, otherwise deepen the most-liked type.
    if desired is None:
        for t in uncovered:
            if has_unused(t):
                desired = t
                break

    # All six types covered: deepen only types the user actually likes. If they
    # like nothing, the walk ends early rather than probing disliked types.
    if desired is None:
        candidates = [
            t for t in RIASEC_ORDER
            if has_unused(t) and 0 < counts[t] < PER_TYPE_CAP
            and (sums[t] / counts[t]) >= LIKE_THRESHOLD
        ]
        if candidates:
            desired = max(candidates, key=lambda t: (sums[t] / counts[t], -RIASEC_ORDER.index(t)))

    if desired is None:
        # Nothing left we're allowed to ask.
        return NextQuestion(done=True, question=None,
                            answered=answered, target=TOTAL_TARGET)

    nxt = _first_unused(pool[desired], asked_ids)
    if nxt is None:
        return NextQuestion(done=True, question=None,
                            answered=answered, target=TOTAL_TARGET)

    return NextQuestion(done=False, question=nxt,
                        answered=answered, target=TOTAL_TARGET)
