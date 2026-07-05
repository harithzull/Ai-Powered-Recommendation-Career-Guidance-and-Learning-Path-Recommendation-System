from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from accounts.models import UserProfile
from assessment.models import UserResponse


@login_required
def index(request):
    has_assessment = UserResponse.objects.filter(
        user=request.user, riasec_answers__isnull=False
    ).exists()
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    profile_complete = profile.is_complete()

    top_rec = None
    if has_assessment and profile_complete:
        from recommender.cache import get_cached_or_compute
        recs = get_cached_or_compute(request.user, top_n=5)
        if recs:
            top_rec = recs[0]

    return render(request, "dashboard/dashboard.html", {
        "has_assessment": has_assessment,
        "profile_complete": profile_complete,
        "top_rec": top_rec,
    })
