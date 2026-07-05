from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from assessment.models import UserResponse
from recommender.models import Career
from roadmap.generator import get_or_create_roadmap
from roadmap.models import RoadmapProgress


@login_required
def roadmap(request, career_id: int):
    career = get_object_or_404(Career, pk=career_id)

    if not UserResponse.objects.filter(user=request.user).exists():
        return redirect("assessment:interests")

    steps, roadmap_title, overview = get_or_create_roadmap(request.user, career)

    if request.method == "POST":
        valid_indices = {s.index for s in steps}
        submitted = set()
        for key in request.POST:
            if key.startswith("step_"):
                try:
                    idx = int(key.removeprefix("step_"))
                    if idx in valid_indices:
                        submitted.add(idx)
                except ValueError:
                    pass

        RoadmapProgress.objects.filter(user=request.user, career=career).delete()
        if submitted:
            RoadmapProgress.objects.bulk_create([
                RoadmapProgress(user=request.user, career=career, step_index=i)
                for i in submitted
            ])

        return redirect("roadmap:roadmap", career_id=career_id)

    completed = set(
        RoadmapProgress.objects
        .filter(user=request.user, career=career)
        .values_list("step_index", flat=True)
    )

    total = len(steps)
    done = len(completed)
    progress_pct = round(done / total * 100) if total else 0

    steps_ctx = [
        {"step": s, "done": s.index in completed}
        for s in steps
    ]

    return render(request, "roadmap/roadmap.html", {
        "career":        career,
        "roadmap_title": roadmap_title,
        "overview":      overview,
        "steps_ctx":     steps_ctx,
        "total":         total,
        "done":          done,
        "progress_pct":  progress_pct,
    })
