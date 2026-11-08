from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.utils import timezone

from .adaptive import select_next
from .validation import clean_history, clean_skills, parse_json
from .state import invalidate_derived
from careercoach.security import rate_limited, serialized_user_work
from .models import RIASECAnswer, RIASECQuestion, SkillRating, UserResponse
from .suggested_skills import get_suggested_skills
from recommender.scoring import normalized_riasec
from recommender.models import Skill
from recommender.aliases import search_skill_names

RATING_OPTIONS = [
    (1, "1 – Strongly Disagree"),
    (2, "2 – Disagree"),
    (3, "3 – Neutral"),
    (4, "4 – Agree"),
    (5, "5 – Strongly Agree"),
]

# ─────────────────────────────────────────────────────────────────────────────
# PAGE 1 — RIASEC interest questions
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@require_http_methods(["GET", "POST"])
@serialized_user_work
def background(request):
    """
    Step 1 of 3: collect the user's background (field of study + experience).
    Saves to UserProfile, then continues to the interest assessment.
    """
    from accounts.forms import ProfileForm
    from accounts.models import UserProfile

    instance, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = ProfileForm(request.POST, instance=instance)
        # Both fields are optional on the model, but required for this step.
        form.fields["field_of_study"].required = True
        form.fields["experience_level"].required = True
        if form.is_valid():
            with transaction.atomic():
                form.save()
                invalidate_derived(request.user)
            return redirect("assessment:interests")
    else:
        form = ProfileForm(instance=instance)

    return render(request, "assessment/background.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
@rate_limited("assessment", "ASSESSMENT_REQUESTS_PER_MINUTE", 60, by_user=True)
@serialized_user_work
def interests(request):
    """
    Step 2 of 3: adaptive RIASEC interest walk.

    GET renders a shell; the page drives one question at a time via the
    ``next_question`` JSON endpoint and finally POSTs the collected answers
    here as ``answers_json`` = ``[{"id": <qid>, "rating": <1-5>}, ...]``.
    """
    # Guard: background (step 1) must be completed before the interest walk.
    from accounts.models import UserProfile
    prof, _ = UserProfile.objects.get_or_create(user=request.user)
    if not prof.is_complete():
        return redirect("assessment:background")

    if request.method == "POST":
        raw = request.POST.get("answers_json", "[]").strip() or "[]"
        try:
            history, valid_questions = clean_history(parse_json(raw), complete=True)
        except ValueError:
            messages.error(request, "Your answers were malformed — please try again.")
            return redirect("assessment:interests")

        cleaned = dict(history)

        with transaction.atomic():
            response, _ = UserResponse.objects.get_or_create(user=request.user)
            response.completed_at = None
            response.save(update_fields=["completed_at", "submitted_at"])
            SkillRating.objects.filter(response=response).delete()
            invalidate_derived(request.user)
            RIASECAnswer.objects.filter(response=response).delete()
            RIASECAnswer.objects.bulk_create([
                RIASECAnswer(response=response, question=q, rating=cleaned[qid])
                for qid, q in valid_questions.items()
            ])

        return redirect("assessment:skills")

    return render(request, "assessment/interests.html", {
        "rating_options": RATING_OPTIONS,
    })


@login_required
@require_POST
@rate_limited("questions", "ASSESSMENT_REQUESTS_PER_MINUTE", 60, by_user=True)
def next_question(request):
    """JSON endpoint: given the answer history, return the next question."""
    try:
        body = parse_json(request.body.decode("utf-8") or "{}")
        if not isinstance(body, dict):
            raise ValueError
        history, _ = clean_history(body.get("history", []))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "bad request"}, status=400)

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
@require_http_methods(["GET", "POST"])
@rate_limited("assessment", "ASSESSMENT_REQUESTS_PER_MINUTE", 60, by_user=True)
@serialized_user_work
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
            submitted_skills = clean_skills(parse_json(raw))
        except ValueError:
            messages.error(request, "Skill data was malformed — please try again.")
            return redirect("assessment:skills")

        with transaction.atomic():
            response.completed_at = timezone.now()
            response.save(update_fields=["submitted_at", "completed_at"])
            invalidate_derived(request.user)
            SkillRating.objects.filter(response=response).delete()
            if submitted_skills:
                SkillRating.objects.bulk_create([
                    SkillRating(response=response, skill_name=n, rating=r)
                    for n, r in submitted_skills.items()
                ])

        # Compute lazily after redirect. Stored answers remain safe if ML is unavailable.

        messages.success(request, "Assessment saved! Your responses have been recorded.")
        return redirect("dashboard:index")

    return render(request, "assessment/skills.html", {
        "suggested_skills": suggested,
        "initial_ratings": initial_ratings,
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

@login_required
@require_GET
def skill_search(request):
    q = request.GET.get("q", "").strip()
    if len(q) > 100:
        return JsonResponse({"error": "Search query is too long."}, status=400)
    if len(q) < 2:
        return JsonResponse({"results": []})
    names = search_skill_names(q)
    return JsonResponse({"results": names})


@login_required
@require_POST
@serialized_user_work
def retake(request):
    with transaction.atomic():
        UserResponse.objects.filter(user=request.user).delete()
        invalidate_derived(request.user)
        request.session.pop("chatbot_history", None)
    return redirect("assessment:background")
