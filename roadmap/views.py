from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from assessment.state import is_complete
from careercoach.security import consume, serialized_user_work
from recommender.cache import RecommendationUnavailable
from recommender.models import Career
from roadmap.generator import _steps_from_json, get_or_create_roadmap
from roadmap.models import RoadmapProgress, SavedRoadmap


@login_required
@require_http_methods(["GET", "POST"])
@serialized_user_work
def roadmap(request, career_id):
    career = get_object_or_404(Career, pk=career_id)
    if not is_complete(request.user):
        return redirect("assessment:interests")

    saved = SavedRoadmap.objects.filter(user=request.user, career=career).first()
    steps = None
    if saved:
        try:
            steps = _steps_from_json(saved.steps_json)
            if not steps or [s.index for s in steps] != list(range(len(steps))):
                steps = None
        except (ValueError, TypeError, KeyError, AttributeError):
            pass

    if request.method == "POST" and request.POST.get("action") == "generate":
        if steps is None:
            if not consume("roadmap-day", request.user.pk, settings.ROADMAP_REQUESTS_PER_DAY, 86400):
                response = JsonResponse({"error": "Daily roadmap limit reached. Please try again later."}, status=429)
                response["Retry-After"] = "86400"
                return response
            with transaction.atomic():
                SavedRoadmap.objects.filter(user=request.user, career=career).delete()
                RoadmapProgress.objects.filter(user=request.user, career=career).delete()
            try:
                get_or_create_roadmap(request.user, career)
            except (OSError, RuntimeError, ImportError, ValueError) as exc:
                raise RecommendationUnavailable from exc
        return redirect("roadmap:roadmap", career_id=career.pk)

    if steps is None:
        if request.method == "POST":
            return JsonResponse({"error": "Generate a roadmap before updating progress."}, status=400)
        return render(request, "roadmap/start.html", {"career": career})

    valid_indices = {s.index for s in steps}
    if request.method == "POST":
        submitted = set()
        for key in request.POST:
            if key.startswith("step_"):
                try:
                    index = int(key.removeprefix("step_"))
                except ValueError:
                    return JsonResponse({"error": "Invalid roadmap step."}, status=400)
                if index not in valid_indices:
                    return JsonResponse({"error": "Invalid roadmap step."}, status=400)
                submitted.add(index)
        with transaction.atomic():
            RoadmapProgress.objects.filter(user=request.user, career=career).delete()
            RoadmapProgress.objects.bulk_create([
                RoadmapProgress(user=request.user, career=career, step_index=i) for i in submitted
            ])
        return redirect("roadmap:roadmap", career_id=career.pk)

    completed = set(RoadmapProgress.objects.filter(user=request.user, career=career)
                    .values_list("step_index", flat=True)) & valid_indices
    total, done = len(steps), len(completed)
    return render(request, "roadmap/roadmap.html", {
        "career": career, "roadmap_title": saved.title, "overview": saved.overview,
        "steps_ctx": [{"step": s, "done": s.index in completed} for s in steps],
        "total": total, "done": done, "progress_pct": round(done / total * 100) if total else 0,
    })
