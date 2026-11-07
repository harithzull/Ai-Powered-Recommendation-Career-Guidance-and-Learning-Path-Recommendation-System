from django.urls import reverse

from accounts.models import UserProfile
from recommender.cache import get_cached_or_compute
from assessment.state import is_complete


def navigation(request):
    """Shared navigation links that depend on the signed-in user's results."""
    recommendations_url = reverse("recommender:results")
    context = {"top_roadmap_url": recommendations_url}

    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return context

    has_assessment = is_complete(user)
    if not has_assessment:
        return context

    profile, _ = UserProfile.objects.get_or_create(user=user)
    if not profile.is_complete():
        return context

    # Navigation must not initiate ML work or mutate state while rendering a page.
    recs = get_cached_or_compute(user, top_n=1, compute=False)
    if recs:
        context["top_roadmap_url"] = reverse(
            "roadmap:roadmap",
            kwargs={"career_id": recs[0]["career"].pk},
        )

    return context
