from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.utils import timezone

from .validation import clean_skills, parse_json
from .state import invalidate_derived
from careercoach.security import rate_limited, serialized_user_work
from .models import SkillRating, UserResponse
from .suggested_skills import get_suggested_skills
from recommender.scoring import riasec_profile
from recommender.aliases import search_skill_names

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
def interests(request):
    if request.method == "POST":
        return JsonResponse({"error": "Legacy submissions are retired. Start a versioned assessment."}, status=410)
    return redirect("assessment:start")


@login_required
@require_POST
def next_question(request):
    return JsonResponse({"error": "The legacy adaptive endpoint is retired. Start a balanced assessment."}, status=410)


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
        if not response.riasec_answers.exists() and not response.active_session_id:
            return redirect("assessment:interests")
    except UserResponse.DoesNotExist:
        return redirect("assessment:interests")

    # Compute RIASEC profile from the already-prefetched answers (no extra query)
    profile = riasec_profile(response)

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
    return redirect("assessment:start")


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
@rate_limited("interest-start", "ASSESSMENT_REQUESTS_PER_MINUTE", 60, by_user=True)
@serialized_user_work
def retake(request):
    from .v2_views import begin
    return begin(request)
