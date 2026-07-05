from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from accounts.models import UserProfile
from assessment.models import UserResponse
from recommender.cache import get_cached_or_compute


@login_required
def results(request):
    # Require assessment
    if not UserResponse.objects.filter(user=request.user).exists():
        return redirect("assessment:quiz")

    # Require profile — redirect with ?next= so they come back after saving
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if not profile.is_complete():
        return redirect("/accounts/profile/?next=/recommendations/")

    recommendations = get_cached_or_compute(request.user)
    return render(request, "recommender/results.html", {
        "recommendations": recommendations,
    })
