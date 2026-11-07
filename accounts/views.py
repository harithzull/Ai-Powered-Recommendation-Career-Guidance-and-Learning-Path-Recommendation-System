from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods
from django.db import transaction

from assessment.state import invalidate_derived
from careercoach.security import rate_limited, serialized_user_work

from .forms import ProfileForm, RegisterForm
from .models import UserProfile


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


@require_http_methods(["GET", "POST"])
@rate_limited("register", "REGISTER_ATTEMPTS_PER_HOUR", 3600)
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
@require_http_methods(["GET", "POST"])
@serialized_user_work
def profile(request):
    instance, _ = UserProfile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=instance)
        if form.is_valid():
            with transaction.atomic():
                form.save()
                invalidate_derived(request.user)
            messages.success(request, "Profile saved.")
            return redirect(_safe_next(request))
    else:
        form = ProfileForm(instance=instance)
    return render(request, "accounts/profile.html", {
        "form": form,
        "next": request.GET.get("next", ""),
    })
