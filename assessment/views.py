import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from .adaptive import select_next
from .models import RIASECAnswer, RIASECQuestion, SkillRating, UserResponse
from .suggested_skills import get_suggested_skills
from recommender.cache import compute_and_cache, invalidate as invalidate_rec_cache
from recommender.scoring import normalized_riasec
from recommender.models import Skill

RATING_OPTIONS = [
    (1, "1 – Strongly Disagree"),
    (2, "2 – Disagree"),
    (3, "3 – Neutral"),
    (4, "4 – Agree"),
    (5, "5 – Strongly Agree"),
]

_VALID = {"1", "2", "3", "4", "5"}


def _safe_int(val, default=0):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


# ─────────────────────────────────────────────────────────────────────────────
# PAGE 1 — RIASEC interest questions
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def background(request):
    """
    Step 1 of 3: collect the user's background (field of study + experience).
    Saves to UserProfile, then continues to the interest assessment.
    """
    from accounts.forms import ProfileForm
    from accounts.models import UserProfile

    if request.method == "GET" and request.GET.get("retake") == "1":
        UserResponse.objects.filter(user=request.user).delete()
        invalidate_rec_cache(request.user)

    instance, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = ProfileForm(request.POST, instance=instance)
        # Both fields are optional on the model, but required for this step.
        form.fields["field_of_study"].required = True
        form.fields["experience_level"].required = True
        if form.is_valid():
            form.save()
            return redirect("assessment:interests")
    else:
        form = ProfileForm(instance=instance)

    return render(request, "assessment/background.html", {"form": form})


@login_required
def interests(request):
    """
    Step 2 of 3: adaptive RIASEC interest walk.

    GET renders a shell; the page drives one question at a time via the
    ``next_question`` JSON endpoint and finally POSTs the collected answers
    here as ``answers_json`` = ``[{"id": <qid>, "rating": <1-5>}, ...]``.
    """
    if request.method == "GET" and request.GET.get("retake") == "1":
        UserResponse.objects.filter(user=request.user).delete()
        invalidate_rec_cache(request.user)

    # Guard: background (step 1) must be completed before the interest walk.
    from accounts.models import UserProfile
    prof, _ = UserProfile.objects.get_or_create(user=request.user)
    if not prof.is_complete():
        return redirect("assessment:background")

    if request.method == "POST":
        raw = request.POST.get("answers_json", "[]").strip() or "[]"
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            messages.error(request, "Your answers were malformed — please try again.")
            return redirect("assessment:interests")

        # Validate and de-duplicate (last answer for a question wins).
        cleaned: dict[int, int] = {}
        for item in payload if isinstance(payload, list) else []:
            qid = _safe_int(item.get("id")) if isinstance(item, dict) else 0
            rating = str(item.get("rating", "")) if isinstance(item, dict) else ""
            if qid and rating in _VALID:
                cleaned[qid] = int(rating)

        valid_questions = {
            q.id: q for q in RIASECQuestion.objects.filter(id__in=cleaned.keys())
        }
        if len(valid_questions) < 6:
            messages.error(request, "Please complete the interest assessment before continuing.")
            return redirect("assessment:interests")

        with transaction.atomic():
            response, _ = UserResponse.objects.get_or_create(user=request.user)
            RIASECAnswer.objects.filter(response=response).delete()
            RIASECAnswer.objects.bulk_create([
                RIASECAnswer(response=response, question=q, rating=cleaned[qid])
                for qid, q in valid_questions.items()
            ])

        return redirect("assessment:skills")

    return render(request, "assessment/interests.html", {
        "rating_options": RATING_OPTIONS,
    })


@require_POST
@login_required
def next_question(request):
    """JSON endpoint: given the answer history, return the next question."""
    try:
        body = json.loads(request.body or "{}")
        history_raw = body.get("history", [])
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "bad request"}, status=400)

    history: list[tuple[int, int]] = []
    for item in history_raw if isinstance(history_raw, list) else []:
        if not isinstance(item, dict):
            continue
        qid = _safe_int(item.get("id"))
        rating = _safe_int(item.get("rating"))
        if qid and 1 <= rating <= 5:
            history.append((qid, rating))

    result = select_next(history)
    if result.done or result.question is None:
        return JsonResponse({"done": True, "answered": result.answered})

    q = result.question
    return JsonResponse({
        "done": False,
        "answered": result.answered,
        "target": result.target,
        "question": {
            "id":   q.id,
            "type": q.riasec_type,
            "text": q.text,
        },
    })


# ─────────────────────────────────────────────────────────────────────────────
# PAGE 2 — Adaptive skill pills
# ─────────────────────────────────────────────────────────────────────────────

@login_required
def skills(request):
    """Step 2 of 2: Adaptive pill skill rating. Requires Page 1 to be done."""
    # Guard: redirect back if Page 1 not completed
    # Prefetch riasec_answers__question so we can compute the profile from
    # the in-memory cache — avoids a second DB round-trip that could read a
    # stale snapshot on retake (Bug 1).
    try:
        response = UserResponse.objects.prefetch_related(
            "riasec_answers__question", "skill_ratings"
        ).get(user=request.user)
        if not response.riasec_answers.exists():
            return redirect("assessment:interests")
    except UserResponse.DoesNotExist:
        return redirect("assessment:interests")

    # Compute RIASEC profile from the already-prefetched answers (no extra query)
    profile = normalized_riasec(
        (a.question.riasec_type, a.rating)
        for a in response.riasec_answers.all()   # uses prefetch cache
    )

    try:
        field_of_study = response.user.profile.field_of_study
    except AttributeError:
        field_of_study = ""

    suggested: list[str] = get_suggested_skills(
        profile,
        field_of_study=field_of_study,
        top_types=1,
    )

    # Pre-populate from existing skill ratings
    initial_ratings: dict[str, int] = {
        s.skill_name: s.rating for s in response.skill_ratings.all()
    }

    if request.method == "POST":
        # Parse JSON blob of {skill_name: rating} from pill UI
        raw = request.POST.get("rated_skills_json", "{}").strip() or "{}"
        submitted_skills: dict[str, int] = {}
        try:
            for name, val in json.loads(raw).items():
                name = str(name).strip()
                try:
                    r = int(val)
                except (TypeError, ValueError):
                    continue
                if name and 1 <= r <= 5:
                    submitted_skills[name] = r
        except (json.JSONDecodeError, ValueError):
            messages.error(request, "Skill data was malformed — please try again.")
            return redirect("assessment:skills")

        with transaction.atomic():
            response.save(update_fields=["submitted_at"])
            SkillRating.objects.filter(response=response).delete()
            if submitted_skills:
                SkillRating.objects.bulk_create([
                    SkillRating(response=response, skill_name=n, rating=r)
                    for n, r in submitted_skills.items()
                ])

        # Recompute and overwrite the cache now that new skill ratings are saved.
        # Called outside the atomic block so the fresh DB rows are visible.
        compute_and_cache(request.user)

        # The assessment changed, so saved roadmaps (and their step progress)
        # are stale — clear them so the next roadmap visit regenerates.
        from roadmap.models import RoadmapProgress, SavedRoadmap
        SavedRoadmap.objects.filter(user=request.user).delete()
        RoadmapProgress.objects.filter(user=request.user).delete()

        messages.success(request, "Assessment saved! Your responses have been recorded.")
        return redirect("dashboard:index")

    return render(request, "assessment/skills.html", {
        "suggested_skills_json": json.dumps(suggested),
        "initial_ratings_json":  json.dumps(initial_ratings),
        "pill_count":            len(suggested),
    })


# ─────────────────────────────────────────────────────────────────────────────
# Backward-compat alias — existing redirect("assessment:quiz") calls land here
# ─────────────────────────────────────────────────────────────────────────────

def quiz(request):
    return redirect("assessment:background")


# ─────────────────────────────────────────────────────────────────────────────
# Skill search endpoint — used by the live-search box in skills.html
# ─────────────────────────────────────────────────────────────────────────────

@require_GET
@login_required
def skill_search(request):
    q = request.GET.get("q", "").strip()
    if len(q) < 2:
        return JsonResponse({"results": []})
    names = list(
        Skill.objects.filter(name__icontains=q)
        .order_by("name")
        .values_list("name", flat=True)[:10]
    )
    return JsonResponse({"results": names})
