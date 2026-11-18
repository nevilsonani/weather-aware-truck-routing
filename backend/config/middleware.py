from collections.abc import Callable

from django.http import HttpRequest, HttpResponse, JsonResponse

HEALTH_PATH = "/api/health"


class HealthCheckMiddleware:
    """Answers the liveness probe before host validation, HTTPS redirects or throttling.

    Platform health checkers (Render, load balancers, Kubernetes) often call the service by an
    internal IP or hostname that is not in ``ALLOWED_HOSTS`` and over plain HTTP; Django would
    reject or redirect those requests and the deploy would be marked unhealthy. Must be first
    in ``MIDDLEWARE``.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.path == HEALTH_PATH and request.method in ("GET", "HEAD"):
            return JsonResponse({"status": "ok"})
        return self.get_response(request)
