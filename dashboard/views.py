from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from accounts.models import UserProfile
from assessment.state import is_complete
from django.views.decorators.http import require_GET


@login_required
@require_GET
def index(request):
    has_assessment = is_complete(request.user)
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
