from django.contrib.auth.views import LoginView
from django.utils.decorators import method_decorator

from careercoach.security import rate_limited


@method_decorator(rate_limited("login", "LOGIN_ATTEMPTS_PER_MINUTE", 60), name="dispatch")
class ThrottledLoginView(LoginView):
    template_name = "accounts/login.html"
