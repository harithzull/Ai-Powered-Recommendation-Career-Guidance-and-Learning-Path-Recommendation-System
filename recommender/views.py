from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from accounts.models import UserProfile
from recommender.cache import get_cached_or_compute
from assessment.state import is_complete
from django.views.decorators.http import require_GET


@login_required
@require_GET
def results(request):
    # Require assessment
    if not is_complete(request.user):
        return redirect("assessment:quiz")

    # Require profile — redirect with ?next= so they come back after saving
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if not profile.is_complete():
        return redirect("/accounts/profile/?next=/recommendations/")

    recommendations = get_cached_or_compute(request.user)
    return render(request, "recommender/results.html", {
        "recommendations": recommendations,
    })
