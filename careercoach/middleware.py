from django.http import HttpResponse
from django.core.exceptions import RequestDataTooBig, TooManyFieldsSent, TooManyFilesSent

from .security import WorkInProgress


class ServiceErrorMiddleware:
    """Friendly errors without rendering templates that depend on recommendations."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        match = getattr(request, 'resolver_match', None)
        if match and match.namespace == 'resume' and match.url_name.startswith('analysis_'):
            # Also cover responses produced before the view, such as CSRF failures.
            from resume.views import private_response
            return private_response(response)
        return response

    def process_exception(self, request, exception):
        from recommender.cache import RecommendationUnavailable
        if isinstance(exception, RecommendationUnavailable):
            return HttpResponse("Recommendations are temporarily unavailable. Please try again later.", status=503)
        if isinstance(exception, WorkInProgress):
            response = HttpResponse("Another request is being processed. Please try again.", status=409)
            response["Retry-After"] = "5"
            return response
        if isinstance(exception, (RequestDataTooBig, TooManyFieldsSent, TooManyFilesSent)):
            return HttpResponse("The submitted request is too large.", status=413)
