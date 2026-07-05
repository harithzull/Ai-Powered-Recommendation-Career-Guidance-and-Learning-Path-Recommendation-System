from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import ProfileForm, RegisterForm
from .models import UserProfile
from assessment.models import UserResponse


def _safe_next(request, default="dashboard:index"):
    """
    Return a validated redirect target from POST then GET, falling back to
    `default` if the value is absent or points off-site.

    Uses Django's url_has_allowed_host_and_scheme so only same-host paths
    are accepted, and https-only when the current request is secure.
    """
    next_url = request.POST.get("next") or request.GET.get("next", "")
    url_is_safe = url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    )
    return next_url if url_is_safe else default


def register(request):
    if request.user.is_authenticated:
        return redirect("dashboard:index")
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f"Account created. Welcome, {user.username}!")
            return redirect("dashboard:index")
    else:
        form = RegisterForm()
    return render(request, "accounts/register.html", {"form": form})


@login_required
def profile(request):
    instance, _ = UserProfile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile saved.")
            # If the user has completed the assessment, recompute recommendations
            # now so the next page load uses the updated background score.
            if UserResponse.objects.filter(
                user=request.user, riasec_answers__isnull=False, skill_ratings__isnull=False
            ).exists():
                from recommender.cache import compute_and_cache
                compute_and_cache(request.user)
            return redirect(_safe_next(request))
    else:
        form = ProfileForm(instance=instance)
    return render(request, "accounts/profile.html", {
        "form": form,
        "next": request.GET.get("next", ""),
    })
