from django.http import HttpResponse
from django.core.exceptions import RequestDataTooBig, TooManyFieldsSent, TooManyFilesSent

from .security import WorkInProgress


class ServiceErrorMiddleware:
    """Friendly errors without rendering templates that depend on recommendations."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

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
